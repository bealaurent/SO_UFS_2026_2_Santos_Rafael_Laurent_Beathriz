#!/usr/bin/env python3
"""Teste de fumaça da API Parte B. Executar enquanto o servidor está ativo."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from urllib.request import Request, urlopen


def api(base, caminho, corpo=None):
    req = Request(base + caminho,
                  data=json.dumps(corpo, ensure_ascii=False).encode("utf-8") if corpo is not None else None,
                  headers={"Content-Type": "application/json"} if corpo is not None else {},
                  method="POST" if corpo is not None else "GET")
    with urlopen(req, timeout=35) as resp:
        return json.load(resp)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8765")
    p.add_argument("--saida", default="logs/teste_parte_b.json")
    args = p.parse_args()
    consultas = [
        "O que é memória virtual e paginação?",
        "O que é memória virtual e paginação?",  # cache hit em condição sequencial
        "Como funciona um cache de páginas?",
        "O que são produtores e consumidores?",
    ]
    resultados = []
    print("1. Saúde:", api(args.url, "/saude"))
    for pergunta in consultas:
        resp = api(args.url, "/consultar", {"consulta": pergunta, "top_k": 2})
        resultados.append(resp)
        print(f"2. Consulta: cache={resp['cache']}; trechos={len(resp['trechos'])}; "
              f"tempo={resp['tempo_total_s']}s; consumidor={resp['consumidor']}")
    # Solicitações concorrentes demonstram a fila/consumidores, mas não são ainda C3 validado.
    concorrentes = ["Explique RAG e embeddings", "Como a swap afeta a RAM?",
                    "Para que serve mmap?", "Como funciona sincronização por mutex?"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        paralelos = list(pool.map(lambda q: api(args.url, "/consultar", {"consulta": q}), concorrentes))
    resultados.extend(paralelos)
    print("3. Consultas paralelas:", len(paralelos))
    estado = api(args.url, "/status")
    print("4. Estado do servidor:", json.dumps(estado, ensure_ascii=False, indent=2))
    destino = Path(args.saida)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"consultas": resultados, "estado": estado},
                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert resultados[0]["cache"] == "miss"
    assert resultados[1]["cache"] == "hit"
    assert estado["armazenamento"]["documentos"] >= 1
    print("Teste B concluído. Evidência salva em", destino)


if __name__ == "__main__":
    main()
