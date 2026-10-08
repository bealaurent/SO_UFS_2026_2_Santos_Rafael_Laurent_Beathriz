# Memória, armazenamento, sincronização e desempenho de aplicações de IA generativa

**Disciplina:** Sistemas Operacionais - 2026.2 (Universidade Federal de Sergipe)


## Vídeo da Atividade

## Equipe
| Nome | Matrícula | Contribuição na Atividade |
| :--- | :--- | :--- |
| Evelyn Hilthegarden Santana de Jesus | 202300061572 | Complemento e formatação de relatório |
| Samyr Teles Sales Silva | 202300061830 | Criação da apresentação |
| Matheus de Oliveira Lima  | 202100012062 | Criação do relatório |
| Rafael de Jesus Santos | 202300114489 | Execução de Testes |
| Luan Feitosa Lima Sátiro  | 202300061714 | Reprodução & automatização de testes |
| Beathriz Laurent Carlos Muniz | 201900050850 | Execução de Testes |

## Estrutura do Repositório

```text
SO_UFS_2026_2_Santos_Rafael_Laurent_Beathriz/
├── ATV_1                                     # Todo o conteúdo da avaliação 1
├── .gitignore
├── README.md                                 # Documentação principal
└── VIDEO.md                                  # Link da apresentação em vídeo
```

## 1. Instalação e Execução

O projeto foi executado no Ubuntu via WSL2 e Linux Nativo. 

### Pré-requisitos
Antes de iniciar, certifique-se de ter instalado em sua máquina:
* [WSL2 (Windows Subsystem for Linux)](https://learn.microsoft.com/pt-br/windows/wsl/install) (caso esteja executando em um ambiente windows)
* [Docker Desktop](https://www.docker.com/products/docker-desktop/)

### Passos para execução via WSL2 e Linux Nativo

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

### - Ambiente WSL2 e Linux Nativo

Para reproduzir os dados coletados neste trabalho, utilize duas instâncias do terminal WSL ou Linux.

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



Os procedimentos de monitoramento e coleta de métricas são os mesmos utilizados no ambiente WSL2 e Linux Nativo, permitindo comparar os resultados obtidos nos dois ambientes.
