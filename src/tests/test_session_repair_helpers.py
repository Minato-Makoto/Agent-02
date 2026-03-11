from agentforge.session_repair import normalize_tool_calls, repair_session_messages


def test_normalize_tool_calls_trims_blank_string_arguments():
    raw = [
        {
            "id": "call-1",
            "function": {"name": "read_file", "arguments": "   "},
        }
    ]
    out = normalize_tool_calls(raw)
    assert out[0]["function"]["arguments"] == "{}"


def test_repair_session_messages_adds_synthetic_tool_for_pending_call():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "function": {"name": "noop", "arguments": "{}"}}],
        }
    ]
    out = repair_session_messages(messages)
    assert len(out) == 2
    assert out[1]["role"] == "tool"
    assert out[1]["tool_call_id"] == "call-1"
    assert out[1]["synthetic"] is True
