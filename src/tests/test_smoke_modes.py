import argparse
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

from agentforge import cli, cli_runtime
from agentforge.cli_args import build_parser
from agentforge.contracts import ChatCompletionResult


class _DummyUI:
    def __init__(self, inputs, verbose=False):
        self._inputs = list(inputs)
        self.verbose = verbose

    def error(self, msg):
        return None

    def status(self, msg):
        return None

    def welcome(self, model_name, tools=None, **kwargs):
        return None

    def goodbye(self):
        return None

    def get_input(self):
        if not self._inputs:
            return "exit"
        return self._inputs.pop(0)

    def stream_start(self):
        return None

    def stream_end(self):
        return None

    def stream_token(self, token):
        return None

    def stream_reasoning(self, token):
        return None

    def show_tool_call(self, name, arguments):
        return None

    def show_tool_result(self, name, result):
        return None

    def thinking_start(self):
        return None

    def thinking_stop(self):
        return None


def _gateway_args(workspace, **overrides):
    data = dict(
        provider="local",
        model="",
        server_exe="",
        models_dir="",
        gateway_host="127.0.0.1",
        gateway_port=18789,
        allow_remote_admin=False,
        open_browser=False,
        base_url="",
        model_id="",
        api_key_env="OPENAI_API_KEY",
        ctx_size=None,
        gpu_layers=None,
        threads=None,
        temp=None,
        top_p=None,
        top_k=None,
        repeat_penalty=None,
        seed=None,
        reasoning_effort="",
        max_tokens=None,
        port=8080,
        host="127.0.0.1",
        boot_timeout=None,
        health_timeout=None,
        request_timeout=None,
        shutdown_timeout=None,
        compat_retry_limit=None,
        max_requests_per_minute=None,
        verbose=False,
        workspace=str(workspace),
        env_file="",
        max_iterations=60,
        max_repeats=3,
        agent_timeout=300.0,
    )
    data.update(overrides)
    return argparse.Namespace(**data)


def test_run_bat_is_webui_first():
    run_bat = Path("run.bat").read_text(encoding="utf-8")
    assert 'python -m agentforge.cli gateway run ^' in run_bat
    assert '--open-browser' in run_bat
    assert 'AUTO_OPEN_BROWSER' in run_bat
    assert '--attach-terminal' not in run_bat
    assert 'MODEL_PATH' not in run_bat
    assert 'terminal connect' not in run_bat


def test_run_bat_uses_crlf_line_endings():
    data = Path("run.bat").read_bytes()
    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")


def test_run_bat_smoke_gateway_help():
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
    assert "usage: agentforge gateway" in proc.stdout


def test_cli_parser_accepts_gateway_run_and_run_alias():
    parser = build_parser()
    gateway_args = parser.parse_args(["gateway", "run", "--open-browser"])
    alias_args = parser.parse_args(["run", "--provider", "local", "--open-browser"])

    assert gateway_args.command == "gateway"
    assert gateway_args.gateway_command == "run"
    assert gateway_args.open_browser is True
    assert alias_args.command == "run"
    assert alias_args.provider == "local"
    assert alias_args.open_browser is True


def test_run_gateway_server_reuses_existing_gateway_instance(monkeypatch, minimal_workspace):
    opened = {}

    monkeypatch.setattr(
        cli,
        "_inspect_gateway_endpoint",
        lambda host, port: {
            "status": "agent_gateway",
            "web_url": "http://127.0.0.1:18789/webchat",
            "payload": {"gateway": True},
        },
    )
    monkeypatch.setattr(cli, "webbrowser", SimpleNamespace(open=lambda url: opened.setdefault("url", url) or True))

    rc = cli.run_gateway_server(_gateway_args(minimal_workspace, open_browser=True))
    assert rc == 0
    assert opened["url"] == "http://127.0.0.1:18789/webchat"


def test_run_gateway_server_fails_fast_when_gateway_port_is_foreign(monkeypatch, minimal_workspace):
    monkeypatch.setattr(
        cli,
        "_inspect_gateway_endpoint",
        lambda host, port: {
            "status": "occupied",
            "web_url": "http://127.0.0.1:18789/webchat",
        },
    )

    rc = cli.run_gateway_server(_gateway_args(minimal_workspace))
    assert rc == 1


def test_run_bat_help_respects_auto_open_browser_override():
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["AUTO_OPEN_BROWSER"] = "0"
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
    assert "usage: agentforge gateway" in proc.stdout


def test_run_bat_exposes_webui_flags():
    run_bat = Path("run.bat").read_text(encoding="utf-8")
    assert 'set "BROWSER_FLAG=--open-browser"' in run_bat
    assert 'set "REMOTE_FLAG=--allow-remote-admin"' in run_bat


