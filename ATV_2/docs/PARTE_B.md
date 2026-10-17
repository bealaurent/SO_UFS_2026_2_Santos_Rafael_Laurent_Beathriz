# AV2 — Parte B: GenResearch-Servidor (implementação incremental)

> Este complemento **não altera** `src/main.py` nem `src/mmap_experimento.py` (C1/C2). Implementação educacional para CPU, com vetores de hashing e resposta **simulada**, sem LLM/Ollama. Use apenas corpus público, sintético ou anonimizado.

## 1. Executar no Linux nativo

Na raiz do repositório:

```bash
python3 --version
python3 -m unittest discover -s tests -v
python3 src/genresearch_servidor.py preparar
python3 src/genresearch_servidor.py servir --porta 8765 --trabalhadores 2 --fila 8 --cache 8
```

Em **outro terminal**, na mesma raiz:

```bash
curl -s http://127.0.0.1:8765/saude
python3 scripts/testar_parte_b.py
curl -s http://127.0.0.1:8765/status | python3 -m json.tool
```

Encerre o primeiro terminal com `Ctrl+C` (o servidor salva o evento de encerramento).

Se `curl` não estiver instalado, o script `testar_parte_b.py` já executa as consultas HTTP com bibliotecas do Python.

## 2. Ingestão de documentos e consulta manual

Os quatro textos sintéticos estão em `dados/documentos_demo/*.txt`. O comando `preparar` grava o corpus, os metadados e os vetores em `dados/indice_parte_b.sqlite3`, com seus arquivos auxiliares WAL/SHM quando presentes.

```bash
curl -s -X POST http://127.0.0.1:8765/consultar \
  -H 'Content-Type: application/json' \
  -d '{"consulta":"Explique a memória virtual e a paginação", "top_k":3, "limite_contexto":800}' \
  | python3 -m json.tool
```

Ingestão via HTTP de um novo documento público/sintético:

```bash
curl -s -X POST http://127.0.0.1:8765/documentos \
  -H 'Content-Type: application/json' \
  -d '{"nome":"exemplo_http.txt", "conteudo":"O sistema operacional organiza processos e memória virtual com paginação."}' \
  | python3 -m json.tool
```

Um `POST /documentos` com mesmo nome substitui o documento e invalida as respostas em cache. Há limite de 2 MB por documento, evitando ingestão acidental de arquivos muito grandes.

## 3. Evidências para o relatório da Parte B

- `dados/indice_parte_b.sqlite3`: armazenamento persistente de documentos, trechos, metadados e vetores simulados.
- `logs/parte_b.jsonl`: um evento JSON por linha (ingestão, produção, consumo, recuperação, cache_hit, cache_miss, cache_substituicao, geracao_simulada, falha, encerramento). O `logging.FileHandler` sincroniza as escritas entre threads.
- `logs/teste_parte_b.json`: respostas, tempos, documentos recuperados e estado da fila/cache.
- `GET /status`: corpus_bytes, indice_bytes, quantidade de documentos e trechos, tamanho médio *amostrado* e máximo de fila, espera média, produtores, consumidores, requisições, hits, misses e substituições.
- `GET /saude`: verificação de servidor ativo.

## 4. Correspondência com a Parte B

| Exigência | Implementação |
|---|---|
| Ingestão | `preparar` e `POST /documentos` + `fragmentar` + `embedding_simulado` (hash determinístico, não embedding semântico real) |
| Armazenamento | SQLite (`documentos`, `trechos`), vetores em JSON, tamanhos reportados |
| Fila | `queue.Queue(maxsize=...)`, requisições HTTP como produtores e threads consumidoras |
| Recuperação | similaridade cosseno de vetores normalizados, `top_k`, tamanho máximo de contexto |
| Resposta | extrato de texto do contexto + trabalho CPU com PBKDF2 (simulação, **não** geração de IA) |
| Cache | `OrderedDict` LRU protegido por `threading.Lock`, acertos/erros/substituições; economia é **estimativa** do tempo original de processamento |
| Logs | `logging.FileHandler` (escrita sincronizada), eventos estruturados em JSONL |

## 5. Observações e limitações

- A recuperação baseada em **hashing de palavras** serve para demonstrar fluxo de RAG sem modelo de embeddings; similaridade do vetor não é qualidade semântica validada.
- A leitura de todos os vetores armazenados a cada consulta é aceitável para o corpus didático pequeno, mas **não escala** para índices grandes. Um banco vetorial ou índice apropriado seria necessário.
- O servidor escuta **somente em 127.0.0.1** e não possui autenticação: **não exponha em rede pública**.
- Uma falta simultânea para a mesma chave pode computar duas respostas antes da entrada ser escrita no cache; o estado LRU é protegido, porém não existe mecanismo single-flight. Isso pode servir à posterior discussão sobre sincronização.
- A média do tamanho da fila é uma **média das observações no ingresso**, não média ponderada por tempo. A economia do cache é estimada pelo custo da execução original, não uma medida contrafactual exata.
- Este ensaio é validação funcional da Parte B. **Não substitui C1-C6**, as três repetições exigidas por configuração, experimentos de corrida/falha controlada (Parte D) nem medição de faltas de página, RSS e E/S (Parte E).
- Para demonstração reproduzível, apague somente os arquivos de teste gerados de `logs/` e `dados/indice_parte_b.sqlite3*` (nunca apague os documentos-fonte) ou utilize caminhos `--banco` / `--log` separados.

## 6. Contribuição e revisão de código

Este complemento foi preparado com auxílio de ChatGPT em 16/10/2026 como ponto de partida da Parte B. A equipe deve revisar, executar, validar, adaptar e atribuir o uso de ferramenta de IA no repositório/relatório conforme as regras de autoria do trabalho. Não apresentar testes desta demonstração como resultados experimentais da equipe: os resultados usados na entrega devem ser coletados e registrados no ambiente de execução declarado.
