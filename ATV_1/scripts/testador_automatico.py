#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import platform
import shutil
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import psutil
except ImportError:  # pragma: no cover - opcional
    psutil = None

try:
    import requests
except ImportError:  # pragma: no cover
    print("ERRO: este script requer a biblioteca 'requests'. Instale com:")
    print("  pip install requests psutil")
    sys.exit(1)


# --------------------------------------------------------------------------
# Utilidades básicas
# --------------------------------------------------------------------------

def run(cmd: list[str] | str, timeout: int = 15, shell: bool = False) -> tuple[int, str, str]:
    """Executa um comando e retorna (returncode, stdout, stderr).
    Nunca lança exceção: falhas viram (returncode != 0, "", mensagem)."""
    try:
        proc = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"comando não encontrado: {cmd}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout ao executar: {cmd}"
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)


def which(tool: str) -> bool:
    return shutil.which(tool) is not None


NOTES: list[str] = []  # avisos/erros coletados ao longo da execução


def note(msg: str) -> None:
    NOTES.append(msg)
    print(f"[nota] {msg}")


# --------------------------------------------------------------------------
# 1. Coleta de informações de hardware / setup
# --------------------------------------------------------------------------

def collect_hardware_info() -> dict[str, Any]:
    info: dict[str, Any] = {}

    # SO / kernel
    rc, out, err = run(["uname", "-a"])
    info["uname"] = out if rc == 0 else platform.platform()
    info["so"] = platform.system()

    # CPU
    rc, lscpu_out, _ = run(["lscpu"])
    info["lscpu"] = lscpu_out
    if psutil:
        info["cpu_logical"] = psutil.cpu_count(logical=True)
        info["cpu_physical"] = psutil.cpu_count(logical=False)
    info["cpu_name"] = platform.processor() or _extract_lscpu_field(lscpu_out, "Model name")

    # GPU — tenta NVIDIA, depois AMD (rocm-smi), depois lspci genérico
    gpu_name = None
    gpu_backend = None
    if which("nvidia-smi"):
        rc, out, _ = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
        if rc == 0 and out:
            gpu_name = out
            gpu_backend = "nvidia-smi"
    if gpu_name is None and which("rocm-smi"):
        rc, out, _ = run(["rocm-smi", "--showproductname"])
        if rc == 0 and out:
            gpu_name = out
            gpu_backend = "rocm-smi"
    if gpu_name is None:
        rc, out, _ = run("lspci | grep -iE 'vga|3d|display'", shell=True)
        if rc == 0 and out:
            gpu_name = out
            gpu_backend = "lspci (sem driver dedicado detectado)"
            note(
                "Não foi possível consultar métricas de GPU via nvidia-smi/rocm-smi. "
                "Isso costuma indicar incompatibilidade de driver dentro do WSL2/container "
                "(mesmo comportamento relatado no teste de referência com GPU AMD)."
            )
    info["gpu_name"] = gpu_name or "não detectada"
    info["gpu_backend"] = gpu_backend

    # Armazenamento
    rc, out, _ = run(["df", "-h", "/"])
    info["df"] = out

    # Memória
    rc, out, _ = run(["free", "-h"])
    if rc == 0 and out:
        info["memoria"] = out
    elif psutil:
        vm = psutil.virtual_memory()
        info["memoria"] = f"total={vm.total / 1e9:.1f}GB disponível={vm.available / 1e9:.1f}GB"
    else:
        info["memoria"] = "indisponível"

    return info


def _extract_lscpu_field(lscpu_out: str, field_name: str) -> Optional[str]:
    for line in lscpu_out.splitlines():
        if line.strip().startswith(field_name):
            return line.split(":", 1)[1].strip()
    return None


# --------------------------------------------------------------------------
# 2. Docker / container da aplicação
# --------------------------------------------------------------------------

def docker_container_status(container: str) -> dict[str, Any]:
    result: dict[str, Any] = {"container": container}
    if not which("docker"):
        note("Docker não encontrado no PATH — pulando inspeção de container.")
        return result

    rc, out, err = run(["docker", "inspect", container])
    if rc != 0:
        note(f"Não foi possível inspecionar o container '{container}': {err or out}")
        return result
    try:
        data = json.loads(out)[0]
        result["image"] = data.get("Config", {}).get("Image")
        result["status"] = data.get("State", {}).get("Status")
        result["started_at"] = data.get("State", {}).get("StartedAt")
        result["pid"] = data.get("State", {}).get("Pid")
        ports = data.get("NetworkSettings", {}).get("Ports", {})
        result["ports"] = ports
    except Exception as exc:  # noqa: BLE001
        note(f"Falha ao interpretar 'docker inspect {container}': {exc}")

    rc, out, _ = run(["docker", "top", container])
    result["top"] = out if rc == 0 else None

    return result


