from builtin_tools import file_ops


def test_file_organizer_tools_mutating_flow(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("AGENTFORGE_WORKSPACE", str(workspace))

    src = workspace / "a.txt"
    src.write_text("hello", encoding="utf-8")

    mk = file_ops._make_directory({"path": "docs/archive"})
    assert mk.success is True
    assert (workspace / "docs" / "archive").is_dir()

    cp = file_ops._copy_file({"source": "a.txt", "destination": "docs/a-copy.txt"})
    assert cp.success is True
    assert (workspace / "docs" / "a-copy.txt").read_text(encoding="utf-8") == "hello"

    mv = file_ops._move_file({"source": "docs/a-copy.txt", "destination": "docs/archive/a-copy.txt"})
    assert mv.success is True
    assert (workspace / "docs" / "archive" / "a-copy.txt").exists()

    rn = file_ops._rename_path({"path": "docs/archive/a-copy.txt", "new_name": "renamed.txt"})
    assert rn.success is True
    assert (workspace / "docs" / "archive" / "renamed.txt").exists()


def test_find_duplicates_reports_hash_groups(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("AGENTFORGE_WORKSPACE", str(workspace))

    (workspace / "d1").mkdir()
    (workspace / "d2").mkdir()
    payload = "same-content"
    (workspace / "d1" / "a.txt").write_text(payload, encoding="utf-8")
    (workspace / "d2" / "b.txt").write_text(payload, encoding="utf-8")

    result = file_ops._find_duplicates({"path": "."})
    assert result.success is True
    assert result.output["duplicate_groups"] >= 1
    group = result.output["groups"][0]
    assert len(group["files"]) >= 2


def test_file_organizer_tools_enforce_workspace_guard(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    monkeypatch.setenv("AGENTFORGE_WORKSPACE", str(workspace))

    result = file_ops._copy_file({"source": str(outside), "destination": "x.txt"})
    assert result.success is False
    assert "SECURITY[" in result.error
