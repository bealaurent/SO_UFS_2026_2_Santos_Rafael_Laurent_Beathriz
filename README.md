# AV2 — GenResearch-Servidor | Guia de instalação, execução e reprodução

**Disciplina:** Sistemas Operacionais — 2026.2 — Universidade Federal de Sergipe (UFS)  
**Projeto:** Memória, armazenamento, sincronização e desempenho de aplicações inspiradas em IA generativa/RAG  
**Repositório do grupo:** https://github.com/bealaurent/SO_UFS_2026_2_Santos_Rafael_Laurent_Beathriz

Este README orienta a reprodução das **Partes A, B, C (C1–C6), D e E**, incluindo os testes funcionais, experimentos oficiais e coleta de evidências. Os experimentos utilizam **Python no Linux**, um **GenResearch-Servidor didático**, vetores simulados e **respostas simuladas**; **não executam inferência real com Ollama ou um LLM**.

> **Importante:** execute os comandos a partir da pasta `ATV_2/`, a menos que uma etapa indique o contrário. As medições variam entre máquinas; os valores impressos nos exemplos são critérios de verificação, não resultados que todo participante necessariamente obterá. Os testes de `--rapido` e de `strace` são **complementares** e não substituem as repetições oficiais.

## 1. Estrutura esperada

```text
SO_UFS_2026_2_Santos_Rafael_Laurent_Beathriz/
├── ATV_1/                           # Materiais da atividade anterior
├── ATV_2/
│   ├── src/
│   │   └── genresearch_servidor.py
│   ├── scripts/
│   │   ├── testar_parte_b.py
│   │   ├── experimentos_c.py
│   │   └── experimentos_d.py
│   ├── tests/
│   │   ├── test_parte_b.py
│   │   └── test_parte_d.py
│   ├── dados/
│   │   └── documentos_demo/         # Textos sintéticos (.txt)
│   ├── docs/
│   │   ├── PARTE_B.md
│   │   ├── PARTE_C.md
│   │   └── PARTE_D.md
│   ├── evidencias/                   # Saídas do terminal e strace
│   ├── logs/                         # Eventos estruturados JSONL
│   ├── resultados/                   # CSV, JSON e logs dos ensaios
│   ├── requirements.txt             # Dependências Python, se incluído
│   └── README.md                    # Este guia
└── README.md                        # Apresentação geral do grupo
```

Os scripts geram automaticamente pastas de saída e arquivos de corpus/índice quando necessário. Para executar, **é indispensável que os quatro documentos `.txt` estejam presentes em `dados/documentos_demo/`**. Não é necessário versionar os corpora `.bin` ou os bancos SQLite gerados, desde que o código e os dados-fonte para recriá-los estejam disponíveis.

## 2. Requisitos e instalação (Ubuntu/Linux)

**Recomendado:** Linux nativo, Python 3.12 (versão utilizada nos testes do grupo), `git`, `curl`, `strace`, `ps` e ferramentas de monitoramento. WSL2 ou contêiner também podem funcionar, mas devem ser declarados separadamente na metodologia; métricas de memória/E/S podem diferir.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl strace procps sysstat
```

Clonar o repositório:

```bash
git clone https://github.com/bealaurent/SO_UFS_2026_2_Santos_Rafael_Laurent_Beathriz.git
cd SO_UFS_2026_2_Santos_Rafael_Laurent_Beathriz
```

Se a AV2 ainda estiver apenas na branch de desenvolvimento (e não na `main`), selecione-a:

```bash
git fetch origin
git switch av2-experimentos-rafael
```

Entre na pasta da avaliação:

```bash
cd ATV_2
```

Crie e ative um ambiente Python virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 --version
```

Se o arquivo `requirements.txt` estiver presente em `ATV_2/`, instale suas dependências:

```bash
python3 -m pip install -r requirements.txt
```

