#!/usr/bin/env python3
"""AV2 Parte C: C1 a C6, coleta local e limitada de experimentos.

Executar na raiz do projeto que contém src/genresearch_servidor.py.
Usa apenas a biblioteca padrão; não altera o código da Parte B.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import json
import mmap
import os
from pathlib import Path
import resource
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
B_SERVER = ROOT / 'src' / 'genresearch_servidor.py'
DEMO = ROOT / 'dados' / 'documentos_demo'
MEG = 1024 * 1024


def agora():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def salvar_json(path, valor):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(valor, ensure_ascii=False, indent=2), encoding='utf-8')


def salvar_csv(path, linhas):
    if not linhas:
        return
    keys = list(dict.fromkeys(k for linha in linhas for k in linha))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(linhas)


def ler_meminfo():
    resultado = {}
    for linha in Path('/proc/meminfo').read_text().splitlines():
        partes = linha.split(':', 1)
        if len(partes) == 2 and partes[0] in {'MemFree', 'MemAvailable', 'Cached', 'SwapTotal', 'SwapFree'}:
            resultado[partes[0] + '_kib'] = int(partes[1].split()[0])
    return resultado


def processo_linux(pid):
    pasta = Path('/proc') / str(pid)
    info = {}
    try:
        for linha in (pasta / 'status').read_text().splitlines():
            for campo in ('VmRSS', 'VmSize', 'VmHWM', 'VmSwap', 'Threads'):
                if linha.startswith(campo + ':'):
                    info[campo + ('_kib' if campo != 'Threads' else '')] = int(linha.split()[1])
        for linha in (pasta / 'io').read_text().splitlines():
            chave, numero = linha.split(':', 1)
            if chave in ('rchar', 'wchar', 'read_bytes', 'write_bytes', 'syscr', 'syscw'):
                info[chave] = int(numero)
        estat = (pasta / 'stat').read_text()
        # Depois do último ')' vêm campos começando pelo state (campo 3).
        vals = estat[estat.rfind(')') + 2:].split()
        info['minflt'] = int(vals[7])
        info['majflt'] = int(vals[9])
    except (OSError, ValueError, IndexError):
        pass
    return info


class Amostrador:
    def __init__(self, pid):
        self.pid = pid
        self.parar = threading.Event()
        self.rss_max = 0
        self.vsz_max = 0
        self.thread_max = 0
        self.inicial = processo_linux(pid)
        self.final = {}
        self._thread = threading.Thread(target=self._executar, daemon=True)

    def _executar(self):
        while not self.parar.is_set():
            dado = processo_linux(self.pid)
            self.rss_max = max(self.rss_max, dado.get('VmRSS_kib', 0))
            self.vsz_max = max(self.vsz_max, dado.get('VmSize_kib', 0))
            self.thread_max = max(self.thread_max, dado.get('Threads', 0))
            self.parar.wait(0.01)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self.final = processo_linux(self.pid)
        self.parar.set()
        self._thread.join(timeout=2)

    def resultado(self):
        saida = {'rss_pico_amostrado_kib': max(self.rss_max, self.final.get('VmRSS_kib', 0)),
                 'vsz_pico_amostrado_kib': max(self.vsz_max, self.final.get('VmSize_kib', 0)),
                 'threads_max': self.thread_max,
                 'rss_final_kib': self.final.get('VmRSS_kib'),
                 'vsz_final_kib': self.final.get('VmSize_kib'),
                 'minflt_delta': self.final.get('minflt', 0) - self.inicial.get('minflt', 0),
                 'majflt_delta': self.final.get('majflt', 0) - self.inicial.get('majflt', 0)}
        for item in ('read_bytes', 'write_bytes', 'rchar', 'wchar', 'syscr', 'syscw'):
            saida[item + '_delta'] = self.final.get(item, 0) - self.inicial.get(item, 0)
        return saida


def gerar_corpus(path, tam):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size == tam:
        return
    livres = shutil.disk_usage(path.parent).free
    if livres < tam + 64 * MEG:
        raise RuntimeError('Espaço insuficiente para gerar corpus com margem de segurança')
    bloco = (b'SISTEMAS OPERACIONAIS memoria virtual pagina cache arquivos RAG embeddings ' * 16384)
    restante = tam
    with path.open('wb') as f:
        while restante:
            dado = bloco[:min(restante, len(bloco))]
            f.write(dado)
            restante -= len(dado)


def leitura_filho(modo, arquivo, tamanho):
    tamanho = int(tamanho)
    inicio_stats = processo_linux(os.getpid())
    mem_ini = ler_meminfo()
    digest = hashlib.sha256()
    contagem = 0
    inicio = time.perf_counter()
    with open(arquivo, 'rb') as f:
        if modo == 'C1':
            while contagem < tamanho:
                bloco = f.read(min(MEG, tamanho - contagem))
                if not bloco:
                    break
                digest.update(bloco)
                contagem += len(bloco)
        elif modo == 'C2':
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                while contagem < tamanho:
                    bloco = mm.read(min(MEG, tamanho - contagem))
                    if not bloco:
                        break
                    digest.update(bloco)
                    contagem += len(bloco)
        else:
            raise ValueError('modo inválido')
    tempo = time.perf_counter() - inicio
    fim_stats = processo_linux(os.getpid())
    ru = resource.getrusage(resource.RUSAGE_SELF)
    memoria_final = ler_meminfo()
    result = {'modo': modo, 'bytes_lidos': contagem, 'sha256': digest.hexdigest(),
              'leitura_s': tempo, 'rss_max_kib': ru.ru_maxrss,
              'rss_final_kib': fim_stats.get('VmRSS_kib'), 'vsz_final_kib': fim_stats.get('VmSize_kib'),
              'minflt_delta': fim_stats.get('minflt', 0) - inicio_stats.get('minflt', 0),
              'majflt_delta': fim_stats.get('majflt', 0) - inicio_stats.get('majflt', 0),
              'read_bytes_delta': fim_stats.get('read_bytes', 0) - inicio_stats.get('read_bytes', 0),
              'rchar_delta': fim_stats.get('rchar', 0) - inicio_stats.get('rchar', 0),
              'memavailable_antes_kib': mem_ini.get('MemAvailable_kib'),
              'memavailable_depois_kib': memoria_final.get('MemAvailable_kib'),
              'cached_antes_kib': mem_ini.get('Cached_kib'),
              'cached_depois_kib': memoria_final.get('Cached_kib')}
    print(json.dumps(result, ensure_ascii=False))


def leituras(testes, destino, reps, rapido):
    pasta = destino / 'C1_C2'
    pasta.mkdir(exist_ok=True, parents=True)
    tamanhos = [MEG if rapido else 2 * MEG, 4 * MEG if rapido else 16 * MEG]
    arquivo = ROOT / 'dados' / 'corpus_c1_c2_av2.bin'
    gerar_corpus(arquivo, max(tamanhos))
    sha = hashlib.sha256(arquivo.read_bytes()).hexdigest()
    saidas = []
    for tamanho in tamanhos:
        for r in range(1, reps + 1):
            ordem = ['C1', 'C2'] if r % 2 else ['C2', 'C1']
            for modo in ordem:
                if modo not in testes:
                    continue
                cmd = [sys.executable, str(Path(__file__).resolve()), '--leitura-filho', modo, str(arquivo), str(tamanho)]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=40, cwd=ROOT)
                if proc.returncode:
                    raise RuntimeError(f'Falha {modo}: {proc.stderr}')
                resultado = json.loads(proc.stdout.strip())
                resultado.update(repeticao=r, corpus_bytes=tamanho,
                                 horario_utc=agora(), arquivo=str(arquivo.relative_to(ROOT)))
                if resultado['bytes_lidos'] != tamanho:
                    raise RuntimeError(f'{modo} leu {resultado["bytes_lidos"]} bytes, esperados {tamanho}')
                saidas.append(resultado)
                print(f'[{modo}] repetição {r}: {tamanho // MEG} MiB em {resultado["leitura_s"]:.5f} s')
    # Evita tratar leituras de conteúdos diferentes como comparáveis.
    for tamanho in tamanhos:
        hashes = {x['sha256'] for x in saidas if x['corpus_bytes'] == tamanho}
        if len(hashes) > 1:
            raise RuntimeError(f'Checksum divergente em C1/C2 com corpus {tamanho}')
    salvar_json(pasta / 'leituras.json', {'corpus_sha256': sha, 'resultados': saidas})
    salvar_csv(pasta / 'leituras.csv', saidas)
    return saidas


def requisicao(url, obj=None, timeout=30):
    dados = None if obj is None else json.dumps(obj, ensure_ascii=False).encode('utf-8')
    req = Request(url, data=dados, headers={'Content-Type': 'application/json; charset=utf-8'},
                  method='POST' if obj is not None else 'GET')
    inicio = time.perf_counter()
    try:
        with urlopen(req, timeout=timeout) as resp:
            code = resp.status
            raw = resp.read()
    except HTTPError as exc:
        code = exc.code
        raw = exc.read()
    tempo = time.perf_counter() - inicio
    try:
        resposta = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        resposta = {'texto': raw[:500].decode('utf-8', errors='replace')}
    return {'http': code, 'cliente_s': tempo, 'corpo': resposta}


def porta_livre():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def preparar_base(destino):
    if not B_SERVER.is_file():
        raise FileNotFoundError(f'Falta {B_SERVER}; extraia o complemento da Parte B no mesmo projeto.')
    arquivos = sorted(DEMO.glob('*.txt'))
    if not arquivos:
        raise FileNotFoundError(f'Faltam documentos demo em {DEMO}')
    sys.path.insert(0, str(ROOT / 'src'))
    from genresearch_servidor import GenResearch
    db = destino / 'indice_base.sqlite3'
    log = destino / 'preparacao.jsonl'
    app = GenResearch(str(db), str(log), 1)
    try:
        for arq in arquivos:
            app.ingerir(arq.name, arq.read_text(encoding='utf-8'))
        stat = app.estatisticas_indice()
    finally:
        app.fechar()
    salvar_json(destino / 'preparacao.json', stat)
    return db


def copiar_sqlite(origem, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(origem) as source, sqlite3.connect(destino) as target:
        source.backup(target)


@contextmanager
def servidor(pasta, banco_base=None, trabalhadores=2, fila=8, cache=0):
    pasta.mkdir(parents=True, exist_ok=True)
    db = pasta / 'indice.sqlite3'
    if banco_base is not None:
        copiar_sqlite(banco_base, db)
    porta = porta_livre()
    cmd = [sys.executable, str(B_SERVER), 'servir', '--porta', str(porta),
           '--trabalhadores', str(trabalhadores), '--fila', str(fila), '--cache', str(cache),
           '--banco', str(db), '--log', str(pasta / 'servidor.jsonl')]
    (pasta / 'comando.txt').write_text(' '.join(cmd), encoding='utf-8')
    with (pasta / 'servidor_terminal.txt').open('w', encoding='utf-8') as output:
        processo = subprocess.Popen(cmd, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        url = f'http://127.0.0.1:{porta}'
        try:
            ate = time.monotonic() + 12
            while time.monotonic() < ate:
                if processo.poll() is not None:
                    raise RuntimeError(f'Servidor terminou antes de iniciar: {pasta / "servidor_terminal.txt"}')
                try:
                    resp = requisicao(url + '/saude', timeout=1)
                    if resp['http'] == 200:
                        break
                except (URLError, TimeoutError, OSError):
                    pass
                time.sleep(.07)
            else:
                raise TimeoutError('Servidor não respondeu em 12 s')
            with Amostrador(processo.pid) as medidor:
                yield url, medidor
        finally:
            if processo.poll() is None:
                processo.send_signal(signal.SIGINT)
                try:
                    processo.wait(timeout=7)
                except subprocess.TimeoutExpired:
                    processo.terminate()
                    try:
                        processo.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        processo.kill()
                        processo.wait(timeout=3)
            (pasta / 'exit_code.txt').write_text(str(processo.returncode), encoding='utf-8')


def percentil(l, p):
    if not l:
        return 0
    l = sorted(l)
    indice = (len(l) - 1) * p
    inicio = int(indice)
    fim = min(len(l) - 1, inicio + 1)
    return l[inicio] * (fim - indice) + l[fim] * (indice - inicio)


def consulta_padrao(i):
    opcoes = ['memória virtual paginação', 'cache de páginas Linux',
              'produtores consumidores mutex', 'RAG embeddings índice',
              'arquivos mmap', 'swap memória virtual']
    # Número produz chaves distintas mesmo quando o tema se repete.
    return f'Explique {opcoes[i % len(opcoes)]}, solicitação número {i + 1}.'


def consulta_lote(url, textos, produtores=1):
    inicio = time.perf_counter()
    resultados = [None] * len(textos)
    def trabalho(i):
        dado = requisicao(url + '/consultar', {'consulta': textos[i]}, timeout=60)
        return i, dado
    with ThreadPoolExecutor(max_workers=produtores) as pool:
        pendentes = [pool.submit(trabalho, i) for i in range(len(textos))]
        for futura in as_completed(pendentes):
            i, valor = futura.result()
            resultados[i] = {'consulta': textos[i], **valor}
    duracao = time.perf_counter() - inicio
    tempos = [d['cliente_s'] for d in resultados]
    return resultados, {
        'solicitacoes': len(textos), 'sucesso': sum(1 for x in resultados if x['http'] == 200),
        'falhas': sum(1 for x in resultados if x['http'] != 200),
        'tempo_lote_s': duracao, 'vazao_req_s': len(resultados) / duracao if duracao else 0,
        'latencia_media_s': sum(tempos) / len(tempos),
        'latencia_mediana_s': percentil(tempos, .5),
        'latencia_p95_s': percentil(tempos, .95),
    }


def executar_C3(destino, db, reps, rapido):
    pasta = destino / 'C3'
    saidas = []
    quantidade = 12 if rapido else 32
    textos = [consulta_padrao(i) for i in range(quantidade)]
    for trabalhadores in (1, 2, 4):
        for r in range(1, reps + 1):
            caso = pasta / f'trabalhadores_{trabalhadores}_rep_{r}'
            with servidor(caso, db, trabalhadores=trabalhadores, fila=8, cache=0) as (url, amostrador):
                mem_ini = ler_meminfo()
                detalhes, metricas = consulta_lote(url, textos, produtores=4)
                estado = requisicao(url + '/status')['corpo']
                mem_fim = ler_meminfo()
            salvar_json(caso / 'requisicoes.json', detalhes)
            salvar_json(caso / 'status.json', estado)
            linha = dict(configuracao='C3', repeticao=r, trabalhadores=trabalhadores,
                         produtores=4, capacidade_fila=8, cache_capacidade=0, **metricas,
                         fila_maxima=estado['fila_e_processamento']['fila_maxima'],
                         fila_media_amostrada=estado['fila_e_processamento']['tamanho_medio_fila_amostrado'],
                         espera_media_fila_s=estado['fila_e_processamento']['espera_media_fila_s'],
                         memavailable_antes_kib=mem_ini.get('MemAvailable_kib'),
                         memavailable_depois_kib=mem_fim.get('MemAvailable_kib'), **amostrador.resultado())
            saidas.append(linha)
            print(f'[C3] {trabalhadores} trabalhadores, rep {r}: {metricas["sucesso"]}/{quantidade}, vazão {metricas["vazao_req_s"]:.1f} req/s')
    salvar_csv(pasta / 'resultados.csv', saidas)
    salvar_json(pasta / 'resultados.json', saidas)
    return saidas


def executar_C4(destino, db, reps, rapido):
    pasta = destino / 'C4'
    saidas = []
    quant = 6 if rapido else 12
    for cache in (0, 8):
        for padrao in ('repetidas', 'distintas'):
            consultas = (['O que é memória virtual e paginação?'] * quant
                         if padrao == 'repetidas' else [consulta_padrao(i) for i in range(quant)])
            for r in range(1, reps + 1):
                caso = pasta / f'cache_{cache}_{padrao}_rep_{r}'
                with servidor(caso, db, trabalhadores=2, fila=8, cache=cache) as (url, amostrador):
                    detalhes, metricas = consulta_lote(url, consultas, produtores=1)
                    estado = requisicao(url + '/status')['corpo']
                salvar_json(caso / 'requisicoes.json', detalhes)
                salvar_json(caso / 'status.json', estado)
                cs = estado['cache']
                linha = dict(configuracao='C4', repeticao=r, capacidade_cache=cache,
                             padrao_consultas=padrao, acertos=cs['acertos'], erros=cs['erros'],
                             substituicoes=cs['substituicoes'], taxa_acerto=cs['taxa_acerto'],
                             tempo_economizado_estimado_s=cs['tempo_economizado_estimado_s'],
                             **metricas, **amostrador.resultado())
                saidas.append(linha)
                print(f'[C4] cache={cache}, {padrao}, rep {r}: {cs["acertos"]} hits / {cs["erros"]} misses')
    salvar_csv(pasta / 'resultados.csv', saidas)
    salvar_json(pasta / 'resultados.json', saidas)
    return saidas


def executar_C5(destino, reps, rapido):
    pasta = destino / 'C5'
    saidas = []
    mem = ler_meminfo()
    if mem.get('MemAvailable_kib', 0) < 512 * 1024:
        raise RuntimeError('C5 interrompido: MemAvailable < 512 MiB; não criar pressão sem margem')
    tamanhos = (32 * 1024, 128 * 1024) if rapido else (256 * 1024, 1024 * 1024)
    base = ('memoria virtual pagina cache sistemas operacionais dados RAG embeddings. ' * 200)
    for tam in tamanhos:
        for r in range(1, reps + 1):
            caso = pasta / f'corpus_{tam//1024}kib_rep_{r}'
            conteudo = (base * ((tam // len(base)) + 1))[:tam]
            with servidor(caso, None, trabalhadores=2, fila=8, cache=0) as (url, amostrador):
                inicio = ler_meminfo()
                ingestao = requisicao(url + '/documentos', {'nome': 'corpus_c5.txt',
                              'conteudo': conteudo, 'tamanho_trecho': 400}, timeout=120)
                if ingestao['http'] != 200:
                    raise RuntimeError(f'Falha na ingestão C5: {ingestao["corpo"]}')
                textos = [consulta_padrao(i) for i in range(4 if rapido else 8)]
                detalhes, metricas = consulta_lote(url, textos, produtores=2)
                estado = requisicao(url + '/status')['corpo']
                fim = ler_meminfo()
            salvar_json(caso / 'requisicoes.json', detalhes)
            salvar_json(caso / 'ingestao.json', ingestao)
            salvar_json(caso / 'status.json', estado)
            linha = dict(configuracao='C5', repeticao=r, corpus_proposto_bytes=tam,
                         corpus_armazenado_bytes=estado['armazenamento']['corpus_bytes'],
                         indice_bytes=estado['armazenamento']['indice_bytes'],
                         trechos=estado['armazenamento']['trechos'],
                         ingestao_http_s=ingestao['cliente_s'],
                         ingestao_interna_s=ingestao['corpo']['ingestao_s'],
                         memavailable_antes_kib=inicio.get('MemAvailable_kib'),
                         memavailable_depois_kib=fim.get('MemAvailable_kib'),
                         cached_antes_kib=inicio.get('Cached_kib'),
                         cached_depois_kib=fim.get('Cached_kib'),
                         swap_usada_inicio_kib=inicio.get('SwapTotal_kib', 0)-inicio.get('SwapFree_kib', 0),
                         swap_usada_fim_kib=fim.get('SwapTotal_kib', 0)-fim.get('SwapFree_kib', 0),
                         **metricas, **amostrador.resultado())
            saidas.append(linha)
            print(f'[C5] corpus={tam//1024} KiB, rep {r}: índice {linha["indice_bytes"]} B, RSS amostrado {linha["rss_pico_amostrado_kib"]} KiB')
    salvar_csv(pasta / 'resultados.csv', saidas)
    salvar_json(pasta / 'resultados.json', saidas)
    return saidas


def executar_C6(destino, db, reps):
    pasta = destino / 'C6'
    saidas = []
    for r in range(1, reps + 1):
        caso = pasta / f'falha_controlada_rep_{r}'
        with servidor(caso, db, trabalhadores=2, fila=8, cache=4) as (url, amostrador):
            invalida = requisicao(url + '/consultar', {'consulta': ''})
            saudavel = requisicao(url + '/saude')
            valida = requisicao(url + '/consultar', {'consulta': 'O que é memória virtual?'})
            estado = requisicao(url + '/status')['corpo']
        comando = [sys.executable, str(B_SERVER), 'preparar', '--diretorio',
                   str(caso / 'diretorio_inexistente'), '--banco', str(caso / 'banco_ausencia.sqlite3'),
                   '--log', str(caso / 'ingestao_ausencia.jsonl')]
        ausente = subprocess.run(comando, cwd=ROOT, capture_output=True, text=True, timeout=20)
        detalhes = {'consulta_invalida': invalida, 'saude_apos_falha': saudavel,
                    'consulta_valida_apos_falha': valida, 'status': estado,
                    'preparar_diretorio_ausente': {'exit_code': ausente.returncode,
                      'stdout': ausente.stdout, 'stderr': ausente.stderr, 'comando': comando}}
        salvar_json(caso / 'falhas_e_recuperacao.json', detalhes)
        linha = dict(configuracao='C6', repeticao=r,
                     http_consulta_invalida=invalida['http'],
                     http_saude_apos_falha=saudavel['http'],
                     http_consulta_valida_apos_falha=valida['http'],
                     exit_code_corpus_ausente=ausente.returncode,
                     falhas_no_servidor=estado['fila_e_processamento']['falhas'],
                     **amostrador.resultado())
        saidas.append(linha)
        print(f'[C6] rep {r}: inválida {invalida["http"]}, recuperação {valida["http"]}, arquivo ausente exit={ausente.returncode}')
    salvar_csv(pasta / 'resultados.csv', saidas)
    salvar_json(pasta / 'resultados.json', saidas)
    return saidas


def executar():
    parser = argparse.ArgumentParser(description='AV2: experimentos C1-C6 com evidências reproduzíveis')
    parser.add_argument('--testes', nargs='+', choices=['C1', 'C2', 'C3', 'C4', 'C5', 'C6'],
                        default=['C1', 'C2', 'C3', 'C4', 'C5', 'C6'])
    parser.add_argument('--repeticoes', type=int, default=3)
    parser.add_argument('--rapido', action='store_true', help='Somente verificação funcional, NÃO vale como experimento final')
    parser.add_argument('--saida', help='Diretório de resultados: padrão cria subpasta com data/hora')
    parser.add_argument('--leitura-filho', nargs=3, metavar=('MODO', 'ARQUIVO', 'BYTES'),
                        help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.leitura_filho:
        leitura_filho(*args.leitura_filho)
        return
    if sys.platform != 'linux':
        parser.error('Este coletor usa /proc e Linux; execute no Ubuntu/WSL/Linux.')
    if args.repeticoes < 1:
        parser.error('repeticoes >= 1')
    if args.repeticoes < 3 and not args.rapido:
        parser.error('O enunciado exige >= 3 repetições; só use valores menores com --rapido')
    if args.rapido:
        print('ATENÇÃO: MODO RÁPIDO PARA VERIFICAÇÃO, NÃO USAR NO RELATÓRIO COMO ENSAIO FINAL.')
    nome = datetime.now().strftime('execucao_%Y%m%d_%H%M%S') + f'_{os.getpid()}'
    destino = Path(args.saida).resolve() if args.saida else ROOT / 'resultados' / 'parte_c' / nome
    destino.mkdir(parents=True, exist_ok=False)
    testes = set(args.testes)
    manifesto = {'horario_utc': agora(), 'comando': sys.argv,
                 'versao_python': sys.version, 'sistema': os.uname().sysname,
                 'kernel': os.uname().release, 'cwd_raiz': str(ROOT),
                 'repeticoes': args.repeticoes, 'modo_rapido': args.rapido,
                 'testes': sorted(testes),
                 'sha256_script': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 'sha256_servidor_b': (hashlib.sha256(B_SERVER.read_bytes()).hexdigest()
                                       if B_SERVER.exists() else None)}
    try:
        manifesto['commit_git'] = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                     capture_output=True, text=True, timeout=2).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        manifesto['commit_git'] = None
    salvar_json(destino / 'manifesto.json', manifesto)
    print('Resultados em:', destino)
    try:
        if {'C1', 'C2'} & testes:
            leituras(testes, destino, args.repeticoes, args.rapido)
        db = None
        if {'C3', 'C4', 'C6'} & testes:
            db = preparar_base(destino)
        if 'C3' in testes:
            executar_C3(destino, db, args.repeticoes, args.rapido)
        if 'C4' in testes:
            executar_C4(destino, db, args.repeticoes, args.rapido)
        if 'C5' in testes:
            executar_C5(destino, args.repeticoes, args.rapido)
        if 'C6' in testes:
            executar_C6(destino, db, args.repeticoes)
    except Exception as exc:
        salvar_json(destino / 'erro.json', {'erro': repr(exc), 'horario_utc': agora()})
        raise
    manifesto['finalizado_utc'] = agora()
    salvar_json(destino / 'manifesto.json', manifesto)
    print('\nCONCLUÍDO. Os arquivos brutos estão em:', destino)
    print('Não use resultados de --rapido como dados experimentais oficiais.')


if __name__ == '__main__':
    executar()
