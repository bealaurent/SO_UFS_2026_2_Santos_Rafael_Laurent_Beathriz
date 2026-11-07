# AV3 — Parte C: adaptação a partir da AV2

## Origem das ideias reutilizadas

A adaptação considera o ZIP `ATV_2.zip` enviado pela equipe. **Não é um kit oficial do professor** nem uma medição já executada. Seus arquivos originais permanecem intactos.

| Componente AV2 | Reaproveitamento nesta AV3 | Ajuste necessário |
| --- | --- | --- |
| `src/genresearch_servidor.py` — `hashlib.pbkdf2_hmac` para resposta simulada | Carga determinística de CPU do `carga_cpu.py` | Trabalho fixo por iterações, checksum, sem servidor HTTP/LLM |
| `scripts/experimentos_c.py` — `time.perf_counter`, `/proc`, CSV, JSON, registro de commit | Registro por repetição e consolidação | Captura do cgroup do **contêiner**, contadores de throttling, quotas efetivas |
| `scripts/experimentos_d.py` — `process_time`, JSON e registros isolados | Técnica de medir tempo da CPU e separar repetições | Remoção de threads/barreiras, que confundiriam a comparação de CPU |
| `scripts/testar_parte_b.py` | Não é adequado para a comparação C1/C2 | Mede consultas HTTP, não carga fixa sob quotas |

Os resultados da AV2 **não** são evidência da AV3; as seis medições precisam ser executadas novamente dentro dos contêineres.

## Instalação

Descompactar o kit na **raiz do repositório** (pasta que contém `ATV_2/` e `ATV_3/`), sem sobrescrever arquivos modificados por outros integrantes sem conferir. Os arquivos do kit estão em `ATV_3/scripts/` e `ATV_3/docs/`.

Pré-requisitos: Ubuntu/Linux com Docker ativo, cgroup v2, Python 3 no host, GNU `timeout`, `sudo` e a imagem `python:3.12-slim` com digest informado. Não requer pacotes Python extras e não requer GPU.

## Verificação rápida de sintaxe

```bash
cd ATV_3
python3 -m py_compile scripts/carga_cpu.py scripts/resumo.py
bash -n scripts/run_experimentos.sh
```

## 1) Piloto — ajustar a carga ANTES do oficial

```bash
cd ATV_3
MODO=piloto ITERACOES=1000000 bash scripts/run_experimentos.sh
```

A condição C1 (0,5 CPU) é executada **uma vez** para avaliar duração e confirmar, dentro do contêiner, `cpu.max`, `memory.max`, `memory.swap.max` e `pids.max`. Verifique `resultados/parte_c/piloto_*/C1_rep_1/registro.json`. Aumente ou reduza as iterações **apenas durante o piloto**, respeitando o máximo de 60 s de carga no contêiner e o timeout do host de 90 s. Não usar o piloto na estatística oficial.

## 2) Oficial — 3 C1 + 3 C2 alternados

Exemplo: se o piloto mostrar que 20 milhões de iterações é seguro, use:

```bash
ITERACOES=20000000 bash scripts/run_experimentos.sh
```

Se o valor escolhido no piloto for outro, substitua 20000000 pelo número congelado e mantenha-o nas **seis** execuções. O script alterna `C1-1, C2-1, C1-2, C2-2, C1-3, C2-3`. **Não altere `ITERACOES` durante a rodada.**

Parâmetros mantidos em todas as execuções: `--memory=256m`, `--memory-swap=256m`, `--pids-limit=64`, `--network none`, mesma imagem por digest e mesma carga. A quota muda entre `--cpus=0.5` e `--cpus=1.0`.

## 3) Resultado e análise

Saída, em `ATV_3/resultados/parte_c/oficial_DATA/`:

- `C1_rep_N/registro.json` e `C2_rep_N/registro.json`: seis registros brutos, incluindo checksum, tempos, confirmação dos limites e deltas de `cpu.stat`;
- `stdout.txt`, `stderr.txt`, `exit_code.txt`: preservam falhas e tentativas;
- `resultados.csv`: tabela consolidada com seis linhas;
- `resumo.md`: medianas, mínimos, máximos e variação;
- `grafico_tempo_c1_c2.svg`: gerado apenas quando as seis execuções são válidas, com **mediana e intervalo mínimo–máximo** por condição;
- `manifesto.txt`: digest da imagem, iterações e SHA256 do script, além de commit quando disponível.

Se necessário, gere o resumo novamente:

```bash
python3 scripts/resumo.py resultados/parte_c/oficial_NOME_DA_EXECUCAO
```

`trabalho_por_segundo` = iterações PBKDF2 / segundos; **não são tokens/s**. `tempo_cpu_s` mede o processo e `tempo_total_s` mede o relógio. `cpu.stat` pertence ao cgroup (inclui overhead do contêiner). `memory.current_bytes` é leitura pontual, `memory.peak_bytes` é o pico do cgroup desde sua criação, e `VmRSS_kib` é o RSS do processo: não confundir estas métricas.

## Limitações e segurança

- Experimento reproduzível de **CPU sintética**; não mede inferência de LLM nem GPU. A carga PBKDF2 é uma adaptação conceitual da AV2 e não garante equivalência de trabalho ao algoritmo da AV2.
- Quota não fixa afinidade nem reserva um núcleo. Fatores como outros processos, frequência da CPU, throttling ancestral, temperatura e versão do runtime afetam os tempos.
- Se o contêiner não conseguir ler seus próprios cgroups ou confirmar os limites, registra erro e a medição é **inválida**. Não substituir por valores inventados.
- A carga é limitada internamente a 60 s (checagem entre blocos) e externamente a 90 s via `timeout`. O script remove somente os contêineres que cria.
- A montagem é apenas leitura, o contêiner não tem rede, usa UID não root, descarta capabilities e bloqueia aquisição de novos privilégios. Nunca montar `/`, o Docker socket ou diretórios sigilosos para este teste.
- As Partes B e D precisam das próprias evidências (namespaces e montagem read-only). A Parte A precisa inventariar o **host do daemon**.
- Registrar no relatório que os scripts AV3 foram adaptados com auxílio de IA e verificados pelo grupo; os valores de resultados têm de vir da execução real.