def test_remote_mode_smoke_with_mock_endpoint(monkeypatch, mock_chat_server, minimal_workspace):
    mock_chat_server.enqueue_stream(
        [
            {"choices": [{"delta": {"content": "remote "}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]},
        ]
    )

    original_connect_remote = cli.LLMInference.connect_remote

    def patched_connect_remote(self, base_url, model_id, api_key="", config=None):
        ok = original_connect_remote(self, base_url, model_id, api_key, config)
        self.capabilities.supports_tools = True
        return ok

    monkeypatch.setattr(cli.LLMInference, "connect_remote", patched_connect_remote)
    monkeypatch.setattr(cli, "ChatUI", lambda verbose=False: _DummyUI(["hello", "exit"], verbose))

    args = argparse.Namespace(
        provider="openai_compatible",
        model="",
        server_exe="",
        base_url=mock_chat_server.url,
        model_id="mock",
        api_key_env="OPENAI_API_KEY",
        ctx_size=1024,
        gpu_layers=-1,
        threads=0,
        temp=0.1,
        max_tokens=128,
        port=8080,
        verbose=False,
        workspace=str(minimal_workspace),
        session="",
        max_iterations=10,
        max_repeats=3,
        agent_timeout=300.0,
    )
    os.environ["OPENAI_API_KEY"] = "dummy"

    rc = cli.run_interactive(args)
    assert rc == 0
    assert len(mock_chat_server.requests) >= 1


def test_remote_openai_endpoint_requires_api_key(monkeypatch, minimal_workspace):
    monkeypatch.setattr(cli, "ChatUI", lambda verbose=False: _DummyUI(["exit"], verbose))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    args = argparse.Namespace(
        provider="openai_compatible",
        model="",
        server_exe="",
        base_url="https://api.openai.com/v1",
        model_id="gpt-5-mini",
        api_key_env="OPENAI_API_KEY",
        ctx_size=1024,
        gpu_layers=-1,
        threads=0,
        temp=0.1,
        max_tokens=128,
        port=8080,
        verbose=False,
        workspace=str(minimal_workspace),
        session="",
        max_iterations=10,
        max_repeats=3,
        agent_timeout=300.0,
    )

    rc = cli.run_interactive(args)
    assert rc == 1


def test_local_mode_smoke_without_starting_real_server(monkeypatch, minimal_workspace):
    monkeypatch.setattr(cli, "ChatUI", lambda verbose=False: _DummyUI(["hello", "exit"], verbose))

    def fake_load_model(self, model_path, config=None, server_exe=""):
        self._loaded = True
        self.capabilities.supports_tools = True
        return True

    def fake_chat_completion(self, messages, **kwargs):
        on_token = kwargs.get("on_token")
        if on_token:
            on_token("ok")
        return ChatCompletionResult(content="ok")

    def fake_unload(self):
        self._loaded = False

    monkeypatch.setattr(cli.LLMInference, "load_model", fake_load_model)
    monkeypatch.setattr(cli.LLMInference, "chat_completion", fake_chat_completion)
    monkeypatch.setattr(cli.LLMInference, "unload", fake_unload)

    args = argparse.Namespace(
        provider="local",
        model="dummy.gguf",
        server_exe="llama-server.exe",
        base_url="",
        model_id="local",
        api_key_env="OPENAI_API_KEY",
        ctx_size=1024,
        gpu_layers=-1,
        threads=0,
        temp=0.1,
        max_tokens=128,
        port=8080,
        verbose=False,
        workspace=str(minimal_workspace),
        session="",
        max_iterations=10,
        max_repeats=3,
        agent_timeout=300.0,
    )

    rc = cli.run_interactive(args)
    assert rc == 0


def test_runtime_applies_agent_loop_overrides(monkeypatch, minimal_workspace):
    captured = {}

    class _FakeAgent:
        def __init__(self, config, **kwargs):
            captured["config"] = config

        def run(self, user_input, callbacks=None):
            return "ok"

        def reset(self):
            return None

    monkeypatch.setattr(cli_runtime, "Agent", _FakeAgent)
    monkeypatch.setattr(cli, "ChatUI", lambda verbose=False: _DummyUI(["exit"], verbose))

    def fake_load_model(self, model_path, config=None, server_exe=""):
        self._loaded = True
        self.capabilities.supports_tools = True
        return True

    def fake_unload(self):
        self._loaded = False

    monkeypatch.setattr(cli.LLMInference, "load_model", fake_load_model)
    monkeypatch.setattr(cli.LLMInference, "unload", fake_unload)

    args = argparse.Namespace(
        provider="local",
        model="dummy.gguf",
        server_exe="llama-server.exe",
        base_url="",
        model_id="local",
        api_key_env="OPENAI_API_KEY",
        ctx_size=1024,
        gpu_layers=-1,
        threads=0,
        temp=0.1,
        max_tokens=128,
        port=8080,
        verbose=False,
        workspace=str(minimal_workspace),
        session="",
        max_iterations=17,
        max_repeats=5,
        agent_timeout=42.5,
    )

    rc = cli.run_interactive(args)
    assert rc == 0
    assert captured["config"].max_iterations == 17
    assert captured["config"].max_repeats == 5
    assert captured["config"].timeout == 42.5


def test_runtime_closes_browser_manager_on_exit(monkeypatch, minimal_workspace):
    monkeypatch.setattr(cli, "ChatUI", lambda verbose=False: _DummyUI(["exit"], verbose))

    def fake_load_model(self, model_path, config=None, server_exe=""):
        self._loaded = True
        self.capabilities.supports_tools = True
        return True

    def fake_unload(self):
        self._loaded = False

    closed = {"called": False}

    def fake_close():
        closed["called"] = True

    from builtin_tools import browser_tools

    monkeypatch.setattr(browser_tools.BrowserManager, "close", staticmethod(fake_close))
    monkeypatch.setattr(cli.LLMInference, "load_model", fake_load_model)
    monkeypatch.setattr(cli.LLMInference, "unload", fake_unload)

    args = argparse.Namespace(
        provider="local",
        model="dummy.gguf",
        server_exe="llama-server.exe",
        base_url="",
        model_id="local",
        api_key_env="OPENAI_API_KEY",
        ctx_size=1024,
        gpu_layers=-1,
        threads=0,
        temp=0.1,
        max_tokens=128,
        port=8080,
        verbose=False,
        workspace=str(minimal_workspace),
        session="",
        max_iterations=10,
        max_repeats=3,
        agent_timeout=300.0,
    )

    rc = cli.run_interactive(args)
    assert rc == 0
    assert closed["called"] is True
