# Atividade 3 — Sistemas Operacionais (UFS, 2026.2)

**Tema:** Virtualização, contêineres Linux, namespaces, cgroups e montagem somente leitura.  
**Projeto:** Laboratório reproduzível com Docker, reutilizando a ideia de carga PBKDF2 do GenResearch-Servidor (AV2).  
**Entrega:** 10/11/2026 · **Apresentação:** 11/11/2026.

> Este repositório contém os scripts e as evidências dos experimentos da AV3. O laboratório **não executa um LLM nem uma GPU**; usa uma carga sintética determinística de CPU para estudar mecanismos do Sistema Operacional. As medições são reais, obtidas ao executar os comandos nos contêineres, e não reutilizam os números da AV2.

## 1. Objetivo

Responder à questão: **como os namespaces alteram a visão dos processos, montagens e rede, e como os cgroups limitam recursos sem transformar um contêiner em uma máquina virtual independente?**

O laboratório está dividido em quatro partes:

| Parte | Experimento | Evidência principal |
|:---|:---|:---|
| **A** | Inventário do ambiente Linux e Docker | Distribuição, kernel, CPUs, RAM, Docker, cgroup v2, imagem por digest e diagrama de camadas |
| **B** | Comparação de dois contêineres | PID no host do daemon, PID 1 interno e handles dos namespaces PID, mount e network |
| **C** | Comparação de quotas de CPU | Seis medições válidas (C1/C2 × 3), JSON, CSV, gráfico, `cpu.max`, `cpu.stat` e limites de memória/tarefas |
| **D** | Montagem read-only e menor privilégio | Leitura permitida e tentativa de escrita negada em diretório sintético |

## 2. Organização dos arquivos

```text
ATV_3/
├── README.md                         # Este guia de preparação e reprodução
├── .gitignore                        # Evita versionar cópias do kit e arquivos temporários
├── scripts/
│   ├── carga_cpu.py                  # Carga PBKDF2 fixa + coleta de métricas no contêiner
│   ├── run_experimentos.sh           # Piloto ou seis execuções C1/C2, via Docker
│   └── resumo.py                     # Validação, CSV, estatísticas e gráfico SVG
├── dados_demo/
│   └── texto.txt                     # Arquivo sintético usado na Parte D
├── docs/
│   └── REUSO_AV2_AV3.md              # Origem e adaptações realizadas da AV2
├── evidencias/
│   ├── parte_a/                      # Inventário de host/daemon e ambiente
│   ├── parte_b/
│   │   └── namespaces.txt            # Saída real da comparação A x B
│   ├── parte_c/                      # Piloto e registros complementares, se coletados
│   └── parte_d/
│       └── mount_readonly.txt        # Leitura e negação de escrita
├── resultados/
│   └── parte_c/
│       ├── piloto_DATA/              # Validação preliminar, não entra na comparação oficial
│       └── oficial_DATA/             # Uma rodada oficial completa
│           ├── manifesto.txt
│           ├── C1_rep_1/ ... C1_rep_3/
│           ├── C2_rep_1/ ... C2_rep_3/
│           ├── resultados.csv
│           ├── resumo.md
│           └── grafico_tempo_c1_c2.svg
└── VIDEO.md                          # Link de vídeo, quando finalizado
```

**Observações:** algumas pastas ou documentos de entrega final podem ser adicionados posteriormente (relatório PDF, slides, diagrama, vídeo). Não é necessário criar arquivos fictícios para preencher a estrutura. Cada `C*_rep_*/` contém `registro.json`, `stdout.txt`, `stderr.txt` e `exit_code.txt`. **Não apagar tentativas com erro**.

## 3. Pré-requisitos e ambiente

- Linux com Docker Engine ativo e acesso autorizado ao daemon; Linux nativo, WSL2 ou VM são possíveis, mas deve-se identificar o **host real do daemon Docker**.
- Docker com **cgroup v2** e os controladores de CPU, memória e tarefas disponíveis.
- Python 3 no host, `bash`, `sudo`, `timeout` (GNU coreutils), `sha256sum` e acesso inicial para obter a imagem.
- Não são necessários pacotes Python adicionais, servidor de LLM, GPU ou rede dentro dos contêineres do experimento.

Verifique:

```bash
sudo systemctl status docker
sudo docker version
docker compose version
sudo docker info --format 'Cgroup={{.CgroupVersion}} Driver={{.CgroupDriver}}'
cat /sys/fs/cgroup/cgroup.controllers
```

