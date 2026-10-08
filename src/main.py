import sys
import platform
import psutil
import os
import time

from mmap_experimento import testar_leitura_convencional, testar_leitura_mmap

def imprimir_informacoes_sistema():
    print("="*50)
    print("Observação do Ambiente (Testes C1 e C2)")
    print("="*50)
    print(f"Sistema Operativo: {platform.system()} {platform.release()}")
    print(f"Processador: {platform.processor()}")
    
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    
    print(f"RAM Total: {mem.total / (1024**3):.2f} GB")
    print(f"RAM Disponível: {mem.available / (1024**3):.2f} GB")
    print(f"Swap Total: {swap.total / (1024**3):.2f} GB")
    print("="*50)

def monitorar_memoria_processo():
    processo = psutil.Process(os.getpid())
    memoria = processo.memory_info()
    print(f"[Métricas] RAM (RSS): {memoria.rss / 1024 / 1024:.2f} MB | Virtual (VSZ): {memoria.vms / 1024 / 1024:.2f} MB")

def main():
    print("Iniciando Experimentos C1 e C2 (Convencional vs mmap)...\n")
    
    imprimir_informacoes_sistema()
    time.sleep(1)

    print("\n" + "="*50)
    print("PARTE C - Experimentos de E/S")
    print("="*50)
    
    caminho_dados = "dados/corpus_simulado.txt"
    os.makedirs("dados", exist_ok=True)
    
    if not os.path.exists(caminho_dados):
        print("A gerar corpus de teste (isto pode demorar alguns segundos)...")
        with open(caminho_dados, "w", encoding="utf-8") as f:
            f.write("Trecho de contexto simulado para IA. " * 500000)
            
    print("Estado inicial da memória:")
    monitorar_memoria_processo()
    
    print("\n--- [C1] Executando leitura convencional ---")
    testar_leitura_convencional(caminho_dados)
    monitorar_memoria_processo()
    
    print("\n--- [C2] Executando leitura por mapeamento de memória ---")
    testar_leitura_mmap(caminho_dados)
    monitorar_memoria_processo()
    
    print("\n[!] Experimentos C1 e C2 finalizados com sucesso!")

if __name__ == '__main__':
    main()