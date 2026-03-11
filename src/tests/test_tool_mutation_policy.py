from agentforge.tool_mutation import is_mutating_tool_call


def test_read_only_tool_is_not_mutating():
    assert is_mutating_tool_call("read_file", {"path": "C:/tmp/a.txt"}) is False


def test_write_file_is_mutating():
    assert is_mutating_tool_call("write_file", {"path": "C:/tmp/a.txt", "content": "ship it"}) is True


def test_process_poll_action_is_not_mutating():
    assert is_mutating_tool_call("process", {"action": "status"}) is False


def test_process_kill_action_is_mutating():
    assert is_mutating_tool_call("process", {"action": "kill"}) is True


def test_desktop_screenshot_is_read_only():
    assert is_mutating_tool_call("desktop_screenshot", {}) is False


def test_desktop_click_is_mutating():
    assert is_mutating_tool_call("desktop_click", {"x": 10, "y": 20}) is True
