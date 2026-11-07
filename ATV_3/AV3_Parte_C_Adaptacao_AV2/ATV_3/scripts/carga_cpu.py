#!/usr/bin/env python3
"""AV3 / Parte C — adaptação da carga PBKDF2 utilizada na AV2.

Roda dentro do contêiner Linux com cgroups v2. Uma execução = trabalho fixo.
Registra medição real; NÃO inventa dados quando controladores não são acessíveis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

CG = Path('/sys/fs/cgroup')


def texto(nome: str) -> str | None:
    try:
        return (CG / nome).read_text(encoding='utf-8').strip()
    except (OSError, UnicodeError):
        return None


def inteiro(nome: str) -> int | None:
    valor = texto(nome)
    try:
        return int(valor) if valor is not None else None
    except ValueError:
        return None


def cpu_stat() -> dict[str, int]:
    linhas = texto('cpu.stat')
    if linhas is None:
        return {}
    resultado = {}
    for linha in linhas.splitlines():
        partes = linha.split()
        if len(partes) == 2:
            try:
                resultado[partes[0]] = int(partes[1])
            except ValueError:
                pass
    return resultado


def mem_processo() -> dict[str, int]:
    resultado = {}
    try:
        conteudo = Path('/proc/self/status').read_text(encoding='utf-8')
        for linha in conteudo.splitlines():
            if linha.startswith(('VmRSS:', 'VmHWM:', 'VmSize:')):
                chave, valor = linha.split(':', 1)
                resultado[chave + '_kib'] = int(valor.split()[0])
    except (OSError, ValueError, IndexError):
        pass
    return resultado


def conferir_limites(cpu_max: str | None, mem_max: str | None,
                     swap_max: str | None, pids_max: str | None,
                     quota_esperada: float) -> tuple[bool, dict[str, bool]]:
    try:
        quota_us, periodo_us = map(int, (cpu_max or '').split())
        cpu_ok = abs(quota_us / periodo_us - quota_esperada) < 0.0001 and periodo_us > 0
    except (ValueError, ZeroDivisionError):
        cpu_ok = False
    itens = {
        'cpu': cpu_ok,
        'memory': mem_max == str(256 * 1024 * 1024),
        'swap': swap_max == '0',
        'pids': pids_max == '64',
    }
    return all(itens.values()), itens


def estourou_tempo(_signum, _frame):
    raise TimeoutError('carga excedeu o limite interno de 60 segundos')


def main() -> int:
    parser = argparse.ArgumentParser(description='AV3 — carga fixa PBKDF2 e métricas de cgroup v2')
    parser.add_argument('--iteracoes', type=int, required=True)
    parser.add_argument('--condicao', choices=['C1', 'C2'], required=True)
    parser.add_argument('--repeticao', type=int, required=True)
    args = parser.parse_args()
    if not (1 <= args.iteracoes <= 100_000_000):
        parser.error('iteracoes deve estar entre 1 e 100000000')

    quota = 0.5 if args.condicao == 'C1' else 1.0
    parametros = {
        'cpu.max': texto('cpu.max'),
        'memory.max': texto('memory.max'),
        'memory.swap.max': texto('memory.swap.max'),
        'pids.max': texto('pids.max'),
    }
    confirmado, itens = conferir_limites(parametros['cpu.max'], parametros['memory.max'],
                                         parametros['memory.swap.max'], parametros['pids.max'], quota)
    resultado = {
        'condicao': args.condicao,
        'repeticao': args.repeticao,
        'iteracoes': args.iteracoes,
        'imagem_python': sys.version.split()[0],
        'pid_contêiner': os.getpid(),
        'cgroup': parametros,
        'limites_verificados': itens,
        'limites_confirmados': confirmado,
        'status': 'erro_limites' if not confirmado else 'em_execucao',
    }

    if not confirmado:
        resultado['erro'] = 'quota/controladores não confirmados; medição não é válida'
        print('AV3_RESULTADO_JSON=' + json.dumps(resultado, ensure_ascii=False, sort_keys=True), flush=True)
        return 3

    antes = cpu_stat()
    t0 = time.perf_counter_ns()
    p0 = time.process_time_ns()
    erro = None
    chave = None
    signal.signal(signal.SIGALRM, estourou_tempo)
    signal.alarm(60)
    try:
        # Reaproveita a ideia da carga PBKDF2 do GenResearch da AV2.
        # Fracionar a carga permite conferir o timeout interno entre blocos;
        # um único PBKDF2 enorme poderia bloquear o tratamento de SIGALRM.
        checksum_incremental = hashlib.sha256()
        feitos = 0
        bloco = 100_000
        while feitos < args.iteracoes:
            atual = min(bloco, args.iteracoes - feitos)
            sal = b'AV2-reutilizacao-cgroups-' + (feitos // bloco).to_bytes(8, 'big')
            digest = hashlib.pbkdf2_hmac('sha256', b'genresearch-av3-carga-fixa',
                                         sal, atual, dklen=32)
            checksum_incremental.update(digest)
            feitos += atual
        chave = checksum_incremental.digest()
    except TimeoutError as exc:
        erro = str(exc)
    finally:
        signal.alarm(0)
    p1 = time.process_time_ns()
    t1 = time.perf_counter_ns()
    depois = cpu_stat()
    wall = (t1 - t0) / 1e9
    resultado.update({
        'status': 'timeout_interno' if erro else 'ok',
        'erro': erro,
        'checksum_sha256': hashlib.sha256(chave).hexdigest() if chave is not None else None,
        'tempo_total_s': round(wall, 8),
        'tempo_cpu_s': round((p1 - p0) / 1e9, 8),
        'trabalho_por_segundo': round(args.iteracoes / wall, 2) if (wall > 0 and not erro) else None,
        'cpu_stat_antes': antes,
        'cpu_stat_depois': depois,
        'cpu_stat_delta': {k: depois[k] - antes[k] for k in
                           ('usage_usec', 'nr_throttled', 'throttled_usec')
                           if k in antes and k in depois},
        'memory.current_bytes': inteiro('memory.current'),
        'memory.peak_bytes': inteiro('memory.peak'),
        'rss': mem_processo(),
    })
    print('AV3_RESULTADO_JSON=' + json.dumps(resultado, ensure_ascii=False, sort_keys=True), flush=True)
    return 124 if erro else 0


if __name__ == '__main__':
    sys.exit(main())
