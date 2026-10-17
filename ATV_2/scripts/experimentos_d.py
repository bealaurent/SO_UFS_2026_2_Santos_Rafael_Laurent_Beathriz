#!/usr/bin/env python3
"""AV2 Parte D — experimento isolado de duplicação de trabalho no cache.

Reutiliza CacheLRU da Parte B. NÃO altera o servidor HTTP nem os dados da Parte C.
Em D1, a barreira pós-miss força uma interleaving reproduzível de misses.
Em D2, um mutex cobre o ciclo buscar->calcular->guardar.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.genresearch_servidor import CacheLRU  # noqa: E402

CONSULTA = "O que são mutexes e cache compartilhado?"
CHAVE = hashlib.sha256(CONSULTA.lower().encode('utf-8')).hexdigest()


def horario_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def salvar_json(caminho: Path, dados: Any) -> None:
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def simular_calculo(duracao_ms: int) -> tuple[str, float]:
    """I/O simulado (sleep) + cálculo de CPU, com resposta determinística."""
    t0 = time.perf_counter()
    time.sleep(duracao_ms / 1000)
    digest = hashlib.pbkdf2_hmac('sha256', CONSULTA.encode(), b'AV2-D', 5000).hex()
    return "Resposta simulada: " + digest[:32], time.perf_counter() - t0


def snapshot_threads(caminho: Path) -> None:
    """Registra threads enquanto todas aguardam sinal de início."""
    try:
        r = subprocess.run(
            ['ps', '-T', '-p', str(os.getpid()), '-o', 'pid,tid,stat,pcpu,pmem,comm'],
            capture_output=True, text=True, timeout=4, check=False,
        )
        caminho.write_text(r.stdout or r.stderr or 'ps não retornou conteúdo\n', encoding='utf-8')
    except (OSError, subprocess.TimeoutExpired) as exc:
        caminho.write_text('ps indisponível: ' + str(exc) + '\n', encoding='utf-8')


def executar_cenario(modo: str, repeticao: int, trabalhadores: int,
                     duracao_ms: int, pasta: Path) -> dict[str, Any]:
    if modo not in ('D1', 'D2'):
        raise ValueError('modo deve ser D1 ou D2')
    if not (2 <= trabalhadores <= 16):
        raise ValueError('trabalhadores deve estar entre 2 e 16')
    if not (5 <= duracao_ms <= 500):
        raise ValueError('espera-ms deve estar entre 5 e 500')

    pasta.mkdir(parents=True, exist_ok=False)
    cache = CacheLRU(capacidade=8)  # cache original da Parte B, com lock por operação
    mutex_transacao = threading.Lock()  # somente D2: protege leitura + processamento + escrita
    mutex_metricas = threading.Lock()
    inicio_liberado = threading.Event()
    pronto = threading.Semaphore(0)
    barreira_apos_miss = threading.Barrier(trabalhadores) if modo == 'D1' else None
    registros: list[dict[str, Any]] = []
    erros: list[str] = []
    contagem_calculos = [0]

    logger = logging.Logger(f'parte_d_{modo}_{os.getpid()}_{repeticao}', level=logging.INFO)
    handler = logging.FileHandler(pasta / 'eventos.jsonl', encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)

    def evento(nome: str, **campos: Any) -> None:
        logger.info(json.dumps({
            'horario_utc': horario_utc(), 'evento': nome,
            'thread': threading.current_thread().name,
            'tid': threading.get_native_id(), **campos,
        }, ensure_ascii=False))

    def calcular_e_guardar() -> tuple[dict[str, Any], str]:
        evento('geracao_iniciada', consulta_sha256=CHAVE)
        resposta, tempo_calculo = simular_calculo(duracao_ms)
        with mutex_metricas:
            contagem_calculos[0] += 1
            numero_calculo = contagem_calculos[0]
        valor = {'resposta': resposta, 'processamento_original_s': tempo_calculo}
        cache.guardar(CHAVE, valor)
        evento('cache_guardado', numero_calculo=numero_calculo,
               tempo_geracao_s=round(tempo_calculo, 8))
        return valor, 'miss'

    def trabalhador() -> None:
        try:
            pronto.release()
            if not inicio_liberado.wait(timeout=10):
                raise TimeoutError('sinal de início não recebido')
            t0 = time.perf_counter()
            tempo_mutex = 0.0
            evento('consulta_inicio', modo=modo)

            if modo == 'D1':
                item = cache.buscar(CHAVE)
                if item is None:
                    evento('cache_miss')
                    assert barreira_apos_miss is not None
                    # Intencional: todos veem miss antes de qualquer thread armazenar.
                    barreira_apos_miss.wait(timeout=10)
                    item, origem = calcular_e_guardar()
                else:
                    origem = 'hit'
                    evento('cache_hit')
            else:
                esperando_desde = time.perf_counter()
                with mutex_transacao:
                    tempo_mutex = time.perf_counter() - esperando_desde
                    evento('mutex_adquirido', espera_s=round(tempo_mutex, 8))
                    item = cache.buscar(CHAVE)
                    if item is None:
                        evento('cache_miss')
                        item, origem = calcular_e_guardar()
                    else:
                        origem = 'hit'
                        evento('cache_hit')
                evento('mutex_liberado')

            registro = {
                'thread': threading.current_thread().name,
                'tid': threading.get_native_id(),
                'cache': origem,
                'resposta': item['resposta'],
                'latencia_s': round(time.perf_counter() - t0, 8),
                'espera_mutex_s': round(tempo_mutex, 8),
            }
            with mutex_metricas:
                registros.append(registro)
            evento('consulta_concluida', cache=origem,
                   latencia_s=registro['latencia_s'])
        except Exception as exc:
            with mutex_metricas:
                erros.append(f'{threading.current_thread().name}: {type(exc).__name__}: {exc}')
            evento('erro', mensagem=str(exc), classe=type(exc).__name__)
            if barreira_apos_miss is not None:
                try:
                    barreira_apos_miss.abort()
                except Exception:
                    pass

    evento('inicializacao', modo=modo, repeticao=repeticao,
           trabalhadores=trabalhadores, atraso_simulado_ms=duracao_ms,
           chave_consulta_sha256=CHAVE)
    threads = [threading.Thread(target=trabalhador, name=f'consumidor-{i+1}')
               for i in range(trabalhadores)]
    try:
        for thread in threads:
            thread.start()
        for _ in threads:
            if not pronto.acquire(timeout=10):
                raise TimeoutError('nem todas as threads ficaram prontas')

        snapshot_threads(pasta / 'ps_threads.txt')
        inicio = time.perf_counter()
        inicio_liberado.set()
        for thread in threads:
            thread.join(timeout=10)
        ainda_vivas = [thread.name for thread in threads if thread.is_alive()]
        if ainda_vivas:
            erros.append('threads ainda vivas após 10 segundos: ' + repr(ainda_vivas))
        duracao_total = time.perf_counter() - inicio

        stats = cache.resumo()
        respostas_distintas = len({r['resposta'] for r in registros})
        duplicacoes = max(0, contagem_calculos[0] - 1)  # chave única no cenário
        valido = (len(registros) == trabalhadores and not erros and respostas_distintas == 1)
        consistente = (contagem_calculos[0] == trabalhadores and stats['erros'] == trabalhadores
                       and stats['acertos'] == 0 and duplicacoes == trabalhadores-1) if modo == 'D1' else (
                       contagem_calculos[0] == 1 and stats['erros'] == 1
                       and stats['acertos'] == trabalhadores-1 and duplicacoes == 0)
        linha = {
            'configuracao': modo,
            'repeticao': repeticao,
            'trabalhadores': trabalhadores,
            'atraso_simulado_ms': duracao_ms,
            'consultas': trabalhadores,
            'respostas_concluidas': len(registros),
            'respostas_distintas': respostas_distintas,
            'geracoes_realizadas': contagem_calculos[0],
            'geracoes_duplicadas': duplicacoes,
            'cache_hits': stats['acertos'],
            'cache_misses': stats['erros'],
            'cache_entradas': stats['tamanho'],
            'tempo_lote_s': round(duracao_total, 8),
            'latencia_media_s': round(statistics.mean(r['latencia_s'] for r in registros), 8) if registros else None,
            'espera_mutex_media_s': round(statistics.mean(r['espera_mutex_s'] for r in registros), 8) if registros else None,
            'falhas': len(erros),
            'sucesso': valido and consistente,
        }
        evento('encerramento', **linha)
        salvar_json(pasta / 'respostas.json', sorted(registros, key=lambda r: r['thread']))
        salvar_json(pasta / 'resumo.json', {**linha, 'erros': erros, 'cache': stats})
        if not (valido and consistente):
            raise RuntimeError(f'falha na validação de {modo}, rep {repeticao}: {erros} / {linha}')
        return linha
    finally:
        inicio_liberado.set()
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=1)
        handler.close()
        logger.removeHandler(handler)


def main() -> None:
    p = argparse.ArgumentParser(description='AV2 Parte D: duplicação de trabalho no cache e correção por mutex')
    p.add_argument('--repeticoes', type=int, default=3)
    p.add_argument('--trabalhadores', type=int, default=4)
    p.add_argument('--espera-ms', type=int, default=30,
                   help='Atraso controlado do processamento simulado (5..500 ms)')
    args = p.parse_args()
    if not 1 <= args.repeticoes <= 20:
        p.error('repeticoes deve ser entre 1 e 20')
    if not 2 <= args.trabalhadores <= 16:
        p.error('trabalhadores deve ser entre 2 e 16')
    if not 5 <= args.espera_ms <= 500:
        p.error('espera-ms deve ser entre 5 e 500')

    base = ROOT / 'resultados' / 'parte_d' / ('execucao_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                                            + f'_{os.getpid()}')
    base.mkdir(parents=True, exist_ok=False)
    def sha256_arquivo(arquivo: Path) -> str:
        return hashlib.sha256(arquivo.read_bytes()).hexdigest()
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                capture_output=True, text=True, timeout=3).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        commit = None
    salvar_json(base / 'manifesto.json', {
        'horario_utc': horario_utc(),
        'comando': ' '.join(sys.argv),
        'python': sys.version, 'kernel': platform.release(),
        'pid': os.getpid(), 'commit_git': commit,
        'sha256_script': sha256_arquivo(Path(__file__)),
        'sha256_cache_original': sha256_arquivo(ROOT / 'src/genresearch_servidor.py'),
        'consulta_sha256': CHAVE, 'repeticoes': args.repeticoes,
        'trabalhadores': args.trabalhadores, 'espera_ms': args.espera_ms,
        'nota': 'D1 força ordem de misses com barreira; não comparar tempos D1/D2 como benchmark puro.',
    })
    print('PARTE D — SINCRONIZAÇÃO DO CACHE', flush=True)
    print('Resultados em:', base, flush=True)
    resultados = []
    for modo in ['D1', 'D2']:
        for repeticao in range(1, args.repeticoes + 1):
            pasta = base / f'{modo}_rep_{repeticao}'
            r = executar_cenario(modo, repeticao, args.trabalhadores, args.espera_ms, pasta)
            resultados.append(r)
            print(f"[{modo}] repetição {repeticao}: geracoes={r['geracoes_realizadas']}, "
                  f"duplicadas={r['geracoes_duplicadas']}, hits={r['cache_hits']}, "
                  f"misses={r['cache_misses']}, respostas={r['respostas_concluidas']}, "
                  f"falhas={r['falhas']}", flush=True)
    campos = list(resultados[0].keys())
    with (base / 'resultados.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(resultados)
    salvar_json(base / 'resultados.json', resultados)
    print('\nCONCLUÍDO. Arquivos brutos em:', base, flush=True)
    print('D1 usa barreira pós-miss intencional; a evidência principal é duplicação vs. ausência de duplicação.', flush=True)


if __name__ == '__main__':
    main()
