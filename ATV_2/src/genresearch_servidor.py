#!/usr/bin/env python3
"""AV2 Parte B: GenResearch-Servidor educacional (vetores e resposta simulados).

Usa somente a biblioteca padrão do Python. Executar na raiz do projeto.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import math
from pathlib import Path
import queue
import re
import sqlite3
import threading
import time
from typing import Any

DIM = 64
MAX_DOC_BYTES = 2_000_000


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def palavras(texto: str) -> list[str]:
    return re.findall(r"\w+", texto.lower(), flags=re.UNICODE)


def embedding_simulado(texto: str) -> list[float]:
    """Vetor estável por hashing de palavras, NÃO é embedding de modelo de IA."""
    vetor = [0.0] * DIM
    for token in palavras(texto):
        h = int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big")
        vetor[h % DIM] += 1.0 if (h >> 6) & 1 else -1.0
    norma = math.sqrt(sum(x * x for x in vetor))
    return [x / norma for x in vetor] if norma else vetor


def fragmentar(texto: str, max_chars: int) -> list[str]:
    """Fragmentação por palavras; quebra palavras longas quando necessário."""
    partes: list[str] = []
    atual = ""
    for palavra in texto.split():
        if len(palavra) > max_chars:
            if atual:
                partes.append(atual)
                atual = ""
            partes.extend(palavra[i:i + max_chars] for i in range(0, len(palavra), max_chars))
        elif not atual:
            atual = palavra
        elif len(atual) + 1 + len(palavra) <= max_chars:
            atual += " " + palavra
        else:
            partes.append(atual)
            atual = palavra
    if atual:
        partes.append(atual)
    return partes


@dataclass
class Trabalho:
    consulta: str
    top_k: int
    limite_contexto: int
    criado_em: float = field(default_factory=time.perf_counter)
    concluido: threading.Event = field(default_factory=threading.Event)
    resultado: dict[str, Any] | None = None
    erro: str | None = None


class CacheLRU:
    def __init__(self, capacidade: int):
        self.capacidade = capacidade
        self._entradas: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.substituicoes = 0
        self.tempo_economizado_estimado = 0.0

    def buscar(self, chave: str) -> dict[str, Any] | None:
        with self._lock:
            if chave not in self._entradas:
                self.misses += 1
                return None
            self.hits += 1
            self._entradas.move_to_end(chave)
            salvo = dict(self._entradas[chave])
            self.tempo_economizado_estimado += float(salvo.get("processamento_original_s", 0.0))
            return salvo

    def guardar(self, chave: str, valor: dict[str, Any]) -> bool:
        with self._lock:
            if self.capacidade == 0:
                return False
            if chave in self._entradas:
                self._entradas.move_to_end(chave)
                self._entradas[chave] = dict(valor)
                return False
            substituiu = len(self._entradas) >= self.capacidade
            if substituiu:
                self._entradas.popitem(last=False)
                self.substituicoes += 1
            self._entradas[chave] = dict(valor)
            return substituiu

    def limpar(self) -> None:
        with self._lock:
            self._entradas.clear()

    def resumo(self) -> dict[str, Any]:
        with self._lock:
            tentativas = self.hits + self.misses
            return {
                "capacidade": self.capacidade,
                "tamanho": len(self._entradas),
                "acertos": self.hits,
                "erros": self.misses,
                "substituicoes": self.substituicoes,
                "taxa_acerto": self.hits / tentativas if tentativas else 0.0,
                "tempo_economizado_estimado_s": round(self.tempo_economizado_estimado, 6),
            }


class GenResearch:
    def __init__(self, banco: str, log: str, trabalhadores: int = 2,
                 capacidade_fila: int = 8, capacidade_cache: int = 8):
        self.banco = Path(banco)
        self.banco.parent.mkdir(parents=True, exist_ok=True)
        self.log_path = Path(log)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger(f"genresearch-{id(self)}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        handler = logging.FileHandler(self.log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(handler)  # logging.FileHandler já protege escrita entre threads
        self._db_lock = threading.Lock()
        self._index_generation = 0  # invalida cache mesmo se houver requisições em andamento
        self._criar_banco()
        self.fila: queue.Queue[Trabalho | None] = queue.Queue(maxsize=capacidade_fila)
        self.cache = CacheLRU(capacidade_cache)
        self._metricas_lock = threading.Lock()
        self.metricas = {
            "produtores_requisicoes": 0,
            "consumidores_processamentos": 0,
            "requisições_concluídas": 0,
            "falhas": 0,
            "fila_amostras": 0,
            "fila_soma": 0,
            "fila_maxima": 0,
            "espera_fila_total_s": 0.0,
            "tempo_total_requisicoes_s": 0.0,
        }
        self.trabalhadores = []
        for numero in range(trabalhadores):
            thread = threading.Thread(target=self._consumidor, name=f"consumidor-{numero + 1}", daemon=True)
            thread.start()
            self.trabalhadores.append(thread)
        self.registrar("inicializacao", trabalhadores=trabalhadores, capacidade_fila=capacidade_fila,
                       capacidade_cache=capacidade_cache, banco=str(self.banco))

    def registrar(self, evento: str, **dados: Any) -> None:
        self._logger.info(json.dumps({"horario_utc": utc(), "evento": evento,
                                      "thread": threading.current_thread().name, **dados}, ensure_ascii=False))

    def _conexao(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.banco, timeout=15)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _criar_banco(self) -> None:
        with closing(self._conexao()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS documentos (
                    nome TEXT PRIMARY KEY, bytes INTEGER NOT NULL,
                    total_trechos INTEGER NOT NULL, criado_em TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trechos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    documento TEXT NOT NULL REFERENCES documentos(nome) ON DELETE CASCADE,
                    posicao INTEGER NOT NULL, texto TEXT NOT NULL, vetor TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_trechos_documento ON trechos(documento);
            """)
            conn.commit()

    def ingerir(self, nome: str, conteudo: str, tamanho_trecho: int = 400) -> dict[str, Any]:
        if not nome or len(nome) > 120 or any(c in nome for c in "/\\\n\r"):
            raise ValueError("nome de documento inválido")
        if not conteudo.strip():
            raise ValueError("documento vazio")
        tamanho = len(conteudo.encode("utf-8"))
        if tamanho > MAX_DOC_BYTES:
            raise ValueError(f"documento excede {MAX_DOC_BYTES} bytes (limite de segurança)")
        if not 80 <= tamanho_trecho <= 4000:
            raise ValueError("tamanho_trecho deve estar entre 80 e 4000 caracteres")
        inicio = time.perf_counter()
        trechos = fragmentar(conteudo, tamanho_trecho)
        with self._db_lock:
            with closing(self._conexao()) as conn:
                conn.execute("BEGIN")
                conn.execute("DELETE FROM documentos WHERE nome=?", (nome,))
                conn.execute("INSERT INTO documentos VALUES (?, ?, ?, ?)", (nome, tamanho, len(trechos), utc()))
                conn.executemany("INSERT INTO trechos (documento, posicao, texto, vetor) VALUES (?, ?, ?, ?)",
                                 [(nome, i, trecho, json.dumps(embedding_simulado(trecho)))
                                  for i, trecho in enumerate(trechos)])
                conn.commit()
            self._index_generation += 1
            self.cache.limpar()  # atualização do índice invalida respostas antigas
        duracao = round(time.perf_counter() - inicio, 6)
        resp = {"documento": nome, "bytes": tamanho, "trechos": len(trechos), "ingestao_s": duracao}
        self.registrar("ingestao", **resp)
        return resp

    def estatisticas_indice(self) -> dict[str, Any]:
        with closing(self._conexao()) as conn:
            docs = conn.execute("SELECT COUNT(*), COALESCE(SUM(bytes),0) FROM documentos").fetchone()
            chunks = conn.execute("SELECT COUNT(*) FROM trechos").fetchone()[0]
        # SQLite pode usar arquivos WAL e SHM; relatamos seus tamanhos também.
        tam = sum(p.stat().st_size for p in [self.banco, Path(str(self.banco) + "-wal"),
                                               Path(str(self.banco) + "-shm")] if p.exists())
        return {"documentos": docs[0], "corpus_bytes": docs[1], "trechos": chunks, "indice_bytes": tam}

    def _recuperar(self, consulta: str, top_k: int, limite_contexto: int) -> tuple[list[dict[str, Any]], str]:
        consulta_vetor = embedding_simulado(consulta)
        with closing(self._conexao()) as conn:
            linhas = conn.execute("SELECT documento, posicao, texto, vetor FROM trechos").fetchall()
        classificados = []
        for doc, pos, texto, vetor_json in linhas:
            vetor = json.loads(vetor_json)
            similaridade = sum(a * b for a, b in zip(consulta_vetor, vetor))
            classificados.append((similaridade, doc, pos, texto))
        classificados.sort(key=lambda v: v[0], reverse=True)
        contexto = ""
        selecionados = []
        for score, doc, pos, texto in classificados[:top_k]:
            # Corpus sem relação semântica não gera contextos arbitrários.
            if score <= 0:
                continue
            resto = limite_contexto - len(contexto)
            if resto <= 0:
                break
            recorte = texto[:resto]
            if not recorte:
                break
            contexto += recorte + ("\n" if len(recorte) < resto else "")
            selecionados.append({"documento": doc, "posicao": pos,
                                 "similaridade": round(score, 4), "caracteres": len(recorte)})
        return selecionados, contexto

    @staticmethod
    def _resposta_simulada(consulta: str, contexto: str) -> str:
        """Simula trabalho de CPU e monta extrato; não utiliza LLM."""
        hashlib.pbkdf2_hmac("sha256", (consulta + contexto).encode("utf-8"), b"AV2-GenResearch", 5000)
        return ("Resposta simulada a partir dos trechos recuperados: " + contexto[:240].replace("\n", " ")) if contexto else \
            "Nenhum trecho relevante foi recuperado para esta consulta."

    def _consumidor(self) -> None:
        while True:
            trabalho = self.fila.get()
            if trabalho is None:
                self.fila.task_done()
                return
            iniciado = time.perf_counter()
            espera = iniciado - trabalho.criado_em
            with self._metricas_lock:
                self.metricas["consumidores_processamentos"] += 1
                self.metricas["espera_fila_total_s"] += espera
            with self._db_lock:
                geracao_indice = self._index_generation
            chave = hashlib.sha256(json.dumps([trabalho.consulta.strip().lower(),
                                                  trabalho.top_k, trabalho.limite_contexto, geracao_indice],
                                                 ensure_ascii=False).encode("utf-8")).hexdigest()
            self.registrar("consumo", espera_fila_s=round(espera, 6), tamanho_fila=self.fila.qsize())
            try:
                item = self.cache.buscar(chave)
                if item is not None:
                    resultado = dict(item)
                    resultado.update(cache="hit", recuperacao_s=0.0, resposta_s=0.0,
                                     economia_estimada_s=item["processamento_original_s"])
                    self.registrar("cache_hit", chave=chave[:12])
                else:
                    self.registrar("cache_miss", chave=chave[:12])
                    t1 = time.perf_counter()
                    trechos, contexto = self._recuperar(trabalho.consulta, trabalho.top_k,
                                                        trabalho.limite_contexto)
                    tempo_recuperacao = time.perf_counter() - t1
                    self.registrar("recuperacao", trechos=len(trechos),
                                   contexto_bytes=len(contexto.encode("utf-8")),
                                   recuperacao_s=round(tempo_recuperacao, 6))
                    t2 = time.perf_counter()
                    resposta = self._resposta_simulada(trabalho.consulta, contexto)
                    tempo_resposta = time.perf_counter() - t2
                    resultado = {
                        "consulta": trabalho.consulta,
                        "resposta": resposta,
                        "trechos": trechos,
                        "contexto_bytes": len(contexto.encode("utf-8")),
                        "contexto_tokens_aproximados": len(palavras(contexto)),
                        "recuperacao_s": round(tempo_recuperacao, 6),
                        "resposta_s": round(tempo_resposta, 6),
                        "processamento_original_s": round(tempo_recuperacao + tempo_resposta, 6),
                        "cache": "miss", "economia_estimada_s": 0.0,
                    }
                    substituiu = self.cache.guardar(chave, resultado)
                    if substituiu:
                        self.registrar("cache_substituicao", chave=chave[:12])
                    self.registrar("geracao_simulada", duracao_s=round(tempo_resposta, 6),
                                   caracteres_resposta=len(resposta))
                resultado.update(espera_fila_s=round(espera, 6),
                                 tempo_total_s=round(time.perf_counter() - trabalho.criado_em, 6),
                                 consumidor=threading.current_thread().name)
                trabalho.resultado = resultado
                with self._metricas_lock:
                    self.metricas["requisições_concluídas"] += 1
                    self.metricas["tempo_total_requisicoes_s"] += resultado["tempo_total_s"]
                self.registrar("consulta_concluida", cache=resultado["cache"],
                               duracao_s=resultado["tempo_total_s"])
            except Exception as exc:
                trabalho.erro = str(exc)
                with self._metricas_lock:
                    self.metricas["falhas"] += 1
                self.registrar("falha", erro=str(exc))
            finally:
                trabalho.concluido.set()
                self.fila.task_done()

    def consultar(self, consulta: str, top_k: int = 3, limite_contexto: int = 800,
                 timeout: float = 30.0) -> dict[str, Any]:
        if not consulta or not consulta.strip() or len(consulta) > 2000:
            raise ValueError("consulta deve ter entre 1 e 2000 caracteres")
        if not 1 <= top_k <= 10 or not 100 <= limite_contexto <= 10000:
            raise ValueError("top_k deve estar entre 1 e 10 e limite_contexto entre 100 e 10000")
        trab = Trabalho(consulta.strip(), top_k, limite_contexto)
        try:
            self.fila.put(trab, timeout=2.0)
        except queue.Full as exc:
            with self._metricas_lock:
                self.metricas["falhas"] += 1
            self.registrar("fila_saturada", capacidade=self.fila.maxsize)
            raise RuntimeError("fila saturada: tempo de espera para inserir excedido") from exc
        tamanho = self.fila.qsize()
        with self._metricas_lock:
            self.metricas["produtores_requisicoes"] += 1
            self.metricas["fila_amostras"] += 1
            self.metricas["fila_soma"] += tamanho
            self.metricas["fila_maxima"] = max(self.metricas["fila_maxima"], tamanho)
        self.registrar("producao", tamanho_fila=tamanho, caracteres_consulta=len(consulta))
        if not trab.concluido.wait(timeout):
            self.registrar("timeout_consulta", segundos=timeout)
            raise TimeoutError("consulta excedeu o tempo limite; pode ainda estar na fila")
        if trab.erro is not None:
            raise RuntimeError(trab.erro)
        assert trab.resultado is not None
        return trab.resultado

    def status(self) -> dict[str, Any]:
        with self._metricas_lock:
            dados = dict(self.metricas)
        n = dados["consumidores_processamentos"]
        amostras = dados["fila_amostras"]
        dados["espera_media_fila_s"] = round(dados["espera_fila_total_s"] / n, 6) if n else 0
        dados["tamanho_medio_fila_amostrado"] = round(dados["fila_soma"] / amostras, 3) if amostras else 0
        dados["tamanho_atual_fila"] = self.fila.qsize()
        dados["trabalhadores"] = len(self.trabalhadores)
        return {"fila_e_processamento": dados, "cache": self.cache.resumo(),
                "armazenamento": self.estatisticas_indice()}

    def fechar(self) -> None:
        self.fila.join()
        for _ in self.trabalhadores:
            self.fila.put(None)
        for t in self.trabalhadores:
            t.join(timeout=5)
        self.registrar("encerramento", status=self.status())
        for handler in self._logger.handlers[:]:
            handler.close()
            self._logger.removeHandler(handler)


