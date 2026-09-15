Script de benchmark para uma aplicação Qwen rodando via Ollama + WebUI
Dockerizada (ex.: Open WebUI). Coleta informações de hardware/setup do
computador do usuário e roda experimentos comparativos de carga (requisições
simultâneas / conversas paralelas), gerando um relatório em Markdown no
mesmo formato usado em "Dados_Brutos_dos_testes.pdf":

  1. Informações sobre o hardware (SO, kernel, CPU, GPU, armazenamento, RAM)
  2. Instalação e execução inicial (tempo de pull da imagem, tempo de
     download do modelo, tempo de inicialização)
  3. Processos e portas em uso
  4. Logs, erros e avisos relevantes (ex.: incompatibilidade de GPU)
  5. Resumo de chamadas de sistema (strace -c), quando disponível
  6. Experimentos comparativos (Config 1, 2, 3, ...) com latência,
     tokens/s, uso de CPU/memória/GPU
  7. Métricas mínimas

REQUISITOS
----------
  - Python 3.8+
  - pip install requests psutil   (psutil é opcional, mas recomendado)
  - Docker instalado e a aplicação já rodando (ex.: `docker compose up -d`)
    com um container do Ollama expondo a API (padrão: localhost:11434)
  - Opcional: nvidia-smi (GPU NVIDIA) ou rocm-smi (GPU AMD) no PATH para
    métricas de GPU. Em WSL2 com GPU AMD isso normalmente não funciona
    (mesma limitação relatada no PDF de referência) — o script detecta
    isso e registra a limitação no relatório em vez de falhar.
  - Opcional: `strace` instalado e permissão de ptrace (CAP_SYS_PTRACE)
    para o resumo de syscalls. Sem isso, essa seção é pulada com uma nota.

EXEMPLO DE USO
---------------
  python3 benchmark_qwen_webui.py \\
      --ollama-url http://localhost:11434 \\
      --webui-url http://localhost:3000 \\
      --container ollama \\
      --model qwen2.5:1.5b \\
      --configs 1:1 3:3 5:5 \\
      --output relatorio_testes.md

Cada item de --configs é "concorrencia:conversas_paralelas", por exemplo
"3:3" dispara 3 requisições simultâneas representando 3 conversas paralelas.

O código deve ser executado na ambiente dockerizado, na mesma pasta.