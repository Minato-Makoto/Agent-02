from agentforge.session import SessionManager


def _new_manager(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    manager = SessionManager(str(sessions_dir))
    manager.new_session()
    return manager


def test_guard_flushes_pending_tool_calls_before_new_assistant_tool_call(tmp_path):
    manager = _new_manager(tmp_path)

    manager.add_assistant_tool_calls(
        [
            {
                "id": "call-1",
                "function": {"name": "read_file", "arguments": {"path": "C:/a.txt"}},
            }
        ]
    )
    manager.add_assistant_tool_calls(
        [
            {
                "id": "call-2",
                "function": {"name": "read_file", "arguments": {"path": "C:/b.txt"}},
            }
        ]
    )

    messages = manager.get_messages()
    assert messages[0].role == "assistant"
    assert messages[0].tool_calls[0]["id"] == "call-1"
    assert messages[1].role == "tool"
    assert messages[1].tool_call_id == "call-1"
    assert messages[1].synthetic is True
    assert messages[2].role == "assistant"
    assert messages[2].tool_calls[0]["id"] == "call-2"


def test_guard_inserts_synthetic_assistant_turn_for_orphan_tool_result(tmp_path):
    manager = _new_manager(tmp_path)

    manager.add_tool_result("orphan-1", "echo_tool", {"ok": True})
    messages = manager.get_messages()

    assert messages[0].role == "assistant"
    assert messages[0].synthetic is True
    assert messages[0].tool_calls[0]["id"] == "orphan-1"
    assert messages[1].role == "tool"
    assert messages[1].tool_call_id == "orphan-1"
    assert messages[1].tool_name == "echo_tool"


def test_guard_flushes_pending_before_plain_message_append(tmp_path):
    manager = _new_manager(tmp_path)
    manager.add_assistant_tool_calls(
        [
            {
                "id": "call-xyz",
                "function": {"name": "noop", "arguments": "{}"},
            }
        ]
    )

    manager.add_message("user", "next turn")
    messages = manager.get_messages()

    assert messages[0].role == "assistant"
    assert messages[1].role == "tool"
    assert messages[1].synthetic is True
    assert messages[1].tool_call_id == "call-xyz"
    assert messages[2].role == "user"
    assert messages[2].content == "next turn"
