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
| Rafael de Jesus Santos | 202300114489 | Função na atividade |
| Luan Feitosa Lima Sátiro  | 202300061714 | Função na atividade |
| Beathriz Laurent Carlos Muniz | 201900050850 | Testes |

## 1. Instalação e Execução

O projeto foi executado no Ubuntu via WSL2 e Linux Nativo. 

Passos para execução via WSL2

**Passo 1: Instalação do Ollama e do Modelo**
```
curl -fsSL [https://ollama.com/install.sh](https://ollama.com/install.sh) | sh ollama pull qwen2.5:1.5b
```
**Passo 2: Execução do Open WebUI (Docker)**
```
docker compose up -d ou docker compose up --build
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
