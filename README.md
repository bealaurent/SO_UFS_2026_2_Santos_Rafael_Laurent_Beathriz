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

## 1. Instalação e Execução (Ambiente WSL2)

O projeto foi executado no Ubuntu via WSL2. 

**Passo 1: Instalação do Ollama e do Modelo**
```bash
**Passo 1: Instalação do Ollama e do Modelo**
```bash
curl -fsSL [https://ollama.com/install.sh](https://ollama.com/install.sh) | sh ollama pull qwen2.5:1.5b
```
**Passo 2: Execução do Open WebUI (Docker)**
```
docker compose up -d
```

## 2. Reprodução dos Experimentos (Coleta de Métricas)
