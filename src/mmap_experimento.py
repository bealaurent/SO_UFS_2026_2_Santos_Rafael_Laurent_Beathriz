import time
import mmap
import os

def testar_leitura_convencional(caminho_arquivo):
    inicio = time.time()
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        conteudo = f.read()
        tamanho = len(conteudo)
    duracao = time.time() - inicio
    print(f"[Convencional] Lidos {tamanho} caracteres em {duracao:.4f} segundos")

def testar_leitura_mmap(caminho_arquivo):
    inicio = time.time()
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            conteudo = mm.read()
            tamanho = len(conteudo)
    duracao = time.time() - inicio
    print(f"[MMAP] Lidos {tamanho} caracteres em {duracao:.4f} segundos")

if __name__ == "__main__":
    caminho = "dados/corpus_simulado.txt"
    if not os.path.exists(caminho):
        with open(caminho, "w") as f:
            f.write("Trecho de contexto simulado para IA. " * 1000000)
            
    print("--- Iniciando Experimentos de E/S ---")
    testar_leitura_convencional(caminho)
    testar_leitura_mmap(caminho)