O ambiente registrado na execução inicial da equipe utilizou Docker Engine **29.1.3**, cgroups **v2** e driver **systemd**, em Linux. Para reproduzir em outra máquina, **registre os valores daquela máquina**, sem copiá-los como se fossem uma nova observação.

### Imagem por digest

A imagem usada nos experimentos é fixada por digest:

```bash
export IMAGEM_LAB='python@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54'
sudo docker pull "$IMAGEM_LAB"
sudo docker image inspect --format '{{index .RepoDigests 0}}' "$IMAGEM_LAB"
```

O script `run_experimentos.sh` usa esse digest por padrão. Não substitua por uma tag móvel (`latest`) sem registrar explicitamente a mudança. `sudo docker` é utilizado para não exigir acesso ao grupo privilegiado `docker`.

## 4. Parte A — Inventário do ambiente

Execute na pasta `ATV_3/`:

```bash
mkdir -p evidencias/parte_a
{
  echo '===== DATA ====='; date -Is
  echo '===== SISTEMA E KERNEL ====='; uname -a; cat /etc/os-release
  echo '===== CPUs ====='; nproc; lscpu
  echo '===== MEMORIA ====='; free -h
  echo '===== DOCKER ====='; sudo docker version; docker compose version
  echo '===== CGROUP ====='
  sudo docker info --format 'Cgroup={{.CgroupVersion}} Driver={{.CgroupDriver}}'
  cat /sys/fs/cgroup/cgroup.controllers
  echo '===== DIGEST ====='
  sudo docker image inspect --format '{{index .RepoDigests 0}}' "$IMAGEM_LAB"
} | tee evidencias/parte_a/inventario_ambiente.txt
```

Inclua no relatório um diagrama de camadas: **hardware → sistema operacional/kernel do host do daemon (e VM intermediária, caso exista) → Docker Engine → contêineres**. Revise o inventário antes de publicá-lo; não inclua credenciais nem informações sigilosas.

## 5. Parte B — Namespaces

Dois contêineres independentes, mesma imagem e rede desligada:

```bash
sudo docker run -d --rm --name av3-ns-a --network none "$IMAGEM_LAB" sleep 3600
sudo docker run -d --rm --name av3-ns-b --network none "$IMAGEM_LAB" sleep 3600
```

Colete os handles reais:

```bash
mkdir -p evidencias/parte_b
{
  for nome in av3-ns-a av3-ns-b; do
    echo "===== CONTÊINER: $nome ====="
    sudo docker inspect --format 'PID no host do daemon={{.State.Pid}}' "$nome"
    echo 'Processo PID 1:'
    sudo docker exec "$nome" sh -c 'cat /proc/1/comm'
    for ns in pid mnt net; do
      echo "Namespace $ns:"
      sudo docker exec "$nome" readlink "/proc/1/ns/$ns"
    done
    echo
  done
} | tee evidencias/parte_b/namespaces.txt
```

Limpe **somente** os contêineres do laboratório:

```bash
sudo docker stop av3-ns-a av3-ns-b
sudo docker ps
```

**Como interpretar:** os dois contêineres podem ver seu próprio processo como PID 1, embora tenham PIDs diferentes no host do daemon. Handles diferentes de `pid`, `mnt` e `net` demonstram namespaces distintos. Isso **não** significa que cada contêiner tenha kernel próprio nem prova isolamento de todas as demais funcionalidades do SO.

### Registros observados na execução da equipe

| Recurso | Contêiner A | Contêiner B |
|---|---|---|
| PID no host do daemon | `39466` | `39524` |
| Processo interno PID 1 | `sleep` | `sleep` |
| PID namespace | `pid:[4026532892]` | `pid:[4026532964]` |
| Mount namespace | `mnt:[4026532880]` | `mnt:[4026532961]` |
| Network namespace | `net:[4026532894]` | `net:[4026532966]` |

Esses identificadores são **da execução registrada**; em outra execução eles serão diferentes.

## 6. Parte C — Limites de recursos via cgroups

### Condições experimentais

| Condição | Quota CPU | `memory.max` | `memory.swap.max` | `pids.max` | Repetições |
|---|---:|---:|---:|---:|---:|
| **C1** | `0.5` CPU | 256 MiB | `0` (sem swap adicional) | `64` | 3 |
| **C2** | `1.0` CPU | 256 MiB | `0` (sem swap adicional) | `64` | 3 |

