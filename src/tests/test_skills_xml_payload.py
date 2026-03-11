from agentforge.skills import SkillLoader


def test_skills_xml_contains_id_location_and_status(minimal_workspace):
    skill_dir = minimal_workspace / "skills" / "web_search"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        """---
name: web_search
description: search
tools:
  - web_search
module: builtin_tools.web_search
---
# web search
""",
        encoding="utf-8",
    )

    loader = SkillLoader(str(minimal_workspace))
    loader.discover()
    xml = loader.build_skills_xml()

    assert "<id>web_search</id>" in xml
    assert "<name>web_search</name>" in xml
    assert f"<location>{skill_file.resolve()}</location>" in xml
    assert "<status>LOCKED</status>" in xml

    loader.activate("web_search")
    xml_active = loader.build_skills_xml()
    assert "<status>ACTIVE</status>" in xml_active
    assert "<tools>web_search</tools>" in xml_active
