"""Minimal llama-server launcher for Agent-02."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentforge",
        description="Thin Agent-02 launcher that defers runtime ownership to llama-server.",
    )
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="Start llama-server directly")
    run_parser.add_argument("--server-exe", required=True)
    run_parser.add_argument("--models-dir", required=True)
    run_parser.add_argument("--host", default="127.0.0.1")
    run_parser.add_argument("--port", type=int, default=8080)
    run_parser.add_argument("--workspace", default="")
    run_parser.add_argument("llama_args", nargs=argparse.REMAINDER)

    return parser


def _build_command(args: argparse.Namespace) -> list[str]:
    command = [
        args.server_exe,
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--models-dir",
        args.models_dir,
    ]
    if args.llama_args:
        command.extend(args.llama_args)
    return command


def run_llama_server(args: argparse.Namespace) -> int:
    workspace = str(args.workspace or "").strip()
    if workspace:
        os.makedirs(workspace, exist_ok=True)

    command = _build_command(args)
    print("[Agent-02] Thin launcher only. Runtime/UI ownership stays with llama-server.")
    print(f"[Agent-02] Command: {subprocess.list2cmdline(command)}")

    process = subprocess.Popen(command)
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return process.wait()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return run_llama_server(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