O script executa uma carga **PBKDF2 sintética de trabalho fixo** (mesmo número de iterações e checksum), alternando `C1-1, C2-1, C1-2, C2-2, C1-3, C2-3`. Muda apenas a quota da CPU. As demais restrições e a imagem permanecem iguais. A carga é limitada a 60 s internamente e o comando tem limite externo de 90 s.

### 6.1. Verificar os scripts

```bash
python3 -m py_compile scripts/carga_cpu.py scripts/resumo.py
bash -n scripts/run_experimentos.sh
```

### 6.2. Piloto (não oficial)

```bash
MODO=piloto ITERACOES=1000000 bash scripts/run_experimentos.sh
```

Examine `resultados/parte_c/piloto_*/C1_rep_1/registro.json`. O piloto determina uma carga segura e verifica se os limites do cgroup foram efetivamente aplicados. **Somente ajuste o número de iterações antes das seis medições oficiais.**

### 6.3. Seis execuções oficiais

Depois de fixar o número de iterações no piloto:

```bash
ITERACOES=20000000 bash scripts/run_experimentos.sh
```

Na execução documentada da equipe, foi utilizado `ITERACOES=20000000` em todas as seis repetições. A execução escreve uma nova pasta `resultados/parte_c/oficial_DATA/` sem substituir rodadas anteriores.

O script configura Docker com:

```text
--network none --cpus 0.5|1.0 --memory 256m --memory-swap 256m
--pids-limit 64 --read-only --cap-drop ALL
--security-opt no-new-privileges --user 65534:65534
```

O script executa a carga a partir de `scripts/` montado como somente leitura, não precisa abrir portas nem montar diretórios do host além dessa pasta.

### 6.4. Conferência dos resultados

O arquivo `registro.json` de cada repetição contém:

- `status`, `docker_exit_code`, `condicao`, `repeticao`, `iteracoes` e `checksum_sha256`;
- `tempo_total_s` (tempo decorrido), `tempo_cpu_s` (tempo de CPU) e `trabalho_por_segundo` (**iterações por segundo, não tokens/s**);
- `cgroup.cpu.max`, `cgroup.memory.max`, `cgroup.memory.swap.max`, `cgroup.pids.max`, `limites_confirmados`;
- `cpu_stat_delta.usage_usec`, `nr_throttled` e `throttled_usec`, quando disponíveis;
- `memory.current_bytes`, `memory.peak_bytes` e RSS/HWM do processo.

Para gerar novamente o resumo de uma execução específica:

```bash
python3 scripts/resumo.py resultados/parte_c/oficial_NOME_DA_EXECUCAO
```

Quando a rodada é válida, aparecem `resultados.csv`, `resumo.md` e `grafico_tempo_c1_c2.svg`. O gráfico apresenta **mediana e intervalo mínimo–máximo** do tempo decorrido; é necessário preservar também os JSONs brutos, `stdout.txt`, `stderr.txt` e códigos de saída.

### 6.5. Resultado observado na execução de 07/11/2026

Os valores abaixo são provenientes das **execuções reais informadas pela equipe**, não são valores esperados para toda máquina:

| Repetição | C1 · 0,5 CPU (s) | C2 · 1,0 CPU (s) |
|---|---:|---:|
| 1 | 5,183216 | 2,649953 |
| 2 | 5,200954 | 2,570914 |
| 3 | 5,327714 | 2,739591 |
| **Mediana** | **5,200954** | **2,649953** |

O trabalho fixo produziu o mesmo SHA-256 nas seis rodadas: `6140a0e6e3548422e6e8c59c884ffe5abe1255848c5af557e0fe934a3afc66d7`.

| Indicador | C1 | C2 |
|---|---|---|
| `cpu.max` | `50000 100000` | `100000 100000` |
| `nr_throttled` por repetição | 52, 52, 53 | 2, 5, 3 |
| `throttled_usec` por repetição | 2600084, 2599104, 2649846 | 1099, 3572, 630 |

Interpretação: a mediana de tempo decorrido foi ~**1,96×** maior em C1. Ambas as condições consumiram aproximadamente 2,6 s de tempo de CPU do processo, mas a restrição de 0,5 CPU causou mais períodos de throttling. A quota é uma restrição de tempo agregado de CPU por período — **não é afinidade nem reserva física de um núcleo**. O ruído do host pode alterar os números em outras execuções. `throttled_usec` é um contador do cgroup; não deve ser simplesmente somado ao wall time da aplicação.

