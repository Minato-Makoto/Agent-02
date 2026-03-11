import json

from agentforge.agent_core import Agent, AgentConfig
from agentforge.contracts import ChatCompletionResult
from agentforge.session import SessionManager
from agentforge.summarizer import Summarizer
from agentforge.tools import ToolRegistry


class _CaptureLLM:
    def __init__(self):
        self.capabilities = type("Caps", (), {"supports_tools": True})()
        self.last_messages = []

    def chat_completion(self, messages, **kwargs):
        del kwargs
        self.last_messages = list(messages)
        return ChatCompletionResult(content="ok")


class _SummarizingLLM:
    def __init__(self):
        self.capabilities = type("Caps", (), {"supports_tools": True})()
        self.last_messages = []
        self.summary_prompts = []

    def generate(self, prompt, **kwargs):
        del kwargs
        self.summary_prompts.append(prompt)
        return (
            "Goal: continue prior task.\n"
            "Decisions made: keep session continuity.\n"
            "File/tool state: no pending writes.\n"
            "Pending work: answer latest user turn.\n"
            "Constraints and risks: preserve transcript linkage."
        )

    def chat_completion(self, messages, **kwargs):
        del kwargs
        self.last_messages = list(messages)
        return ChatCompletionResult(content="continued")


class _SummaryCompletionFallbackLLM:
    def __init__(self):
        self.capabilities = type("Caps", (), {"supports_tools": True})()
        self.last_messages = []
        self.generate_prompts = []
        self.summary_chat_calls = 0

    def generate(self, prompt, **kwargs):
        del kwargs
        self.generate_prompts.append(prompt)
        return "[Error: completion endpoint unavailable]"

    def chat_completion(self, messages, **kwargs):
        del kwargs
        self.last_messages = list(messages)
        if (
            len(messages) == 2
            and str(messages[0].get("role", "")) == "system"
            and "continuation summary" in str(messages[0].get("content", "")).lower()
        ):
            self.summary_chat_calls += 1
            return ChatCompletionResult(
                content=(
                    "Goal: continue current task.\n"
                    "Decisions made: keep same session continuity.\n"
                    "File/tool state: files already generated.\n"
                    "Pending work: process latest user turn.\n"
                    "Constraints and risks: preserve transcript linkage."
                )
            )
        return ChatCompletionResult(content="continued")


def _seed_long_session(manager: SessionManager) -> str:
    session = manager.new_session()
    for idx in range(6):
        manager.add_message("user", f"user-{idx} " + ("x" * 80))
        manager.add_message("assistant", f"assistant-{idx} " + ("y" * 80))
    return session.id


def test_agent_hydrates_prompt_from_loaded_session(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    first_mgr = SessionManager(str(sessions_dir))
    first = first_mgr.new_session()
    first_mgr.add_message("user", "history user")
    first_mgr.add_message("assistant", "history assistant")

    second_mgr = SessionManager(str(sessions_dir))
    loaded = second_mgr.load_session(first.id)
    assert loaded is not None

    llm = _CaptureLLM()
    agent = Agent(
        config=AgentConfig(max_iterations=2, max_repeats=2, timeout=30.0, workspace_dir=str(tmp_path)),
        llm=llm,
        tools=ToolRegistry(),
        session_mgr=second_mgr,
    )

    result = agent.run("new turn")
    assert result == "ok"
    assert any(m.get("role") == "user" and m.get("content") == "history user" for m in llm.last_messages)
    assert any(
        m.get("role") == "assistant" and m.get("content") == "history assistant"
        for m in llm.last_messages
    )


def test_graceful_summary_keeps_same_session_id_and_compacts_in_place(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session_mgr = SessionManager(str(sessions_dir))
    old_id = _seed_long_session(session_mgr)

    llm = _SummarizingLLM()
    agent = Agent(
        config=AgentConfig(max_iterations=2, max_repeats=2, timeout=30.0, workspace_dir=str(tmp_path)),
        llm=llm,
        tools=ToolRegistry(),
        session_mgr=session_mgr,
        summarizer=Summarizer(max_tokens=64),
    )

    result = agent.run("trigger summarization")
    assert result == "continued"
    assert llm.summary_prompts
    assert session_mgr.session is not None
    assert session_mgr.session.id == old_id
    assert session_mgr.session.previous_session_id == ""
    assert (sessions_dir / f"{session_mgr.session.id}.json").exists()
    assert any(
        m.get("role") == "system" and "context memory note" in str(m.get("content", "")).lower()
        for m in llm.last_messages
    )
    assert any(m.get("role") == "user" and m.get("content") == "trigger summarization" for m in llm.last_messages)

    old_payload = json.loads((sessions_dir / f"{old_id}.json").read_text(encoding="utf-8"))
    assert old_payload.get("summary", "").strip() != ""
    assert old_payload.get("metadata", {}).get("last_compaction") == "graceful"


def test_graceful_compaction_injects_context_memory_system_message(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session_mgr = SessionManager(str(sessions_dir))
    old_id = _seed_long_session(session_mgr)

    agent = Agent(
        config=AgentConfig(max_iterations=2, max_repeats=2, timeout=30.0, workspace_dir=str(tmp_path)),
        llm=_SummarizingLLM(),
        tools=ToolRegistry(),
        session_mgr=session_mgr,
        summarizer=Summarizer(max_tokens=64),
    )

    _ = agent.run("trigger summarization")
    assert session_mgr.session is not None
    first_message = session_mgr.session.messages[0]
    assert first_message.role == "system"
    assert "context memory note" in first_message.content.lower()
    assert session_mgr.session.id == old_id


def test_graceful_summary_uses_chat_fallback_when_completion_summary_fails(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session_mgr = SessionManager(str(sessions_dir))
    _seed_long_session(session_mgr)

    llm = _SummaryCompletionFallbackLLM()
    agent = Agent(
        config=AgentConfig(max_iterations=2, max_repeats=2, timeout=30.0, workspace_dir=str(tmp_path)),
        llm=llm,
        tools=ToolRegistry(),
        session_mgr=session_mgr,
        summarizer=Summarizer(max_tokens=64),
    )

    result = agent.run("trigger summarization")
    assert result == "continued"
    assert llm.generate_prompts
    assert llm.summary_chat_calls == 1
    assert session_mgr.session is not None
    assert "Goal: continue current task." in session_mgr.session.summary
    assert "[Compressed" not in session_mgr.session.summary
