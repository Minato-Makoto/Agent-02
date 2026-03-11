from builtin_tools.sys_ops import _shell_command, _validate_command
from builtin_tools.web_ops import _validate_url


def test_blocked_command_is_rejected():
    result = _shell_command({"command": "rm -rf /"})
    assert result.success is False
    assert "SECURITY[BLOCKED_COMMAND]" in result.error


def test_allowlisted_command_executes():
    result = _shell_command({"command": "echo hello"})
    assert result.success is True
    assert result.output["exit_code"] == 0


def test_python_inline_execution_is_blocked():
    ok, code, _ = _validate_command('python -c "print(123)"')
    assert ok is False
    assert code == "BLOCKED_PYTHON_FLAG"


def test_pip_install_is_blocked():
    ok, code, _ = _validate_command("pip install requests")
    assert ok is False
    assert code == "BLOCKED_PIP_SUBCOMMAND"


def test_node_eval_is_blocked():
    ok, code, _ = _validate_command('node -e "console.log(1)"')
    assert ok is False
    assert code == "BLOCKED_NODE_FLAG"


def test_npx_arbitrary_command_is_blocked():
    ok, code, _ = _validate_command("npx cowsay hello")
    assert ok is False
    assert code == "BLOCKED_NPX_COMMAND"


def test_powershell_cmdlet_pipeline_is_allowlisted():
    ok, code, _ = _validate_command("Get-ChildItem | Select-Object -First 1")
    assert ok is True
    assert code == "OK"


def test_web_url_policy_blocks_basic_ssrf_targets():
    ok_localhost, reason_localhost = _validate_url("http://localhost:8080")
    ok_metadata, reason_metadata = _validate_url("http://169.254.169.254/latest/meta-data/")

    assert ok_localhost is False
    assert "Blocked host" in reason_localhost
    assert ok_metadata is False
    assert "Blocked host" in reason_metadata or "private/local IP" in reason_metadata


def test_shell_command_blocks_cwd_outside_workspace_by_default(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("AGENTFORGE_WORKSPACE", str(workspace))
    monkeypatch.delenv("SHELL_WORKSPACE_ONLY", raising=False)

    result = _shell_command({"command": "echo hello", "cwd": str(outside)})
    assert result.success is False
    assert "SECURITY[CWD_OUTSIDE_WORKSPACE]" in result.error


def test_shell_command_allows_outside_cwd_when_workspace_policy_disabled(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("AGENTFORGE_WORKSPACE", str(workspace))
    monkeypatch.setenv("SHELL_WORKSPACE_ONLY", "0")

    result = _shell_command({"command": "echo hello", "cwd": str(outside)})
    assert result.success is True
    assert result.output["exit_code"] == 0
