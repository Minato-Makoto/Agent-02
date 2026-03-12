"""Agent-02 CLI entry point."""

from __future__ import annotations

import os
import socket
import sys
import time

import requests

from .cli_args import (
    build_parser,
    find_workspace,
    get_arg as _arg,
    load_env_file as _load_env_file,
)
from .llama_server import LlamaServerConfig, LlamaServerProcess


def _maybe_load_env_from_args(args) -> int:
    env_file = str(_arg(args, "env_file", "") or "").strip()
    if not env_file:
        return 0
    env_file_abs = os.path.abspath(env_file)
    if not os.path.isfile(env_file_abs):
        print(f"[ERROR] Env file not found: {env_file_abs}")
        return 1
    try:
        loaded = _load_env_file(env_file_abs, override=False)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"[ERROR] Failed to load env file: {exc}")
        return 1
    print(f"[Env] Loaded {len(loaded)} variables from: {env_file_abs}")
    return 0


def _llama_target_host(host: str) -> str:
    normalized = str(host or "").strip()
    if normalized in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return normalized or "127.0.0.1"


def _llama_url(host: str, port: int) -> str:
    target_host = _llama_target_host(host)
    return f"http://{target_host}:{port}"


def _port_is_listening(host: str, port: int) -> bool:
    target_host = _llama_target_host(host)
    try:
        with socket.create_connection((target_host, int(port)), timeout=1):
            return True
    except OSError:
        return False


def _inspect_llama_endpoint(host: str, port: int) -> dict:
    target_host = _llama_target_host(host)
    health_url = f"http://{target_host}:{port}/health"
    try:
        response = requests.get(health_url, timeout=1)
        if response.status_code == 200:
            return {
                "status": "llama_server",
                "llama_url": _llama_url(target_host, port),
            }
    except Exception:
        pass

    if _port_is_listening(target_host, port):
        return {"status": "occupied", "llama_url": _llama_url(target_host, port)}
    return {"status": "free", "llama_url": _llama_url(target_host, port)}


def _build_llama_extra_flags(args) -> list[str]:
    flags: list[str] = []

    ctx_size = _arg(args, "ctx_size", None)
    gpu_layers = _arg(args, "gpu_layers", None)
    threads = _arg(args, "threads", None)
    temperature = _arg(args, "temp", None)
    top_p = _arg(args, "top_p", None)
    top_k = _arg(args, "top_k", None)
    repeat_penalty = _arg(args, "repeat_penalty", None)
    seed = _arg(args, "seed", None)
    max_tokens = _arg(args, "max_tokens", None)

    if ctx_size is not None:
        flags.extend(["--ctx-size", str(ctx_size)])
    if gpu_layers is not None:
        flags.extend(["--gpu-layers", str(gpu_layers)])
    if threads is not None and int(threads) > 0:
        flags.extend(["--threads", str(threads)])
    if temperature is not None:
        flags.extend(["--temp", str(temperature)])
    if top_p is not None:
        flags.extend(["--top-p", str(top_p)])
    if top_k is not None:
        flags.extend(["--top-k", str(top_k)])
    if repeat_penalty is not None:
        flags.extend(["--repeat-penalty", str(repeat_penalty)])
    if seed is not None and int(seed) >= 0:
        flags.extend(["--seed", str(seed)])
    if max_tokens is not None:
        flags.extend(["--n-predict", str(max_tokens)])
    return flags


def run_llama_server(args) -> int:
    env_rc = _maybe_load_env_from_args(args)
    if env_rc != 0:
        return env_rc

    workspace_dir = find_workspace(args)
    if not os.path.isdir(workspace_dir):
        os.makedirs(workspace_dir, exist_ok=True)
    os.environ["AGENTFORGE_WORKSPACE"] = workspace_dir

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ai_agent_root = os.path.dirname(project_root)

    server_exe = str(_arg(args, "server_exe", "") or "").strip()
    if not server_exe:
        server_exe = os.path.join(ai_agent_root, "llama.cpp", "llama-server.exe")

    models_dir = str(_arg(args, "models_dir", "") or "").strip()
    if not models_dir:
        models_dir = os.path.join(ai_agent_root, "models")

    llm_host = str(_arg(args, "host", "127.0.0.1") or "127.0.0.1").strip() or "127.0.0.1"
    llm_port = int(_arg(args, "port", 8080) or 8080)

    probe = _inspect_llama_endpoint(llm_host, llm_port)
    if probe["status"] == "llama_server":
        print(f"[Launcher] llama-server is already running at {_llama_url(llm_host, llm_port)}.")
        print("[Launcher] Reusing the existing llama-server instance instead of starting a duplicate process.")
        return 0
    if probe["status"] == "occupied":
        print(
            f"[ERROR] Cannot start llama-server: {llm_host}:{llm_port} is already in use by another process."
        )
        print("[ERROR] Close the existing service or change HOST/PORT before trying again.")
        return 1

    extra_flags = _build_llama_extra_flags(args)

    host_config = LlamaServerConfig(
        server_exe=server_exe,
        models_dir=models_dir,
        host=llm_host,
        port=llm_port,
        models_max=int(_arg(args, "models_max", 1) or 1),
        boot_timeout=int(_arg(args, "boot_timeout", 120) or 120),
        shutdown_timeout=int(_arg(args, "shutdown_timeout", 5) or 5),
        extra_flags=extra_flags,
    )

    if not os.path.isfile(server_exe):
        print(f"[Launcher] ERROR: llama-server executable not found: {server_exe}")
        return 1
    if not os.path.isdir(models_dir):
        print(f"[Launcher] ERROR: models directory not found: {models_dir}")
        return 1

    llama_server = LlamaServerProcess(host_config)
    print(f"[Launcher] Starting llama-server: {server_exe}")
    print(f"[Launcher] Models dir: {models_dir}")
    if not llama_server.start():
        print("[Launcher] ERROR: llama-server failed to start.")
        if llama_server.last_error:
            print(f"[Launcher] Reason: {llama_server.last_error}")
        if llama_server.command_line:
            print(f"[Launcher] Command: {llama_server.command_line}")
        if llama_server.last_stderr_tail:
            print("[Launcher] llama-server stderr (tail):")
            print(llama_server.last_stderr_tail)
        if llama_server.last_error_category == "port_bind":
            print(f"[Launcher] Check whether {llm_host}:{llm_port} is already in use by another process.")
        return 1

    print(f"[Launcher] URL: {_llama_url(llm_host, llm_port)}")
    print(f"[Launcher] Health: {_llama_url(llm_host, llm_port)}/health")
    print(f"[Launcher] Models: {_llama_url(llm_host, llm_port)}/models")
    print(f"[Launcher] Workspace: {workspace_dir}")
    print("[Launcher] UI ownership belongs to llama-server; Agent-02 is currently a launcher scaffold only.")

    try:
        while llama_server.is_running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()
        print("[Launcher] Stopping llama-server...")
        llama_server.stop()
        return 0

    exit_code = llama_server.last_exit_code or 0
    if exit_code != 0:
        print(f"[Launcher] llama-server exited with code {exit_code}.")
        if llama_server.last_stderr_tail:
            print("[Launcher] llama-server stderr (tail):")
            print(llama_server.last_stderr_tail)
    return exit_code


def main() -> int:
    parser = build_parser()
    parsed = parser.parse_args()

    if not parsed.command:
        parser.print_help()
        return 0

    if parsed.command == "run":
        return run_llama_server(parsed)

    return 0


if __name__ == "__main__":
    sys.exit(main())
