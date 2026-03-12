from pathlib import Path


TEXT_EXTENSIONS = {
    ".bat",
    ".css",
    ".js",
    ".json",
    ".md",
    ".py",
    ".svelte",
    ".toml",
    ".ts",
    ".txt",
    ".yml",
    ".yaml",
}


def _iter_text_files(root: Path):
    skip_prefixes = (
        ".git/",
        ".pytest_cache/",
        "adb-mcp/",
    )
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(prefix) for prefix in skip_prefixes):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        yield path, rel


def test_repo_does_not_reference_the_old_external_ui_repo():
    """Ensure the shipped repo no longer contains references to the old external UI repo."""
    root = Path(__file__).resolve().parents[2]
    forbidden = "open" + "claw"

    offenders = []
    for path, rel in _iter_text_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        if forbidden in text:
            offenders.append(rel)

    assert offenders == []


def test_repo_does_not_ship_a_web_ui_directory():
    root = Path(__file__).resolve().parents[2]
    assert not (root / "ui").exists()


def test_repo_does_not_ship_the_old_gateway_runtime_directory():
    root = Path(__file__).resolve().parents[2]
    assert not (root / "src" / "agentforge" / "gateway").exists()


def test_repo_does_not_ship_the_legacy_agent_runtime_modules():
    root = Path(__file__).resolve().parents[2]
    forbidden = {
        "agent_core.py",
        "cli_runtime.py",
        "context.py",
        "contracts.py",
        "llm_inference.py",
        "model_output_renderer.py",
        "prompting.py",
        "runtime_config.py",
        "schema_normalizer.py",
        "session.py",
        "session_repair.py",
        "skills.py",
        "summarizer.py",
        "tools.py",
        "tool_call_parser.py",
        "tool_id.py",
        "tool_loop.py",
        "tool_mutation.py",
        "transcript_policy.py",
        "ui.py",
    }
    present = {
        path.name
        for path in (root / "src" / "agentforge").glob("*.py")
        if path.name in forbidden
    }
    assert present == set()


def test_repo_does_not_ship_builtin_tools_runtime_directory():
    root = Path(__file__).resolve().parents[2]
    assert not (root / "src" / "builtin_tools").exists()
