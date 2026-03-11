from pathlib import Path

from builtin_tools.file_ops import _write_file


def test_write_file_blocks_path_outside_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("AGENTFORGE_WORKSPACE", str(workspace))

    outside_file = tmp_path / "outside.txt"
    result = _write_file({"path": str(outside_file), "content": "x"})

    assert result.success is False
    assert "SECURITY[WRITE_OUTSIDE_WORKSPACE]" in result.error


def test_write_file_allows_relative_path_inside_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("AGENTFORGE_WORKSPACE", str(workspace))

    result = _write_file({"path": "notes/today.md", "content": "hello"})
    target = workspace / "notes" / "today.md"

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "hello"
