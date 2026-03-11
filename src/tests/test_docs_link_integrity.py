from pathlib import Path


def _iter_markdown_files(root: Path):
    skip_prefixes = (
        "reference/",
        "adb-mcp/",
        "llama-",
    )
    for path in root.rglob("*.md"):
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(prefix) for prefix in skip_prefixes):
            continue
        yield path, rel


def test_docs_do_not_contain_stale_external_links():
    """Ensure no stale external documentation links remain."""
    root = Path(__file__).resolve().parents[2]
    stale_routes = (
        "https://docs.openclaw.ai/platform/model-providers",
        "https://docs.openclaw.ai/ai-agents/model-failover",
    )

    offenders = []
    for path, rel in _iter_markdown_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for route in stale_routes:
            if route in text:
                offenders.append((rel, route))

    assert offenders == []

