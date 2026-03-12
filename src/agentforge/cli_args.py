from __future__ import annotations

import argparse
import os
from typing import Any, Dict
from urllib.parse import urlparse


def _add_shared_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-c", "--ctx-size", type=int, default=None)
    p.add_argument("--gpu-layers", "-ngl", type=int, default=None)
    p.add_argument("--threads", type=int, default=None)
    p.add_argument("--temp", type=float, default=None)
    p.add_argument("--top-p", type=float, default=None)
    p.add_argument("--top-k", type=int, default=None)
    p.add_argument("--repeat-penalty", type=float, default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--max-tokens", type=int, default=None)
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--host", default="")
    p.add_argument("--boot-timeout", type=int, default=None)
    p.add_argument("--shutdown-timeout", type=int, default=None)
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    p.add_argument("--workspace", default="", help="Path to workspace directory")
    p.add_argument(
        "--env-file",
        default="",
        help="Optional .env-style file to preload environment variables.",
    )


def _add_launcher_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--server-exe",
        default="",
        help="Path to llama-server.exe (default: auto-detect relative to project).",
    )
    p.add_argument(
        "--models-dir",
        default="",
        help="Path to models directory (default: auto-detect relative to project).",
    )
    p.add_argument("--models-max", type=int, default=1, help="Maximum concurrently loaded models in router mode.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentforge",
        description="Agent-02 llama-server launcher scaffold",
    )
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Start llama-server directly")
    _add_launcher_args(run_parser)
    _add_shared_args(run_parser)

    return parser


def get_arg(args: Any, name: str, default: Any = None) -> Any:
    return getattr(args, name, default)


def find_workspace(args: Any) -> str:
    explicit = str(get_arg(args, "workspace", "") or "").strip()
    if explicit:
        return os.path.abspath(explicit)

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, "workspace")


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: str, override: bool = False) -> Dict[str, str]:
    loaded: Dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            value = _strip_wrapping_quotes(value.strip())
            loaded[key] = value
            if override or key not in os.environ:
                os.environ[key] = value
    return loaded


def is_openai_api_base_url(base_url: str) -> bool:
    try:
        host = (urlparse(base_url or "").hostname or "").lower()
    except Exception:
        return False
    return host in {"api.openai.com"} or host.endswith(".openai.com")
