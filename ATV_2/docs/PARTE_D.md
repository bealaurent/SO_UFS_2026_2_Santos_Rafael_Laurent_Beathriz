# AV2 — Parte D: sincronização obrigatória

## Objetivo e relação com o servidor da Parte B

A Parte D (opção 2) exige demonstrar acesso concorrente a um recurso compartilhado, uma falha controlada de sincronização e sua correção. O ensaio **reutiliza a classe `CacheLRU` original** de `src/genresearch_servidor.py` sem alterar o servidor HTTP nem os dados da Parte C.

**Nuance técnica:** o cache original usa `threading.Lock` em `buscar()` e `guardar()`, portanto a estrutura interna do dicionário é protegida. O *ciclo composto* `buscar -> recuperar/gerar -> guardar` não é uma operação atômica. Duas ou mais threads podem observar `miss` para a mesma chave e executar trabalho duplicado. Trata-se de *cache stampede* / duplicação de processamento, **não de corrupção do dicionário**.

Este experimento é **isolado e instrumentado**. Não modifica o servidor real nem tenta causar deadlock.

### D1 — Sem lock da transação (falha reproduzida)

Quatro threads recebem a mesma consulta com cache inicialmente vazio. Uma barreira proposital após a leitura garante que todas vejam `miss` antes de qualquer gravação. Cada uma simula recuperação/geração e grava a mesma chave: quatro cálculos da mesma resposta, três redundantes, uma entrada final. A barreira **força intencionalmente um entrelaçamento de execução possível**, para produzir evidência estável; ela não demonstra frequência natural da falha em cargas reais.

### D2 — Com lock envolvendo toda a transação

As mesmas quatro threads começam juntas. Um `threading.Lock` externo protege toda a sequência `buscar -> calcular -> guardar`. A primeira executa o cálculo e preenche o cache; as demais encontram a resposta e não repetem o cálculo. O lock global é didático, porém serializa também operações independentes. Num sistema de produção, *locks por chave* ou deduplicação de requisições em andamento (*single-flight*) seriam alternativas mais escaláveis.

O atraso programado simula espera por E/S/processamento, e `hashlib.pbkdf2_hmac` simula custo computacional. **Não há LLM**, e o algoritmo não deve ser apresentado como inferência real.

## Instalação

Extraia o ZIP na raiz do projeto que já contém:

```text
src/genresearch_servidor.py
scripts/experimentos_c.py
```

O complemento adiciona:

```text
scripts/experimentos_d.py
tests/test_parte_d.py
docs/PARTE_D.md
```

Requer Python 3 com biblioteca padrão e utilitário Linux `ps` para o retrato dos threads. Não necessita `pip install`, Docker, Ollama ou servidor HTTP ativo. Não apaga nem sobrescreve resultados anteriores.

## Executar

1. Na raiz do projeto, teste os novos arquivos:

```bash
python3 -m unittest discover -s tests -p 'test_parte_d.py' -v
```

2. Experimento oficial com três repetições:

```bash
mkdir -p evidencias/parte_d
python3 scripts/experimentos_d.py --repeticoes 3 --trabalhadores 4 --espera-ms 30 \
  | tee evidencias/parte_d/execucao_D1_D2.txt
```

O console deve registrar, por repetição:

```text
[D1] ... geracoes=4, duplicadas=3, hits=0, misses=4, respostas=4, falhas=0
[D2] ... geracoes=1, duplicadas=0, hits=3, misses=1, respostas=4, falhas=0
```

Esses números são **critérios de validação esperados**, não medições efetivas na máquina do usuário até que os comandos sejam executados lá.

## Evidências

Cada execução cria automaticamente `resultados/parte_d/execucao_AAAAMMDD_HHMMSS_microssegundos_PID/`:

- `manifesto.json`: data UTC, parâmetros, versões, commit e hashes do código
- `resultados.csv` / `resultados.json`: seis observações (3 D1 e 3 D2)
- `D1_rep_X/resumo.json` e `D2_rep_X/resumo.json`: contagens, cache, latência e erros
- `D1_rep_X/respostas.json`, `D2_rep_X/respostas.json`: resposta, acerto/erro, thread e latência individuais
- `D1_rep_X/eventos.jsonl`, `D2_rep_X/eventos.jsonl`: sequência dos eventos com thread, TID e carimbo UTC, com escrita protegida pelo `logging`
- `D1_rep_X/ps_threads.txt`, `D2_rep_X/ps_threads.txt`: saída de `ps -T` com as threads presentes antes da liberação do sinal de início

Para inspecionar a execução mais recente, **não use só a ordenação lexical se outras pastas forem criadas depois**. Prefira o caminho impresso pelo script. Exemplo:

```bash
DIR=$(find resultados/parte_d -maxdepth 1 -type d -name 'execucao_*' | sort | tail -n 1)
cat "$DIR/resultados.csv"
cat "$DIR/D1_rep_1/resumo.json"
cat "$DIR/D2_rep_1/resumo.json"
cat "$DIR/D1_rep_1/ps_threads.txt"
cat "$DIR/D1_rep_1/eventos.jsonl"
```

As medições de tempo de D1 e D2 **não são diretamente comparáveis como benchmark de desempenho**, pois D1 introduz uma barreira após o `miss` para controlar o entrelaçamento. A comparação pretendida é de **correção, trabalho duplicado, hits e misses**. Documente o custo e a limitação do lock global.

### Observação de exigências complementares

- A Parte D prova uma forma de duplicação de processamento por acesso concorrente. Não representa perda de atualização nem corrupção do cache.
- C6 (entrada inválida / arquivo inexistente) é outra falha controlada, **não substitui** este teste de sincronização.
- A Parte E e a documentação de processos, chamadas de sistema, métricas e entrega final devem ser verificadas separadamente.
