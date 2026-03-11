from pathlib import Path

from agentforge.agent_core import Agent, AgentConfig
from agentforge.contracts import ChatCompletionResult
from agentforge.skills import SkillLoader
from agentforge.tools import ToolRegistry


class _DummyLLM:
    def __init__(self):
        self.capabilities = type("Caps", (), {"supports_tools": True})()

    def chat_completion(self, **kwargs):
        return ChatCompletionResult(content="ok")


def _write_skill_file(path: Path) -> Path:
    skill_dir = path / "skills" / "file_ops"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        """---
name: File Ops
description: File operations
tools:
  - list_directory
module: builtin_tools.file_ops
---
# File Ops skill
""",
        encoding="utf-8",
    )
    return skill_file


def test_skill_is_unavailable_until_activation_then_unlocked(minimal_workspace):
    skill_file = _write_skill_file(minimal_workspace)
    loader = SkillLoader(str(minimal_workspace))
    discovered = loader.discover()
    assert "file_ops" in discovered

    registry = ToolRegistry()
    agent = Agent(
        config=AgentConfig(
            max_iterations=2,
            max_repeats=3,
            timeout=30.0,
            workspace_dir=str(minimal_workspace),
        ),
        llm=_DummyLLM(),
        tools=registry,
        skill_loader=loader,
    )

    before = agent.tool_loop.execute_tool("list_directory", {"path": str(minimal_workspace)})
    assert before.success is False
    assert "not found" in before.error

    read_file_tool = registry.find("read_file")
    assert read_file_tool is not None
    read_result = read_file_tool.execute({"path": str(skill_file)})
    assert read_result.success is True
    assert registry.has("list_directory")
    after = agent.tool_loop.execute_tool("list_directory", {"path": str(minimal_workspace)})
    assert after.success is True
    assert isinstance(after.output, list)


def test_skill_full_flow_discover_activate_register_execute_deactivate(minimal_workspace):
    skill_file = _write_skill_file(minimal_workspace)
    loader = SkillLoader(str(minimal_workspace))
    discovered = loader.discover()
    assert "file_ops" in discovered

    registry = ToolRegistry()
    agent = Agent(
        config=AgentConfig(
            max_iterations=2,
            max_repeats=3,
            timeout=30.0,
            workspace_dir=str(minimal_workspace),
        ),
        llm=_DummyLLM(),
        tools=registry,
        skill_loader=loader,
    )

    # activate + register via read_file bootstrap flow
    read_file_tool = registry.find("read_file")
    assert read_file_tool is not None
    assert read_file_tool.execute({"path": str(skill_file)}).success is True
    assert registry.has("list_directory") is True

    executed = agent.tool_loop.execute_tool("list_directory", {"path": str(minimal_workspace)})
    assert executed.success is True
    assert isinstance(executed.output, list)

    # deactivate + unregister
    loader.deactivate("file_ops")
    registry.unregister_skill("file_ops")
    assert loader.get_skill("file_ops") is not None
    assert loader.get_skill("file_ops").active is False
    assert registry.has("list_directory") is False

    blocked = agent.tool_loop.execute_tool("list_directory", {"path": str(minimal_workspace)})
    assert blocked.success is False
    assert "not found" in blocked.error