def docker_stats_snapshot(containers: list[str]) -> Optional[str]:
    """Retorna a saída bruta de `docker stats --no-stream` para os containers dados."""
    if not which("docker") or not containers:
        return None
    rc, out, err = run(["docker", "stats", "--no-stream", *containers], timeout=20)
    return out if rc == 0 else None


def pull_docker_image(image: str) -> Optional[float]:
    if not which("docker"):
        return None
    t0 = time.perf_counter()
    rc, out, err = run(["docker", "pull", image], timeout=1800)
    elapsed = time.perf_counter() - t0
    if rc != 0:
        note(f"Falha ao dar pull na imagem '{image}': {err or out}")
        return None
    return elapsed


def pull_model_in_container(container: str, model: str) -> Optional[float]:
    if not which("docker"):
        return None
    t0 = time.perf_counter()
    rc, out, err = run(["docker", "exec", container, "ollama", "pull", model], timeout=1800)
    elapsed = time.perf_counter() - t0
    if rc != 0:
        note(f"Falha ao baixar o modelo '{model}' no container '{container}': {err or out}")
        return None
    return elapsed


# --------------------------------------------------------------------------
# 3. Processos e portas
# --------------------------------------------------------------------------

def collect_processes_and_ports(process_pattern: str = "ollama") -> dict[str, str]:
    result = {}
    rc, out, _ = run(f"ps -eLf | grep -i {process_pattern} | grep -v grep", shell=True)
    result["processos"] = out if rc == 0 else "(nenhum processo encontrado / comando indisponível)"

    rc, out, _ = run("ss -tulpn 2>/dev/null | grep LISTEN", shell=True)
    if rc != 0 or not out:
        rc, out, _ = run("netstat -tulpn 2>/dev/null | grep LISTEN", shell=True)
    result["portas"] = out if rc == 0 and out else "(indisponível — pode exigir privilégios elevados)"
    return result


# --------------------------------------------------------------------------
# 4. strace opcional (resumo de syscalls)
# --------------------------------------------------------------------------