Os **scripts novos das Partes B, C e D usam a biblioteca padrão do Python**; o arquivo de dependências pode ser necessário para os módulos anteriores do grupo. Verifique o conteúdo de `requirements.txt` antes de executar.

Confira os arquivos essenciais:

```bash
ls src/genresearch_servidor.py
ls scripts/testar_parte_b.py scripts/experimentos_c.py scripts/experimentos_d.py
ls dados/documentos_demo/*.txt
```

Não use `sudo` para executar os testes Python. Os servidores didáticos escutam apenas em `127.0.0.1`.

## 3. Parte A — Inventário do ambiente

A Parte A consiste em **coletar e interpretar características do ambiente**, não em iniciar o servidor. Cada participante que reproduzir os experimentos deve registrar seu próprio ambiente, pois os resultados dependem da máquina.

```bash
mkdir -p evidencias/parte_a

{
  echo '===== DATA/HORA ====='; date -Is
  echo '===== DISTRIBUIÇÃO ====='; cat /etc/os-release
  echo '===== KERNEL ====='; uname -a
  echo '===== CPU ====='; lscpu; nproc
  echo '===== RAM E SWAP ====='; free -h; swapon --show
  echo '===== MEMINFO ====='; cat /proc/meminfo
  echo '===== DISCO ====='; lsblk -f; df -h
  echo '===== LINGUAGEM ====='; python3 --version
  echo '===== VERSÃO DO CÓDIGO ====='; git rev-parse HEAD
} > evidencias/parte_a/inventario.txt 2>&1
```

Se houver GPU NVIDIA:

```bash
nvidia-smi > evidencias/parte_a/gpu_nvidia.txt
```

Amostras curtas do sistema (cada comando dura aproximadamente cinco segundos):

```bash
vmstat 1 5 > evidencias/parte_a/vmstat.txt
iostat -xz 1 5 > evidencias/parte_a/iostat.txt
```

Na análise, explicar `MemFree`, `MemAvailable`, cache de páginas, swap, paginação e relevância para documentos/índices. Informar se o ambiente é Linux nativo, VM, WSL2 ou contêiner. A Parte A **não é substituída** pelos resultados de C1–C6.

## 4. Parte B — GenResearch-Servidor (verificação funcional)

Primeiro, execute todos os testes unitários:

```bash
python3 -m unittest discover -s tests -v
```

Na versão com as Partes B e D, o conjunto contém **cinco testes**. A saída deve terminar em `OK`. Se falhar, não prossiga aos ensaios oficiais antes de investigar.

Prepare o índice com os documentos sintéticos:

```bash
python3 src/genresearch_servidor.py preparar
```

Inicie o servidor no **Terminal 1**:

```bash
python3 src/genresearch_servidor.py servir \
  --porta 8765 \
  --trabalhadores 2 \
  --fila 8 \
  --cache 8
```

Mantenha esse terminal aberto. No **Terminal 2**, entre na mesma pasta `ATV_2/` e, se necessário, ative o ambiente virtual. Execute:

```bash
curl -s http://127.0.0.1:8765/saude
python3 scripts/testar_parte_b.py
curl -s http://127.0.0.1:8765/status | python3 -m json.tool
```

O teste demonstra ingestão, armazenamento SQLite, recuperação de trechos, fila de consultas, consumidores, resposta simulada, acertos/erros de cache e logs.

**Evidências principais:**

```text
logs/parte_b.jsonl
logs/teste_parte_b.json
dados/indice_parte_b.sqlite3           # banco gerado; pode ser recriado
```

O endpoint `/status` fornece contadores da fila, cache e armazenamento. Para preservar uma cópia:

```bash
mkdir -p evidencias/parte_b
curl -s http://127.0.0.1:8765/status \
  | python3 -m json.tool \
  > evidencias/parte_b/status_servidor.json
```

Encerre o servidor do Terminal 1 com `Ctrl+C` antes de iniciar os benchmarks oficiais, para reduzir interferências no desempenho.

## 5. Parte C — Experimentos C1 a C6

