"""
Agent-02 CLI entry point.

`agentforge run` is now a deprecated alias for `agentforge gateway run`.
The supported runtime surface is the gateway plus WebUI.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser

import requests

from .cli_args import (
    build_inference_config,
    build_parser,
    find_workspace,
    get_arg as _arg,
    load_env_file as _load_env_file,
)
from .cli_runtime import run_interactive as _run_interactive
from .llm_inference import LLMInference
from .ui import ChatUI


def run_interactive(args) -> int:
    return _run_interactive(args, ui_factory=ChatUI, llm_factory=LLMInference)


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


def _is_loopback_host(host: str) -> bool:
    normalized = str(host or "").strip().lower()
    return normalized in {"127.0.0.1", "localhost", "::1"}


def _gateway_target_host(host: str) -> str:
    normalized = str(host or "").strip()
    if normalized in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return normalized or "127.0.0.1"


def _webchat_url(host: str, port: int) -> str:
    target_host = _gateway_target_host(host)
    return f"http://{target_host}:{port}/webchat"


def _port_is_listening(host: str, port: int) -> bool:
    target_host = _gateway_target_host(host)
    try:
        with socket.create_connection((target_host, int(port)), timeout=1):
            return True
    except OSError:
        return False


def _inspect_gateway_endpoint(host: str, port: int) -> dict:
    target_host = _gateway_target_host(host)
    health_url = f"http://{target_host}:{port}/health"
    try:
        response = requests.get(health_url, timeout=1)
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, dict) and payload.get("gateway") is True:
                return {
                    "status": "agent_gateway",
                    "payload": payload,
                    "web_url": _webchat_url(target_host, port),
                }
    except Exception:
        pass

    if _port_is_listening(target_host, port):
        return {"status": "occupied", "web_url": _webchat_url(target_host, port)}
    return {"status": "free", "web_url": _webchat_url(target_host, port)}


def _schedule_browser_open(host: str, port: int) -> None:
    target_host = _gateway_target_host(host)
    health_url = f"http://{target_host}:{port}/health"
    web_url = _webchat_url(target_host, port)

    def _worker() -> None:
        deadline = time.time() + 30.0
        while time.time() < deadline:
            try:
                response = requests.get(health_url, timeout=1)
                if response.status_code == 200:
                    webbrowser.open(web_url)
                    return
            except Exception:
                pass
            time.sleep(0.25)

    threading.Thread(target=_worker, name="agent-02-browser-open", daemon=True).start()


def run_gateway_server(args) -> int:
    from .agent_core import AgentConfig
    from .gateway.inference_host import InferenceHostConfig
    from .gateway.server import create_app, run_gateway

    env_rc = _maybe_load_env_from_args(args)
    if env_rc != 0:
        return env_rc

    workspace_dir = find_workspace(args)
    if not os.path.isdir(workspace_dir):
        print(f"[ERROR] Workspace not found: {workspace_dir}")
        return 1
    os.environ["AGENTFORGE_WORKSPACE"] = workspace_dir

    config = build_inference_config(args)

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ai_agent_root = os.path.dirname(project_root)

    server_exe = str(_arg(args, "server_exe", "") or "").strip()
    if not server_exe:
        server_exe = os.path.join(ai_agent_root, "llama.cpp", "llama-server.exe")

    models_dir = str(_arg(args, "models_dir", "") or "").strip()
    if not models_dir:
        models_dir = os.path.join(ai_agent_root, "models")

    gateway_host = str(_arg(args, "gateway_host", "127.0.0.1") or "127.0.0.1").strip()
    gateway_port = int(_arg(args, "gateway_port", 18789) or 18789)
    allow_remote_admin = bool(_arg(args, "allow_remote_admin", False))
    open_browser = bool(_arg(args, "open_browser", False))

    if not _is_loopback_host(gateway_host) and not allow_remote_admin:
        print(
            "[ERROR] Refusing to bind the WebUI/admin gateway on a non-loopback address. "
            "Pass --allow-remote-admin if you really want this."
        )
        return 1

    gateway_probe = _inspect_gateway_endpoint(gateway_host, gateway_port)
    if gateway_probe["status"] == "agent_gateway":
        print(
            f"[Gateway] Agent-02 is already running at http://{_gateway_target_host(gateway_host)}:{gateway_port}."
        )
        print("[Gateway] Reusing the existing WebUI instance instead of starting a second server.")
        if open_browser:
            webbrowser.open(gateway_probe["web_url"])
        return 0
    if gateway_probe["status"] == "occupied":
        print(
            f"[ERROR] Cannot start Agent-02: {gateway_host}:{gateway_port} is already in use by another process."
        )
        print("[ERROR] Close the existing service or change GATEWAY_PORT before trying again.")
        return 1

    llm_host = str(_arg(args, "host", "127.0.0.1") or "127.0.0.1")
    llm_port = int(_arg(args, "port", 8080) or 8080)
    llm_base_url = f"http://{llm_host}:{llm_port}"

    host_config = InferenceHostConfig(
        server_exe=server_exe,
        models_dir=models_dir,
        host=llm_host,
        port=llm_port,
        boot_timeout=int(_arg(args, "boot_timeout", 120) or 120),
        shutdown_timeout=int(_arg(args, "shutdown_timeout", 5) or 5),
    )

    agent_config = AgentConfig(
        max_iterations=int(_arg(args, "max_iterations", 60) or 60),
        max_repeats=int(_arg(args, "max_repeats", 3) or 3),
        timeout=float(_arg(args, "agent_timeout", 300) or 300),
        workspace_dir=workspace_dir,
        verbose=bool(_arg(args, "verbose", False)),
    )

    app = create_app(
        workspace_dir=workspace_dir,
        host_config=host_config,
        agent_config=agent_config,
        inference_config=config,
        llm_base_url=llm_base_url,
    )

    if os.path.isfile(server_exe) and os.path.isdir(models_dir):
        inference_host = app.state.inference_host
        print(f"[Gateway] Starting llama-server: {server_exe}")
        print(f"[Gateway] Models dir: {models_dir}")
        if not inference_host.start():
            print(
                "[Gateway] ERROR: llama-server failed to start. "
                f"Check whether {llm_host}:{llm_port} is already in use by another process."
            )
            return 1
    else:
        print(f"[Gateway] No local llama-server found at {server_exe}. Gateway will boot without local models.")

    print(f"[Gateway] Starting on {gateway_host}:{gateway_port}")
    print(f"[Gateway] WebUI: {_webchat_url(gateway_host, gateway_port)}")
    print(f"[Gateway] WebSocket: ws://{gateway_host}:{gateway_port}/ws")
    print(f"[Gateway] Workspace: {workspace_dir}")

    if open_browser:
        _schedule_browser_open(gateway_host, gateway_port)

    run_gateway(app, host=gateway_host, port=gateway_port)
    return 0


def main() -> int:
    parser = build_parser()
    parsed = parser.parse_args()

    if not parsed.command:
        parser.print_help()
        return 0

    if parsed.command == "run":
        print("[Deprecated] `agentforge run` now maps to `agentforge gateway run`.")
        return run_gateway_server(parsed)

    if parsed.command == "gateway":
        if getattr(parsed, "gateway_command", "run") != "run":
            parser.error("Unsupported gateway command.")
        return run_gateway_server(parsed)

    return 0


if __name__ == "__main__":
    sys.exit(main())
