from agentforge.contracts import ToolCall
from agentforge.prompting import PromptBuilder


def test_prompt_builder_builds_structured_tool_messages():
    prompt = PromptBuilder()
    prompt.set_system("system")
    prompt.add_user("user asks")
    prompt.add_assistant_tool_calls(
        [ToolCall(id="call_1", name="list_directory", arguments={"path": "workspace"})],
        content="",
    )
    prompt.add_tool_result("call_1", "list_directory", {"items": ["a.txt"]})
    messages = prompt.build_messages(include_system=True)

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "assistant"
    assert "tool_calls" in messages[2]
    assert messages[3]["role"] == "tool"
    assert messages[3]["tool_call_id"] == "call_1"


def test_prompt_builder_truncate_reduces_message_count():
    prompt = PromptBuilder()
    prompt.set_system("sys")
    for i in range(20):
        prompt.add_user("u" * 200)
        prompt.add_assistant("a" * 200)

    before = prompt.count
    prompt.truncate(max_tokens=100, chars_per_token=1)
    after = prompt.count

    assert after < before