O executor `scripts/experimentos_c.py` cria um **diretório novo por execução** em `resultados/parte_c/`. Para C3–C6 ele inicia e encerra seus próprios servidores locais; não é necessário deixar o servidor da Parte B funcionando.

Crie a pasta das evidências e permita ao Bash detectar falhas em comandos ligados a `tee`:

```bash
mkdir -p evidencias/parte_c
set -o pipefail
```

### 5.1 Teste rápido opcional — somente verificação

```bash
python3 scripts/experimentos_c.py --rapido --repeticoes 1 \
  | tee evidencias/parte_c/ensaio_rapido.txt
```

O modo rápido usa parâmetros menores, **não vale como resultado oficial** e não substitui as três repetições exigidas.

### 5.2 C1 e C2 — Leitura convencional versus `mmap`

```bash
python3 scripts/experimentos_c.py --testes C1 C2 --repeticoes 3 \
  | tee evidencias/parte_c/execucao_C1_C2.txt
```

- **C1:** leitura com `open()`/`read()` em blocos de 1 MiB.
- **C2:** leitura com arquivo mapeado (`mmap`) e processamento em blocos de 1 MiB.
- **Tamanhos:** 2 MiB e 16 MiB, com três repetições por método/tamanho (**12 leituras**).
- O executor alterna a ordem dos métodos e compara os hashes SHA-256 dos dados processados.

**Resultado:** `resultados/parte_c/execucao_.../C1_C2/leituras.csv` e `leituras.json`.

### 5.3 C3 — Concorrência e fila

```bash
python3 scripts/experimentos_c.py --testes C3 --repeticoes 3 \
  | tee evidencias/parte_c/execucao_C3.txt
```

- Quatro produtores HTTP e **1, 2 ou 4 trabalhadores consumidores**.
- Três repetições por quantidade de trabalhadores (**9 cenários; 32 consultas por cenário**).
- Registra latência média, mediana e p95; vazão, fila, espera, memória, threads, faltas de página e E/S.

**Resultado:** `.../C3/resultados.csv`, `resultados.json` e os arquivos de cada cenário (`status.json`, `requisicoes.json`, `servidor.jsonl`, `comando.txt`).

### 5.4 C4 — Cache compartilhado

```bash
python3 scripts/experimentos_c.py --testes C4 --repeticoes 3 \
  | tee evidencias/parte_c/execucao_C4.txt
```

- Cache **desligado (`0`)** versus cache **LRU de oito entradas (`8`)**.
- Consultas **repetidas** versus **distintas**.
- Três repetições por combinação (**12 cenários**).
- Registra hits, misses, substituições, economia de tempo estimada e latências.

**Resultado:** `.../C4/resultados.csv`, `resultados.json` e evidências por cenário.

### 5.5 C5 — Variação controlada do corpus

```bash
python3 scripts/experimentos_c.py --testes C5 --repeticoes 3 \
  | tee evidencias/parte_c/execucao_C5.txt
```

- Corpora sintéticos de **256 KiB e 1024 KiB**, três repetições por tamanho (**6 cenários**).
- Registra tempo de ingestão, tamanho do índice, trechos, RSS, VSZ, `MemAvailable`, swap, faltas de página, E/S e latências.
- **Não é um teste de esgotamento de RAM:** variação de corpus não garante paginação intensa, swap ou *thrashing*. Não force pressão perigosa na memória.

**Resultado:** `.../C5/resultados.csv` e `resultados.json`, além de `ingestao.json` e logs por cenário.

### 5.6 C6 — Falhas controladas

```bash
python3 scripts/experimentos_c.py --testes C6 --repeticoes 3 \
  | tee evidencias/parte_c/execucao_C6.txt
```

Executa três rodadas com entrada inválida e recuperação, além de diretório de ingestão ausente. **Critérios observados nos testes do grupo:** HTTP `400` para consulta inválida; HTTP `200` para saúde e consulta válida depois da falha; código de saída `2` para corpus ausente. São falhas **intencionais**; não significam erro inesperado do benchmark.

