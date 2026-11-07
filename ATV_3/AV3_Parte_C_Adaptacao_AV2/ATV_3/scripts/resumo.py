#!/usr/bin/env python3
"""AV3 Parte C — consolida medições reais e gera gráfico SVG sem dependências.

Não inventa valores nem produz gráfico oficial com dados ausentes/inválidos.
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
import statistics
import sys
from xml.sax.saxutils import escape


def valor_em(d, *chaves):
    for chave in chaves:
        if isinstance(d, dict):
            d = d.get(chave)
        else:
            return None
    return d


def gerar_svg(pasta, grupos):
    # Barras: mediana; linhas verticais: min/max de 3 repetições.
    valores = [v for lst in grupos.values() for v in lst]
    maior = max(valores) * 1.15 if valores else 1
    W,H,top,base = 780,440,80,355
    escala = (base-top) / maior
    elementos = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
     '<rect width="100%" height="100%" fill="white"/>',
     '<text x="40" y="37" font-family="sans-serif" font-weight="bold" font-size="20">AV3 • Tempo de execução sob quotas de CPU</text>',
     '<text x="40" y="59" font-family="sans-serif" font-size="13" fill="#555">Mediana e intervalo mín–máx • 3 repetições por condição • segundos</text>']
    for i in range(5):
        y = base - (i/4)* (base-top)
        n = maior*i/4
        elementos += [f'<line x1="105" y1="{y:.1f}" x2="710" y2="{y:.1f}" stroke="#ddd"/>',
                     f'<text x="90" y="{y+5:.1f}" font-size="12" font-family="sans-serif" text-anchor="end">{n:.1f}</text>']
    for x,(cond,cap) in ((260,('C1','0,5 CPU')),(530,('C2','1,0 CPU'))):
        tempos=grupos[cond]
        med=statistics.median(tempos)
        mini,maxi=min(tempos),max(tempos)
        y=base-med*escala
        alto=base-maxi*escala
        baixo=base-mini*escala
        elementos += [f'<rect x="{x-67}" y="{y:.1f}" width="134" height="{base-y:.1f}" fill="#4169a6" opacity="0.86"/>',
                     f'<line x1="{x}" y1="{alto:.1f}" x2="{x}" y2="{baixo:.1f}" stroke="#aa4c31" stroke-width="3"/>',
                     f'<line x1="{x-17}" y1="{alto:.1f}" x2="{x+17}" y2="{alto:.1f}" stroke="#aa4c31" stroke-width="3"/>',
                     f'<line x1="{x-17}" y1="{baixo:.1f}" x2="{x+17}" y2="{baixo:.1f}" stroke="#aa4c31" stroke-width="3"/>',
                     f'<text x="{x}" y="{max(77,y-12):.1f}" text-anchor="middle" font-family="sans-serif" font-size="13">{med:.3f} s</text>',
                     f'<text x="{x}" y="{base+24}" text-anchor="middle" font-family="sans-serif" font-size="15">{escape(cond)} · {escape(cap)}</text>']
    elementos += ['</svg>']
    (pasta / 'grafico_tempo_c1_c2.svg').write_text('\n'.join(elementos)+'\n', encoding='utf-8')


def main() -> int:
    if len(sys.argv)!=2:
        print('Uso: python3 scripts/resumo.py resultados/parte_c/oficial_...',file=sys.stderr)
        return 2
    pasta=Path(sys.argv[1]).resolve()
    arquivos=sorted(pasta.glob('C*_rep_*/registro.json'))
    if not arquivos:
        print('Nenhum registro encontrado',file=sys.stderr)
        return 2
    linhas=[]
    for arquivo in arquivos:
        r=json.loads(arquivo.read_text(encoding='utf-8'))
        linha={
            'condicao':r.get('condicao'),'repeticao':r.get('repeticao'),
            'iteracoes':r.get('iteracoes'),'status':r.get('status'),
            'docker_exit_code':r.get('docker_exit_code'),
            'limites_confirmados':r.get('limites_confirmados'),
            'checksum_sha256':r.get('checksum_sha256'),
            'tempo_total_s':r.get('tempo_total_s'),'tempo_cpu_s':r.get('tempo_cpu_s'),
            'trabalho_por_segundo':r.get('trabalho_por_segundo'),
            'cpu.max':valor_em(r,'cgroup','cpu.max'),
            'memory.max':valor_em(r,'cgroup','memory.max'),
            'memory.swap.max':valor_em(r,'cgroup','memory.swap.max'),
            'pids.max':valor_em(r,'cgroup','pids.max'),
            'usage_usec_delta':valor_em(r,'cpu_stat_delta','usage_usec'),
            'nr_throttled_delta':valor_em(r,'cpu_stat_delta','nr_throttled'),
            'throttled_usec_delta':valor_em(r,'cpu_stat_delta','throttled_usec'),
            'memory.current_bytes':r.get('memory.current_bytes'),
            'memory.peak_bytes':r.get('memory.peak_bytes'),
            'VmRSS_kib':valor_em(r,'rss','VmRSS_kib'),
            'VmHWM_kib':valor_em(r,'rss','VmHWM_kib'),
            'arquivo_origem':str(arquivo.relative_to(pasta))
        }
        linhas.append(linha)
    with (pasta/'resultados.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    grupos={c:[] for c in ('C1','C2')}
    trabalhos=set()
    digests=set()
    problemas=[]
    for r in linhas:
        if (r['status']=='ok' and r['docker_exit_code']==0 and r['limites_confirmados'] is True
                and r['tempo_total_s'] is not None and r['checksum_sha256']):
            grupos[r['condicao']].append(r['tempo_total_s'])
            trabalhos.add(r['iteracoes'])
            digests.add(r['checksum_sha256'])
        else:
            problemas.append(f"{r['condicao']} rep {r['repeticao']}: status={r['status']}; ver {r['arquivo_origem']}")
    completo=(len(arquivos)==6 and all(len(grupos[c])==3 for c in grupos)
              and len(trabalhos)==1 and len(digests)==1
              and {(r['condicao'],r['repeticao']) for r in linhas} ==
                    {(c,i) for c in ('C1','C2') for i in (1,2,3)})
    md=['# Resumo da Parte C — AV3','',f'**Execuções encontradas:** {len(arquivos)}',
        f'**Comparação oficial completa e válida:** {"SIM" if completo else "NÃO"}','']
    for cond in ('C1','C2'):
        vals=grupos[cond]
        if vals:
            md += [f'## {cond}', f'- Mediana wall time: {statistics.median(vals):.6f} s',
                f'- Mínimo e máximo: {min(vals):.6f} a {max(vals):.6f} s',
                f'- Amplitude: {max(vals)-min(vals):.6f} s',
                f'- Número de medições válidas: {len(vals)}','']
    if problemas:
        md += ['## Erros e tentativas inválidas']+[f'- {p}' for p in problemas]+['']
    if not completo:
        md += ['**Não usar como comparação conclusiva.** Corrigir impedimentos, preservar os arquivos de erro e gerar nova rodada oficial.','']
    else:
        gerar_svg(pasta,grupos)
        md += ['Gráfico: `grafico_tempo_c1_c2.svg` (mediana e mínimo-máximo).',
               'Trabalho: número fixo de iterações PBKDF2; **não são tokens/s**.','',
               'Interpretação requer considerar ruído de host, throttling e limites ancestrais.','']
    (pasta/'resumo.md').write_text('\n'.join(md),encoding='utf-8')
    print('\n'.join(md))
    print('CSV:',pasta/'resultados.csv')
    return 0 if completo else 1


if __name__=='__main__':
    sys.exit(main())
