from agentforge.skills import SkillLoader


def test_skill_loader_discovers_skill_md_with_folder_id(minimal_workspace):
    skill_dir = minimal_workspace / "skills" / "file_ops"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: file_ops
description: file tools
tools:
  - list_directory
module: builtin_tools.file_ops
---
# file ops
""",
        encoding="utf-8",
    )

    loader = SkillLoader(str(minimal_workspace))
    discovered = loader.discover()
    assert "file_ops" in discovered
    skill = discovered["file_ops"]
    assert skill.skill_id == "file_ops"
    assert skill.name == "file_ops"
    assert skill.skill_file.endswith("SKILL.md")


def test_skill_loader_warns_when_name_mismatches_folder(minimal_workspace, caplog):
    skill_dir = minimal_workspace / "skills" / "my_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        """---
name: Pretty Skill
description: display name differs from id
tools:
  - list_directory
module: builtin_tools.file_ops
---
# my skill
""",
        encoding="utf-8",
    )

    loader = SkillLoader(str(minimal_workspace))
    with caplog.at_level("WARNING"):
        discovered = loader.discover()

    assert "my_skill" in discovered
    assert loader.get_skill("my_skill") is discovered["my_skill"]
    assert loader.get_skill("Pretty Skill") is discovered["my_skill"]
    assert "Skill name/id mismatch" in caplog.text

