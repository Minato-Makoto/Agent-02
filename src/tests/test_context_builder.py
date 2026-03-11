from agentforge.context import ContextBuilder


def test_context_builder_assembles_runtime_tools_and_skills(tmp_path):
    (tmp_path / "IDENTITY.md").write_text("# Identity", encoding="utf-8")
    (tmp_path / "SOUL.md").write_text("# Soul", encoding="utf-8")
    (tmp_path / "AGENT.md").write_text("# Agent", encoding="utf-8")
    (tmp_path / "USER.md").write_text("# User", encoding="utf-8")

    builder = ContextBuilder(str(tmp_path))
    prompt = builder.build_system_prompt(
        skills_xml="<available_skills></available_skills>",
        tool_summaries=[("read_file", "Read a file"), ("list_directory", "List files")],
    )

    assert "## Runtime" in prompt
    assert "## Available Tools" in prompt
    assert "<available_skills></available_skills>" in prompt
    assert "list_directory" in prompt
    assert builder.load_errors == []


def test_context_builder_records_bootstrap_decode_errors(tmp_path):
    (tmp_path / "IDENTITY.md").write_text("# Identity", encoding="utf-8")
    (tmp_path / "SOUL.md").write_text("# Soul", encoding="utf-8")
    (tmp_path / "USER.md").write_text("# User", encoding="utf-8")
    # Invalid UTF-8 to force UnicodeDecodeError
    (tmp_path / "AGENT.md").write_bytes(b"\xff\xfe\x00\x00")

    builder = ContextBuilder(str(tmp_path))
    prompt = builder.build_system_prompt()

    assert "# Identity" in prompt
    assert "# Soul" in prompt
    assert any("Failed to read bootstrap file" in e for e in builder.load_errors)
