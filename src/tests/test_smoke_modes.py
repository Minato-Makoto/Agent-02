import argparse
import os
import subprocess
from pathlib import Path

from agentforge import cli
from agentforge.cli_args import build_parser


def _launcher_args(workspace, **overrides):
    data = dict(
        server_exe="",
        models_dir="",
        ctx_size=None,
        gpu_layers=None,
        threads=None,
        temp=None,
        top_p=None,
        top_k=None,
        repeat_penalty=None,
        seed=None,
        max_tokens=None,
        port=8080,
        host="127.0.0.1",
        boot_timeout=None,
        shutdown_timeout=None,
        models_max=1,
        verbose=False,
        workspace=str(workspace),
        env_file="",
    )
    data.update(overrides)
    return argparse.Namespace(**data)


def test_run_bat_is_launcher_only():
    run_bat = Path("run.bat").read_text(encoding="utf-8")
    assert "python -m agentforge.cli run ^" in run_bat
    assert "run_interactive" not in run_bat
    assert "GATEWAY_HOST" not in run_bat
    assert "GATEWAY_PORT" not in run_bat
    assert "--allow-remote-admin" not in run_bat


def test_run_bat_uses_crlf_line_endings():
    data = Path("run.bat").read_bytes()
    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")


def test_run_bat_smoke_run_help():
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["EXTRA_ARGS"] = "--help"
    env["AGENTFORGE_NO_PAUSE_ON_FAIL"] = "1"

    proc = subprocess.run(
        ["cmd", "/c", "run.bat"],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0
    assert "usage: agentforge run" in proc.stdout


def test_cli_parser_accepts_run_command():
    parser = build_parser()
    args = parser.parse_args(["run", "--server-exe", "llama-server.exe"])

    assert args.command == "run"
    assert args.server_exe == "llama-server.exe"


def test_run_llama_server_reuses_existing_instance(monkeypatch, minimal_workspace):
    monkeypatch.setattr(
        cli,
        "_inspect_llama_endpoint",
        lambda host, port: {
            "status": "llama_server",
            "llama_url": "http://127.0.0.1:8080",
        },
    )

    rc = cli.run_llama_server(_launcher_args(minimal_workspace))
    assert rc == 0


def test_run_llama_server_fails_fast_when_port_is_foreign(monkeypatch, minimal_workspace):
    monkeypatch.setattr(
        cli,
        "_inspect_llama_endpoint",
        lambda host, port: {
            "status": "occupied",
            "llama_url": "http://127.0.0.1:8080",
        },
    )

    rc = cli.run_llama_server(_launcher_args(minimal_workspace))
    assert rc == 1


def test_run_bat_does_not_reference_gateway_flags():
    run_bat = Path("run.bat").read_text(encoding="utf-8")
    assert "ALLOW_REMOTE_ADMIN" not in run_bat
    assert "REMOTE_FLAG" not in run_bat


def test_cli_module_no_longer_exposes_interactive_runtime():
    assert not hasattr(cli, "run_interactive")
