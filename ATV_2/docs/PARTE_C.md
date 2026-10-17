# AV2 — Parte C: C1 a C6 (executor experimental reproduzível)

**Uso:** coloque `scripts/experimentos_c.py` no mesmo projeto que contém `src/genresearch_servidor.py` e `dados/documentos_demo/*.txt` (complemento da Parte B). Execute **no Linux**, preferencialmente nativo, como no inventário da Parte A. O script usa apenas bibliotecas padrão Python, `/proc` Linux e o servidor da Parte B. Não é necessário executar Ollama. Este código **não altera** os módulos de C1/C2 do grupo, que podem ser mantidos no repositório; fornece medições adicionais e padronizadas para a AV2.

## 1. Antes de executar

A partir da raiz do projeto:

```bash
python3 --version
python3 -m unittest discover -s tests -v
python3 src/genresearch_servidor.py preparar
```

Não precisa deixar o servidor da Parte B aberto: o executor inicia servidores em **portas locais efêmeras** e os encerra automaticamente a cada cenário. Evite rodar outros benchmarks ou jogos durante as medições, porque usam a mesma RAM/CPU/disco. **Não execute como root**. Prepare espaço de disco (pelo menos algumas centenas de MiB) e mantenha o equipamento em condições estáveis. Os servidores só escutam `127.0.0.1`.

## 2. Teste funcional rápido (NÃO é resultado experimental)

```bash
python3 scripts/experimentos_c.py --rapido --repeticoes 1 --testes C1 C2 C3 C4 C5 C6
```

Roda uma configuração reduzida. Confirme que aparece `CONCLUÍDO` e nenhum `erro.json`. **Não use esse ensaio como 3 repetições oficiais**.

## 3. Executar oficialmente, na ordem C1–C6

Recomendado executar C1 e C2 juntos, alternando a ordem dentro das repetições, para diminuir o viés de sempre favorecer a segunda leitura pelo cache de páginas.

```bash
python3 scripts/experimentos_c.py --testes C1 C2 --repeticoes 3
python3 scripts/experimentos_c.py --testes C3 --repeticoes 3
python3 scripts/experimentos_c.py --testes C4 --repeticoes 3
python3 scripts/experimentos_c.py --testes C5 --repeticoes 3
python3 scripts/experimentos_c.py --testes C6 --repeticoes 3
```

**Ou** execute tudo de uma vez:

```bash
python3 scripts/experimentos_c.py --repeticoes 3
```

Cada comando cria uma pasta nova em `resultados/parte_c/execucao_AAAAMMDD_HHMMSS_PID/`. Não apaga os testes anteriores.

## 4. Matriz experimental e arquivos

| Configuração | Controle do teste | Repetições oficiais | Dados principais |
| --- | --- | --- | --- |
| C1 | `open().read()` em blocos de 1 MiB, corpus sintético de 2 e 16 MiB | 3 por tamanho (6 leituras) | `C1_C2/leituras.csv`, `leituras.json` |
| C2 | `mmap(...).read()` em blocos de 1 MiB, **mesmos bytes de C1** | 3 por tamanho (6 leituras) | `C1_C2/leituras.csv`, `leituras.json` |
| C3 | 4 produtores HTTP; 1, 2 ou 4 consumidores (`--trabalhadores`); 32 consultas distintas, cache desativado | 3 por nº de trabalhadores (9 cenários) | `C3/resultados.csv`, casos com `requisicoes.json`, `status.json`, `servidor.jsonl` |
| C4 | cache desligado (0) vs LRU de 8 itens, consultas repetidas vs distintas, sequenciais para hits determinísticos | 3 por combinação (12 cenários) | `C4/resultados.csv`, casos com respostas e logs |
| C5 | aumentar **controladamente** um documento sintético de 256 KiB para 1024 KiB e comparar ingestão, índice e requisições | 3 por tamanho (6 cenários) | `C5/resultados.csv`, logs e ingestão |
| C6 | requisição inválida `HTTP 400` seguida de consulta saudável `HTTP 200`, mais ingestão de diretório inexistente com saída não-zero | 3 por cenário (3 rodadas, dois tipos de falha) | `C6/resultados.csv`, `falhas_e_recuperacao.json`, logs |