**Resultado:** `.../C6/resultados.csv`, `falhas_e_recuperacao.json`, registros de inicialização/erro e códigos de saída.

### 5.7 Quantidade de medições da Parte C

| Teste | Execuções/cenários oficiais |
|---|---:|
| C1 e C2 | 12 leituras |
| C3 | 9 cenários |
| C4 | 12 cenários |
| C5 | 6 cenários |
| C6 | 3 rodadas |
| **Total** | **42** |

Também é possível executar **todos os testes em uma única invocação**:

```bash
python3 scripts/experimentos_c.py --repeticoes 3 \
  | tee evidencias/parte_c/execucao_C1_a_C6.txt
```

Para investigar resultados de uma execução, use **o caminho exato impresso pelo executor**. Para localizar todos os CSVs existentes:

```bash
find resultados/parte_c -type f \( -name 'leituras.csv' -o -name 'resultados.csv' \) | sort
find resultados/parte_c -name 'erro.json'
```

Cada cenário de C3 a C6 contém resultados brutos, logs e parâmetros. O arquivo `manifesto.json`, na pasta da execução, registra informações de reprodutibilidade. Não misture resultados de `--rapido` com os ensaios oficiais.

## 6. Parte D — Sincronização do cache: D1 e D2

O experimento reproduz uma situação de **trabalho duplicado** no ciclo `consultar cache → calcular → salvar` e sua correção por `threading.Lock`. O estado interno do LRU já é protegido; o objetivo é proteger a **operação composta**. A configuração D1 usa uma barreira proposital para reproduzir o entrelaçamento.

Teste unitário específico:

```bash
python3 -m unittest discover -s tests -p 'test_parte_d.py' -v
```

Execução oficial:

```bash
mkdir -p evidencias/parte_d
python3 scripts/experimentos_d.py \
  --repeticoes 3 \
  --trabalhadores 4 \
  --espera-ms 30 \
  | tee evidencias/parte_d/execucao_D1_D2.txt
```

| Medida por repetição | D1 — Sem mutex na operação completa | D2 — Com mutex |
|---|---:|---:|
| Consultas concluídas | 4 | 4 |
| Gerações realizadas | 4 | 1 |
| Gerações duplicadas | 3 | 0 |
| Hits / misses | 0 / 4 | 3 / 1 |

Esses são os resultados esperados da demonstração controlada; confira sempre os valores reais de sua execução.

**Saída:** `resultados/parte_d/execucao_.../resultados.csv` e `resultados.json`, além das pastas `D1_rep_1` a `D2_rep_3`, com `eventos.jsonl`, `resumo.json`, `respostas.json` e `ps_threads.txt`.

**Limitação:** os tempos de D1 e D2 não são um benchmark isolado de ganho de performance: D1 impõe uma barreira após o cache miss. A evidência principal é a **duplicação do cálculo e a eliminação dessa duplicação**.

## 7. Parte E — Memória virtual e armazenamento

A comparação principal de métodos e tamanhos utiliza os dados **oficiais de C1/C2 e C5**. Para obter evidência complementar das chamadas de sistema `openat`, `read`, `mmap`, `munmap` e `close`, execute:

```bash
mkdir -p evidencias/parte_e

strace -f -yy \
  -e trace=openat,read,close,mmap,munmap \
  -o evidencias/parte_e/strace_C1_C2.txt \
  python3 scripts/experimentos_c.py \
    --testes C1 C2 \
    --repeticoes 1 \
    --rapido \
  | tee evidencias/parte_e/execucao_strace_C1_C2.txt
```

**Por que `--rapido`?** O executor exige pelo menos três repetições nos ensaios oficiais; uma repetição é permitida apenas para verificação e rastreamento complementar. `strace` adiciona sobrecarga; **não use seus tempos como resultados oficiais**.

