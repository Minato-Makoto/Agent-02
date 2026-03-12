from pathlib import Path

import pytest


@pytest.fixture
def minimal_workspace(tmp_path: Path) -> Path:
    for name in ("IDENTITY.md", "SOUL.md", "AGENT.md", "USER.md"):
        (tmp_path / name).write_text(f"# {name}\n", encoding="utf-8")
    (tmp_path / "skills").mkdir(exist_ok=True)
    return tmp_path
