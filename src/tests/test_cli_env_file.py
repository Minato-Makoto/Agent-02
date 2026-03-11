import os

from agentforge.cli import _load_env_file


def test_load_env_file_parses_export_and_quotes(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "A=1",
                "export B='two'",
                'C="three four"',
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("A", raising=False)
    monkeypatch.delenv("B", raising=False)
    monkeypatch.delenv("C", raising=False)
    loaded = _load_env_file(str(env_file))

    assert loaded["A"] == "1"
    assert loaded["B"] == "two"
    assert loaded["C"] == "three four"
    assert os.environ["A"] == "1"


def test_load_env_file_does_not_override_existing_when_override_false(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("KEEP=from_file\n", encoding="utf-8")
    monkeypatch.setenv("KEEP", "from_env")

    loaded = _load_env_file(str(env_file), override=False)
    assert loaded["KEEP"] == "from_file"
    assert os.environ["KEEP"] == "from_env"