Filtrar chamadas relacionadas diretamente ao corpus:

```bash
grep 'corpus_c1_c2_av2.bin' \
  evidencias/parte_e/strace_C1_C2.txt \
  > evidencias/parte_e/chamadas_corpus.txt

grep 'munmap(' \
  evidencias/parte_e/strace_C1_C2.txt \
  > evidencias/parte_e/chamadas_munmap.txt
```

Verifique:

```bash
cat evidencias/parte_e/chamadas_corpus.txt
head -n 20 evidencias/parte_e/chamadas_munmap.txt
wc -l evidencias/parte_e/strace_C1_C2.txt
```

**Interpretação:** `read()` e `mmap()` não implicam necessariamente leitura física de disco (o cache de páginas pode satisfazer o acesso). O script de `mmap` mapeia o arquivo completo, mesmo quando processa apenas um prefixo. As repetições oficiais não controlam explicitamente estado frio/quente do cache; não afirme que uma leitura estava em cache frio sem evidências.

## 8. Como localizar e conferir todos os resultados

Execute a partir de `ATV_2/`:

```bash
# Pastas dos testes oficiais
find resultados/parte_c -maxdepth 1 -type d -name 'execucao_*' | sort
find resultados/parte_d -maxdepth 1 -type d -name 'execucao_*' | sort

# CSV dos experimentos
find resultados -type f -name '*.csv' | sort

# Evidências textuais
find evidencias -type f | sort

# Logs de sincronização
find resultados/parte_d -type f -name 'eventos.jsonl' | sort
```

**Checklist mínimo para a entrega:** código e documentos sintéticos; versão do ambiente e commit; instruções deste README; CSVs/JSONs de C1–C6; logs e manifesto por cenário; D1/D2 com arquivos `eventos.jsonl` e `ps_threads.txt`; evidências do `strace`; dados da Parte A; análise dos resultados, gráficos, relatório, apresentação, contribuição individual e vídeo.

## 9. Publicação e cuidados com o GitHub

Antes do commit, revise os arquivos que serão publicados:

```bash
git status --short
find resultados evidencias logs -type f -size +90M -print
```

**Não publique:** `.venv/`, `__pycache__/`, senhas, tokens, `.env`, informações pessoais desnecessárias, pesos de modelos ou grandes corpora recriáveis. A saída de `strace` e logs pode conter **caminhos absolutos e nomes de usuário locais**: revise esse conteúdo antes da publicação pública. Preserve CSVs/JSONs e evidências úteis, respeitando as regras do grupo e do professor.

Para atualizar especificamente este README após colocá-lo em `ATV_2/README.md`, a partir da **raiz do repositório**:

```bash
git add ATV_2/README.md
git commit -m 'docs(av2): adiciona guia de reprodução dos testes'
git push
```

Se estiver publicando uma branch nova pela primeira vez, use `git push -u origin NOME_DA_BRANCH` em vez de `git push`. O push requer autenticação por GitHub CLI, token pessoal ou SSH; **senha de conta não funciona para Git via HTTPS**.

## 10. Limitações e referências internas

- A aplicação didática usa **vetores por hashing e geração simulada**; respostas textuais não devem ser apresentadas como resultados de um LLM real.
- C5 compara tamanhos modestos e pode não produzir aumento da swap nem faltas de página maiores; não alegue *thrashing* sem medição.
- Alguns picos de RSS/VSZ são **amostrados** e podem perder picos curtos.
- A taxa de acerto do cache e o tempo economizado são específicos da carga usada. A economia é **estimada**.
- D1 demonstra processamento redundante, **não corrupção do dicionário**.
- Para detalhes de implementação, consulte `docs/PARTE_B.md`, `docs/PARTE_C.md` e `docs/PARTE_D.md`.

**Autoria e ferramentas:** o código e os guias complementares foram elaborados com auxílio de IA e devem ser revisados, validados e atribuídos pela equipe na documentação e na tabela de contribuições da AV2.
