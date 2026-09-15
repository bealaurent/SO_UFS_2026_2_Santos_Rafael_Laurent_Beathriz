# Inferência Local com Ollama e Open WebUI

**Disciplina:** Sistemas Operacionais - 2026.2 (Universidade Federal de Sergipe)

**Trilha Selecionada:** Trilha A (Chat Local: Ollama + Open WebUI)

**Modelo Selecionado:** Qwen2.5-1.5B-Instruct

## Vídeo da Atividade


## Equipe
| Nome | Matrícula | Contribuição na Atividade |
| :--- | :--- | :--- |
| Evelyn Hilthegarden Santana de Jesus | 202300061572 | Função na atividade |
| Samyr Teles Sales Silva | 202300061830 | Função na atividade |
| Matheus de Oliveira Lima  | 202100012062 | Função na atividade |
| Rafael de Jesus Santos | 202300114489 | Execução de Testes |
| Luan Feitosa Lima Sátiro  | 202300061714 | Reprodução & automatização de testes |
| Beathriz Laurent Carlos Muniz | 201900050850 | Execução de Testes |

## Estrutura do Repositório

```text
SO_UFS_2026_2_Santos_Rafael_Laurent_Beathriz/
├── docs/                                     # Documentações e relatórios
│   ├── Relatório.pdf                         # Relatório das execuções
│   └── Slides.pdf                            # Slides Apresentação
├── logs/                                     # Saídas de execução e rastreamentos
│   └── strace-final-SO_WSL.txt               # Log
├── scripts/                                  # Automações e orquestração de containers
│   ├── docker-compose.yml                    # Arquivo de configuração do docker
│   ├── testador_automatico_readme.txt        # Guia para rodar script
│   └── testador_automatico.py                # Script para automatizar testes
├── .gitignore
├── README.md                                 # Documentação principal
└── VIDEO.md                                  # Link da apresentação em vídeo
```

## 1. Instalação e Execução

O projeto foi executado no Ubuntu via WSL2 e Linux Nativo. 

### Pré-requisitos
Antes de iniciar, certifique-se de ter instalado em sua máquina:
* [WSL2 (Windows Subsystem for Linux)](https://learn.microsoft.com/pt-br/windows/wsl/install)
* [Docker Desktop](https://www.docker.com/products/docker-desktop/)

### Passos para execução via WSL2

**Passo 1: Instalação do Ollama e do Modelo no terminal WSL**
```
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:1.5b
```

**Passo 2: Execução do Open WebUI (Docker) na IDE**
```
docker compose up -d
```

## 2. Reprodução dos Experimentos (Coleta de Métricas)

### - Ambiente WSL2

Para reproduzir os dados coletados neste trabalho, utilize duas instâncias do terminal WSL.

**Terminal 1 (Monitoramento de CPU/RAM e Threads):**
```
htop
```
**Terminal 2 (Monitoramento de Chamadas de Sistema - strace):**
1. Descubra o PID do Ollama:
```
ps -eLf | grep ollama
```
2. Conecte o strace ao processo principal:
```
sudo strace -f -c -p PID_AQUI -o logs/strace-resumo.txt
```

Enquanto os monitores rodam, envie os prompts de teste via Open WebUI. Interrompa o strace (Ctrl+C) após a IA finalizar a resposta para gerar os logs.

### - Ambiente Linux Nativo

## 1. Instalação e Execução

O projeto foi executado em um ambiente Linux nativo.

### Pré-requisitos

Antes de iniciar, certifique-se de ter instalado em sua máquina:

* [Ollama](https://ollama.com/)
* [Docker Engine](https://docs.docker.com/engine/install/) ou Docker Desktop
* Docker Compose

### Passos para execução no Linux Nativo

**Passo 1: Instalação do Ollama e do Modelo no terminal**

```
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:1.5b
```

**Passo 2: Execução do Open WebUI**

No diretório do projeto, execute:

```
docker compose up -d
```

Após a inicialização dos containers, o Open WebUI estará disponível para envio dos prompts e realização dos experimentos.

## 2. Reprodução dos Experimentos (Coleta de Métricas)

Para reproduzir os dados coletados neste trabalho, utilize duas instâncias do terminal Linux.

**Terminal 1: Monitoramento de CPU/RAM e Threads**

```
htop
```

**Terminal 2: Monitoramento de Chamadas de Sistema — strace**

1. Descubra o PID do Ollama:

```
ps -eLf | grep ollama
```

2. Conecte o strace ao processo principal:

```
sudo strace -f -c -p PID_AQUI -o logs/strace-resumo.txt
```

Enquanto os monitores rodam, envie os prompts de teste via Open WebUI. Interrompa o strace (`Ctrl+C`) após a IA finalizar a resposta para gerar os logs.

Os procedimentos de monitoramento e coleta de métricas são os mesmos utilizados no ambiente WSL2, permitindo comparar os resultados obtidos nos dois ambientes.