O executor varia **mais de três fatores**: método de leitura, tamanho do corpus, número de trabalhadores, tamanho do cache, tipo de consulta. Compara C1 e C2 no mesmo corpus binário; C3/C4/C6 usam os mesmos quatro documentos sintéticos da Parte B; somente C5 **varia deliberadamente** o corpus. Registre no relatório que os experimentos de E/S e de RAG usam corpora sintéticos de tamanhos diferentes por terem objetivos diferentes, não são comparação direta entre si.

## 5. Métricas e interpretação correta

- `leitura_s`, `tempo_lote_s`, `vazao_req_s`, `latencia_media_s`, `latencia_mediana_s`, `latencia_p95_s`: tempos e vazão.
- `rss_pico_amostrado_kib`, `vsz_pico_amostrado_kib`: amostras por `/proc/PID/status` a cada ~10 ms, podendo não capturar picos muito breves; `rss_max_kib` para C1/C2 é o pico reportado pelo kernel para o processo de leitura.
- `minflt_delta`, `majflt_delta`: faltas de página menores e maiores, diferenças de `/proc/PID/stat`. **Falta menor não significa acesso ao disco**.
- `read_bytes_delta`, `write_bytes_delta` e `syscr_delta`, `syscw_delta`: estatísticas de I/O do processo (`/proc/PID/io`) quando disponíveis. `read_bytes=0` é possível se a leitura for atendida pelo cache de páginas, não significa que não houve leitura lógica.
- `MemAvailable`, `Cached`, troca em swap: retratos do sistema inteiro, influenciados por outros processos.
- `fila_maxima`, `espera_media_fila_s` e `fila_media_amostrada`: fornecidos pela API; **fila_media_amostrada é média dos ingressos**, não média por unidade de tempo.
- `tempo_economizado_estimado_s`: estimativa do custo original da consulta guardada em cache, não economia diretamente medida em ambiente contrafactual.
- `C5` varia o tamanho do corpus para observar o aumento **sem forçar exaustão de RAM ou swap**. É possível não ocorrer swap/paginação intensa; registre esse resultado e os limites de segurança. O script aborta C5 se `MemAvailable < 512 MiB` antes de começar. Não use `stress-ng` ou desative swap sem aprovação e avaliação de risco.
- Em C1/C2, as leituras contam bytes e calculam SHA-256 sobre os mesmos dados para validar consistência. O cronômetro inclui a atualização do hash em ambos os métodos. As repetições alternam a ordem C1→C2 / C2→C1. **Não pressupõem cache de páginas frio**: se o professor quiser comparar cache frio/quente, adicionem ensaio separado e explicitamente documentado, sem `drop_caches` em máquina compartilhada.
- O servidor da Parte B usa vetores por hashing e geração de resposta **simulada**, não LLM. Não o descreva como IA generativa real ou recuperação semântica verificada.

## 6. Evidências e encerramento

Todo ensaio cria `manifesto.json` com comandos, versão Python/kernel, SHA-256 do coletor e do servidor e commit Git (se presente). Cada caso de C3 a C6 possui `comando.txt`, `servidor_terminal.txt`, `servidor.jsonl`, `status.json` e resultados brutos. C6 registra também `stderr` e código de saída do diretório ausente.

Para localizar resultados:

```bash
find resultados/parte_c -name 'resultados.csv' -o -name 'leituras.csv'
find resultados/parte_c -name 'erro.json'
```

Para inspecionar dados de um experimento (substitua `PASTA` pela pasta recém-criada):

```bash
cat PASTA/C1_C2/leituras.csv
cat PASTA/C3/resultados.csv
cat PASTA/C4/resultados.csv
cat PASTA/C5/resultados.csv
cat PASTA/C6/resultados.csv
```

Quando terminar, preservem `manifesto.json`, CSVs, `requisicoes.json`, `status.json`, logs e comandos. **Não incluam tokens, dados privados ou arquivos de modelos** no GitHub. Os arquivos grandes de corpus podem ser gerados pelo script e não precisam ser versionados; documentem o método e mantenham os resultados brutos.

## 7. Limite entre Parte C e Parte D

**C6 trata falhas de entrada/ingestão de forma controlada**, mas **não substitui** a Parte D (provar uma condição de corrida ou falha de sincronização, demonstrar correção usando mecanismo equivalente a mutex/semáforo e coletar as evidências). Faça essa demonstração separadamente, em execução isolada e segura.

**Atenção:** a entrega exige resultado real da máquina declarada na Parte A. Testes de desenvolvimento feitos em outra máquina, no modo rápido ou fora da equipe não podem substituir os dados que o grupo deve coletar.