def criar_handler(servico: GenResearch):
    class Handler(BaseHTTPRequestHandler):
        def responder(self, codigo: int, obj: dict[str, Any]):
            dados = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def do_GET(self):
            if self.path == "/saude":
                self.responder(200, {"servico": "GenResearch-Servidor", "status": "ok"})
            elif self.path == "/status":
                self.responder(200, servico.status())
            else:
                self.responder(404, {"erro": "rota não encontrada"})

        def do_POST(self):
            if self.path not in ("/consultar", "/documentos"):
                self.responder(404, {"erro": "rota não encontrada"})
                return
            try:
                tam = int(self.headers.get("Content-Length", "0"))
                if not 1 <= tam <= MAX_DOC_BYTES + 50_000:
                    self.responder(413, {"erro": "payload inválido ou muito grande"})
                    return
                corpo = json.loads(self.rfile.read(tam).decode("utf-8"))
                if not isinstance(corpo, dict):
                    raise ValueError("esperado objeto JSON")
                if self.path == "/consultar":
                    resp = servico.consultar(corpo.get("consulta", ""),
                                            int(corpo.get("top_k", 3)),
                                            int(corpo.get("limite_contexto", 800)))
                else:
                    resp = servico.ingerir(corpo.get("nome", ""),
                                          corpo.get("conteudo", ""),
                                          int(corpo.get("tamanho_trecho", 400)))
                self.responder(200, resp)
            except ValueError as exc:
                self.responder(400, {"erro": str(exc)})
            except RuntimeError as exc:
                self.responder(503, {"erro": str(exc)})
            except TimeoutError as exc:
                self.responder(504, {"erro": str(exc)})
            except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self.responder(400, {"erro": f"entrada inválida: {exc}"})
            except Exception as exc:
                servico.registrar("falha_http", erro=str(exc))
                self.responder(500, {"erro": "falha interna; consulte os logs"})

        def log_message(self, formato, *args):
            servico.registrar("http", mensagem=formato % args)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="GenResearch-Servidor AV2 / Parte B")
    sub = parser.add_subparsers(dest="comando", required=True)
    ing = sub.add_parser("preparar", help="Ingerir arquivos .txt e criar índice SQLite")
    ing.add_argument("--diretorio", default="dados/documentos_demo")
    ing.add_argument("--tamanho-trecho", type=int, default=400)
    srv = sub.add_parser("servir", help="Iniciar API HTTP local com fila e cache")
    srv.add_argument("--porta", type=int, default=8765)
    srv.add_argument("--trabalhadores", type=int, default=2)
    srv.add_argument("--fila", type=int, default=8)
    srv.add_argument("--cache", type=int, default=8)
    for subcmd in [ing, srv]:
        subcmd.add_argument("--banco", default="dados/indice_parte_b.sqlite3")
        subcmd.add_argument("--log", default="logs/parte_b.jsonl")
    args = parser.parse_args()
    if args.comando == "preparar":
        app = GenResearch(args.banco, args.log, trabalhadores=1)
        try:
            docs = sorted(Path(args.diretorio).glob("*.txt"))
            if not docs:
                parser.error(f"não foram encontrados arquivos .txt em {args.diretorio}")
            for arquivo in docs:
                if arquivo.stat().st_size > MAX_DOC_BYTES:
                    parser.error(f"{arquivo} excede {MAX_DOC_BYTES} bytes; use documentos menores")
                print(json.dumps(app.ingerir(arquivo.name, arquivo.read_text(encoding="utf-8"),
                                             args.tamanho_trecho), ensure_ascii=False))
            print(json.dumps(app.estatisticas_indice(), ensure_ascii=False, indent=2))
        finally:
            app.fechar()
        return
    if args.trabalhadores < 1 or args.fila < 1 or args.cache < 0:
        parser.error("trabalhadores e fila >= 1; cache >= 0")
    app = GenResearch(args.banco, args.log, args.trabalhadores, args.fila, args.cache)
    servidor = ThreadingHTTPServer(("127.0.0.1", args.porta), criar_handler(app))
    print(f"GenResearch iniciado em http://127.0.0.1:{args.porta}", flush=True)
    print("Rotas: GET /saude, GET /status, POST /consultar, POST /documentos", flush=True)
    print("Para encerrar: Ctrl+C", flush=True)
    try:
        servidor.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("Encerrando o serviço...", flush=True)
    finally:
        servidor.server_close()
        app.fechar()


if __name__ == "__main__":
    main()