def strace_summary(pid: int, seconds: int) -> Optional[str]:
    if seconds <= 0:
        return None
    if not which("strace"):
        note("strace não está instalado — pulando resumo de syscalls.")
        return None
    try:
        proc = subprocess.Popen(
            ["strace", "-f", "-c", "-p", str(pid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception as exc:  # noqa: BLE001
        note(f"Não foi possível anexar strace ao PID {pid}: {exc}")
        return None

    time.sleep(seconds)
    proc.send_signal(subprocess.signal.SIGINT)
    try:
        _, stderr = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        note("strace não finalizou a tempo — resumo pode estar incompleto/ausente.")
        return None

    if "Operation not permitted" in stderr or "ptrace" in stderr.lower() and "EPERM" in stderr:
        note(
            "Permissão negada para anexar strace (requer CAP_SYS_PTRACE / --privileged "
            "no container ou execução como root no host)."
        )
        return None
    return stderr.strip() or None


# --------------------------------------------------------------------------
# 5. Monitoramento de recursos (amostragem em background)
# --------------------------------------------------------------------------

@dataclass
class ResourceSampler:
    interval: float
    containers: list[str]
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: Optional[threading.Thread] = None
    samples: list[dict[str, Any]] = field(default_factory=list)

    def _gpu_util(self) -> Optional[float]:
        if which("nvidia-smi"):
            rc, out, _ = run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"]
            )
            if rc == 0 and out:
                try:
                    return float(out.splitlines()[0])
                except ValueError:
                    return None
        if which("rocm-smi"):
            rc, out, _ = run(["rocm-smi", "--showuse"])
            if rc == 0:
                for line in out.splitlines():
                    if "GPU use" in line and "%" in line:
                        try:
                            return float(line.split(":")[-1].replace("%", "").strip())
                        except ValueError:
                            pass
        return None

    def _loop(self) -> None:
        while not self._stop.is_set():
            sample: dict[str, Any] = {"t": time.time()}
            if psutil:
                sample["cpu_pct"] = psutil.cpu_percent(interval=None)
                sample["mem_pct"] = psutil.virtual_memory().percent
            gpu = self._gpu_util()
            if gpu is not None:
                sample["gpu_pct"] = gpu
            self.samples.append(sample)
            self._stop.wait(self.interval)

    def start(self) -> None:
        self._stop.clear()
        self.samples = []
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def summary(self) -> dict[str, Any]:
        def agg(key: str) -> Optional[dict[str, float]]:
            vals = [s[key] for s in self.samples if key in s]
            if not vals:
                return None
            return {"media": statistics.mean(vals), "pico": max(vals)}

        return {
            "cpu": agg("cpu_pct"),
            "memoria": agg("mem_pct"),
            "gpu": agg("gpu_pct"),
            "n_amostras": len(self.samples),
        }


# --------------------------------------------------------------------------
# 6. Requisições ao Ollama e experimentos comparativos
# --------------------------------------------------------------------------

def wait_for_service(url: str, timeout: int = 30) -> bool:
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code < 500:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def ollama_generate(ollama_url: str, model: str, prompt: str, timeout: int = 120) -> dict[str, Any]:
    """Envia uma requisição não-streaming para /api/generate e retorna
    latência + métricas de tokens/s reportadas pelo próprio Ollama."""
    t0 = time.perf_counter()
    try:
        r = requests.post(
            f"{ollama_url.rstrip('/')}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        latency = time.perf_counter() - t0
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "latency_s": time.perf_counter() - t0}

    eval_count = data.get("eval_count")
    eval_duration_ns = data.get("eval_duration")
    tokens_per_s = None
    if eval_count and eval_duration_ns:
        tokens_per_s = eval_count / (eval_duration_ns / 1e9)

    return {
        "ok": True,
        "latency_s": latency,
        "eval_count": eval_count,
        "tokens_per_s": tokens_per_s,
        "total_duration_s": (data.get("total_duration") or 0) / 1e9,
        "load_duration_s": (data.get("load_duration") or 0) / 1e9,
    }


def run_load_config(
    label: str,
    ollama_url: str,
    model: str,
    concurrency: int,
    conversations: int,
    prompt: str,
    sample_interval: float,
    stats_containers: list[str],
) -> dict[str, Any]:
    print(f"\n>>> Executando {label}: concorrência={concurrency}, conversas={conversations}")

    sampler = ResourceSampler(interval=sample_interval, containers=stats_containers)
    sampler.start()
    t0 = time.perf_counter()

    results: list[dict[str, Any]] = []
    total_calls = concurrency * conversations
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(ollama_generate, ollama_url, model, prompt)
            for _ in range(total_calls)
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    wall_time = time.perf_counter() - t0
    sampler.stop()

    ok_results = [r for r in results if r.get("ok")]
    errors = [r for r in results if not r.get("ok")]
    latencies = [r["latency_s"] for r in ok_results]
    tokens = [r["tokens_per_s"] for r in ok_results if r.get("tokens_per_s")]

    docker_snapshot = docker_stats_snapshot(stats_containers)

    return {
        "label": label,
        "concorrencia": concurrency,
        "conversas_paralelas": conversations,
        "total_requisicoes": total_calls,
        "erros": len(errors),
        "tempo_total_s": wall_time,
        "latencia_media_s": statistics.mean(latencies) if latencies else None,
        "latencia_p95_s": (statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 5 else None),
        "tokens_por_s_media": statistics.mean(tokens) if tokens else None,
        "recursos": sampler.summary(),
        "docker_stats_snapshot": docker_snapshot,
        "erros_detalhe": [r.get("error") for r in errors][:5],
    }


# --------------------------------------------------------------------------
# 7. Geração do relatório em Markdown
# --------------------------------------------------------------------------

def render_report(
    hw: dict[str, Any],
    install: dict[str, Any],
    proc_ports: dict[str, str],
    container_status: dict[str, Any],
    strace_out: Optional[str],
    configs_results: list[dict[str, Any]],
    args: argparse.Namespace,
) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Relatório dos testes feitos (gerado automaticamente)\n")
    add(f"_Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}_\n")

    add("## Informações sobre o hardware\n")
    add(f"- **Sistema Operacional:** {hw['so']}")
    add(f"- **Processador:** {hw.get('cpu_name') or 'não detectado'}"
        + (f" ({hw['cpu_physical']} núcleos, {hw['cpu_logical']} threads)" if psutil else ""))
    add(f"- **Placa de vídeo:** {hw['gpu_name']}"
        + (f" _(via {hw['gpu_backend']})_" if hw.get("gpu_backend") else ""))
    add(f"- **Runtime de IA:** Ollama ({args.model}) via Docker, container `{args.container}`")
    add("")

    add("### Kernel / uname\n```\n" + hw["uname"] + "\n```\n")
    if hw.get("lscpu"):
        add("### Processador (lscpu)\n```\n" + hw["lscpu"] + "\n```\n")
    add("### Armazenamento (df -h /)\n```\n" + hw.get("df", "indisponível") + "\n```\n")
    add("### Memória\n```\n" + hw.get("memoria", "indisponível") + "\n```\n")

    add("## Instalação e execução inicial\n")
    add(f"- Comando usado para instalar/atualizar imagem: `docker pull {args.image}`" if args.image else "- Imagem não informada (pull não executado)")
    if install.get("pull_image_s") is not None:
        add(f"- Tempo de pull da imagem: {install['pull_image_s']:.1f}s")
    if install.get("pull_model_s") is not None:
        add(f"- Tempo de download do modelo `{args.model}`: {install['pull_model_s']:.1f}s")
    add(f"- Status do container `{args.container}`: {container_status.get('status', 'desconhecido')}")
    add(f"- Imagem em execução: {container_status.get('image', 'desconhecida')}")
    if container_status.get("ports"):
        add(f"- Portas mapeadas: `{json.dumps(container_status['ports'])}`")
    add("")

    add("## Processos e portas\n")
    add("### Processos (ps -eLf | grep ollama)\n```\n" + proc_ports["processos"] + "\n```\n")
    add("### Portas em uso (ss -tulpn)\n```\n" + proc_ports["portas"] + "\n```\n")
    if container_status.get("top"):
        add("### docker top\n```\n" + container_status["top"] + "\n```\n")

    add("## Logs, Erros e Avisos Relevantes\n")
    if NOTES:
        for n in NOTES:
            add(f"- {n}")
    else:
        add("- Nenhum aviso relevante registrado durante a execução.")
    add("")

    if strace_out:
        add("## Resumo de chamadas de sistema (strace -c)\n```\n" + strace_out + "\n```\n")

    add("## Experimentos comparativos\n")
    add(
        "Cada configuração dispara N requisições simultâneas (`concorrência`) "
        f"representando conversas paralelas, usando o prompt fixo:\n\n> {args.prompt!r}\n"
    )
    for cfg in configs_results:
        add(f"### {cfg['label']} (concorrência={cfg['concorrencia']}, conversas={cfg['conversas_paralelas']})\n")
        add(f"- Total de requisições: {cfg['total_requisicoes']} (erros: {cfg['erros']})")
        add(f"- Tempo total da rodada: {cfg['tempo_total_s']:.2f}s")
        if cfg["latencia_media_s"] is not None:
            add(f"- Latência média por requisição: {cfg['latencia_media_s']:.2f}s")
        if cfg["latencia_p95_s"] is not None:
            add(f"- Latência p95: {cfg['latencia_p95_s']:.2f}s")
        if cfg["tokens_por_s_media"] is not None:
            add(f"- Tokens/s (média, reportado pelo Ollama): {cfg['tokens_por_s_media']:.2f}")
        rec = cfg["recursos"]
        if rec.get("cpu"):
            add(f"- CPU (host): média {rec['cpu']['media']:.1f}% / pico {rec['cpu']['pico']:.1f}%")
        if rec.get("memoria"):
            add(f"- Memória (host): média {rec['memoria']['media']:.1f}% / pico {rec['memoria']['pico']:.1f}%")
        if rec.get("gpu"):
            add(f"- GPU: média {rec['gpu']['media']:.1f}% / pico {rec['gpu']['pico']:.1f}%")
        else:
            add("- GPU: métrica não disponível (sem nvidia-smi/rocm-smi funcional no ambiente)")
        if cfg.get("docker_stats_snapshot"):
            add("\n`docker stats --no-stream` ao final da rodada:\n```\n" + cfg["docker_stats_snapshot"] + "\n```")
        if cfg["erros_detalhe"]:
            add(f"- Exemplos de erro: {cfg['erros_detalhe']}")
        add("")

    add("## Métricas mínimas\n")
    if install.get("pull_model_s") is not None:
        add(f"- tempo de carregamento/download do modelo = {install['pull_model_s']:.1f}s")
    first_cfg_with_load = next(
        (c for c in configs_results if c["recursos"].get("n_amostras")), None
    )
    if configs_results:
        first_latency = configs_results[0].get("latencia_media_s")
        if first_latency is not None:
            add(f"- tempo médio de resposta (config 1) = {first_latency:.2f}s")
    add("- demais métricas detalhadas por configuração na seção anterior")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def parse_config(s: str) -> tuple[int, int]:
    try:
        c, p = s.split(":")
        return int(c), int(p)
    except Exception as exc:  # noqa: BLE001
        raise argparse.ArgumentTypeError(
            f"formato inválido '{s}', use concorrencia:conversas, ex. '3:3'"
        ) from exc


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ollama-url", default="http://localhost:11434", help="URL da API do Ollama")
    p.add_argument("--webui-url", default="http://localhost:3000", help="URL da WebUI (para checagem de saúde)")
    p.add_argument("--container", default="ollama", help="Nome do container do Ollama")
    p.add_argument("--webui-container", default="open-webui", help="Nome do container da WebUI")
    p.add_argument("--image", default=None, help="Imagem Docker do Ollama para medir tempo de pull (opcional)")
    p.add_argument("--model", default="qwen2.5:1.5b", help="Modelo a ser testado")
    p.add_argument("--pull-model", action="store_true", help="Baixar o modelo antes dos testes e medir o tempo")
    p.add_argument(
        "--configs",
        nargs="+",
        type=parse_config,
        default=[(1, 1), (3, 3), (5, 5)],
        help="Configurações de carga no formato concorrencia:conversas (ex.: 1:1 3:3 5:5)",
    )
    p.add_argument("--prompt", default="Explique em 3 frases o que é aprendizado de máquina.")
    p.add_argument("--sample-interval", type=float, default=1.0, help="Intervalo (s) de amostragem de CPU/GPU")
    p.add_argument("--strace-seconds", type=int, default=0, help="Segundos de strace -c no PID do container (0 = desativado)")
    p.add_argument("--output", default="relatorio_testes.md", help="Arquivo Markdown de saída")
    p.add_argument("--raw-json", default=None, help="Se definido, também salva os dados brutos em JSON neste caminho")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()

    print("== 1/6 Coletando informações de hardware ==")
    hw = collect_hardware_info()

    print("== 2/6 Verificando container e serviço ==")
    container_status = docker_container_status(args.container)
    if not wait_for_service(args.ollama_url + "/api/tags", timeout=15):
        note(f"Não foi possível confirmar que a API do Ollama está no ar em {args.ollama_url}.")

    install: dict[str, Any] = {}
    print("== 3/6 Instalação / download do modelo ==")
    if args.image:
        install["pull_image_s"] = pull_docker_image(args.image)
    if args.pull_model:
        install["pull_model_s"] = pull_model_in_container(args.container, args.model)

    print("== 4/6 Processos, portas e (opcional) strace ==")
    proc_ports = collect_processes_and_ports()
    strace_out = None
    pid = container_status.get("pid")
    if args.strace_seconds > 0 and pid:
        strace_out = strace_summary(pid, args.strace_seconds)

    print("== 5/6 Rodando experimentos comparativos de carga ==")
    stats_containers = [c for c in (args.container, args.webui_container) if c]
    configs_results = []
    for i, (concurrency, conversations) in enumerate(args.configs, start=1):
        cfg_result = run_load_config(
            label=f"Config {i}",
            ollama_url=args.ollama_url,
            model=args.model,
            concurrency=concurrency,
            conversations=conversations,
            prompt=args.prompt,
            sample_interval=args.sample_interval,
            stats_containers=stats_containers,
        )
        configs_results.append(cfg_result)

    print("== 6/6 Gerando relatório ==")
    report_md = render_report(hw, install, proc_ports, container_status, strace_out, configs_results, args)

    out_path = Path(args.output)
    out_path.write_text(report_md, encoding="utf-8")
    print(f"\nRelatório salvo em: {out_path.resolve()}")

    if args.raw_json:
        raw = {
            "hardware": hw,
            "instalacao": install,
            "processos_portas": proc_ports,
            "container_status": container_status,
            "configs_results": configs_results,
            "notas": NOTES,
        }
        Path(args.raw_json).write_text(json.dumps(raw, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
        print(f"Dados brutos salvos em: {Path(args.raw_json).resolve()}")


if __name__ == "__main__":
    main()