## 7. Parte D — Montagem somente leitura

O teste usa **somente um diretório sintético** e um usuário não root. Não monta `/`, `$HOME` inteiro ou o socket do Docker.

```bash
mkdir -p dados_demo evidencias/parte_d
printf 'Documento sintetico da AV3\n' > dados_demo/texto.txt

sudo docker run --rm \
  --name av3-mount-ro \
  --network none \
  --user 65534:65534 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --read-only \
  --mount "type=bind,src=$PWD/dados_demo,dst=/dados,readonly" \
  "$IMAGEM_LAB" \
  sh -c '
    echo "===== TESTE DE LEITURA ====="
    cat /dados/texto.txt || exit 1
    echo "===== TESTE DE ESCRITA ====="
    if (printf "tentativa\n" > /dados/tentativa.txt); then
      echo "ERRO: escrita permitida"
      exit 1
    else
      echo "SUCESSO: escrita negada"
    fi
  ' 2>&1 | tee evidencias/parte_d/mount_readonly.txt
```

**Resultado observado:** a leitura exibiu `Documento sintetico da AV3` e a tentativa de criar `/dados/tentativa.txt` retornou `Read-only file system`, seguida de `SUCESSO: escrita negada`.

Interpretação: uma montagem read-only impede a escrita nesse caminho, e as demais opções reduzem os privilégios do contêiner. **Isso não prova isolamento absoluto** nem substitui políticas de segurança do kernel e permissões de acesso.

## 8. Conceitos e limitações importantes

- **Namespaces** isolam visões de recursos (PID, mount, network). Dois contêineres compartilham o kernel do host do daemon, não possuem dois kernels próprios.
- **Cgroups** controlam/contabilizam recursos; `cpu.max` é quota por período, enquanto `memory.max` e `pids.max` definem outros limites.
- **Wall time** é o tempo decorrido de relógio; **CPU time** é tempo efetivamente utilizado pelo processo.
- **Throttling** indica períodos em que o consumo excedeu a quota do cgroup. Não inferir uma causa apenas de uma amostra.
- **RSS do processo**, `memory.current` e `memory.peak` são métricas diferentes e não devem ser chamadas indistintamente de “RAM média”.
- A carga é **CPU sintética (PBKDF2)**, sem inferência neural, GPU, rede ou uso distribuído; resultados não são benchmarks de modelos de IA.
- Não executar cargas deliberadamente destrutivas, fork bombs, testes de OOM ou alterações do host sem autorização. Preservar falhas e documentar limitações de execução.

## 9. Relação com a AV2 e uso de IA

A implementação reaproveita **ideias** da AV2: carga PBKDF2 para trabalho computacional, medição de tempo, CSV/JSON e documentação das repetições. A AV3 acrescenta isolamento Docker, confirmação dos cgroups, estatísticas de throttling e experimentos de namespaces/mount. Consulte `docs/REUSO_AV2_AV3.md` para o detalhamento.

**Declaração de IA a completar pelo grupo:** registrar ferramenta/modelo utilizados, finalidades, até três prompts relevantes, sugestões adotadas/corrigidas/rejeitadas, como foram verificadas e adaptações dos scripts. As saídas de IA **não são evidências do kernel**: somente os logs efetivamente coletados são resultados experimentais.

## 10. Entrega e reprodução

O repositório deve conter: códigos/configuração, README, inventário/diagrama, evidências reais das Partes B e D, seis registros brutos da Parte C, CSV, gráfico, relatório PDF, apresentação, tabela de contribuições, declaração crítica de IA e `VIDEO.md` (ou `video.txt`) com URL do vídeo. Inserir também o endereço do vídeo no README e no relatório final. Revisar os arquivos antes do push para excluir segredos e dados pessoais.

**Vídeo da equipe:** *inserir URL quando estiver disponível*.

**Reprodução rápida:** clone o repositório, entre em `ATV_3/`, obtenha a imagem por digest, execute as Partes A, B e D, faça o piloto da Parte C e, por último, as seis rodadas oficiais. Um experimento só pode ser considerado reproduzido após conferir os limites, checksums, logs e resultados gerados na nova máquina.

---

**Referências técnicas:** enunciado oficial da Atividade 3 de Sistemas Operacionais (UFS 2026.2); `namespaces(7)` (Linux man-pages); documentação de cgroup v2 do kernel Linux; Docker — *Resource constraints*.
