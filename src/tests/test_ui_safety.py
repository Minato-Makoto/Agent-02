import sys

import agentforge.ui as ui_module
from rich.console import Console
from agentforge.ui import ChatUI


def test_ui_sanitize_replaces_unencodable_text():
    ui = ChatUI(verbose=False)
    ui._encoding = "ascii"
    out = ui._sanitize("ok🙂")
    assert "ok" in out


def test_ui_stream_lifecycle_resets_internal_state():
    ui = ChatUI(verbose=False)
    ui.stream_start()
    ui.stream_reasoning("r")
    ui.stream_token("a")
    ui.stream_end()
    assert ui._phase == "idle"
    assert ui._dim_active is False


def test_ui_error_closes_active_lane():
    ui = ChatUI(verbose=False)
    ui._last_user_input = "hello"
    ui.thinking_start()
    ui.stream_reasoning("x")
    ui.error("boom")
    assert ui._phase == "idle"
    assert ui._renderer.active is False


def test_ui_does_not_echo_user_input_in_output_lane():
    ui = ChatUI(verbose=False)
    ui._last_user_input = "secret prompt"
    ui.thinking_start()
    ui.stream_reasoning("plan")
    ui.stream_token("done")

    assert "secret prompt" not in ui._renderer.reasoning_text
    assert "secret prompt" not in ui._renderer.output_text


def test_chatui_rich_console_does_not_enable_soft_wrap(monkeypatch):
    class _FakeConsole:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs
            self.file = sys.stdout

        def push_theme(self, theme):
            del theme

    monkeypatch.setattr(ui_module, "HAS_RICH", True)
    monkeypatch.setattr(ui_module, "Console", _FakeConsole)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)

    ui = ChatUI(verbose=False)
    assert ui._use_rich is True
    assert isinstance(ui.console, _FakeConsole)
    assert "soft_wrap" not in ui.console.kwargs


def test_goodbye_does_not_emit_leading_blank_line(monkeypatch):
    ui = ChatUI(verbose=False)
    emitted = []

    monkeypatch.setattr(ui, "_emit", lambda *args, **kwargs: emitted.append(("emit", args, kwargs)))
    monkeypatch.setattr(
        ui,
        "_emit_branch",
        lambda prefix, message, **kwargs: emitted.append(("branch", prefix, message, kwargs)),
    )

    ui.goodbye()
    assert emitted
    first = emitted[0]
    assert first[0] == "branch"
    assert first[1] == "└─ "
    assert first[2] == "session terminated."


def test_tool_call_stream_formatter_prettifies_complete_json():
    ui = ChatUI(verbose=False)
    rendered = ui._format_tool_call_stream_content('{"path":"workspace/AGENT.md","mode":"read"}')
    assert "\n" in rendered
    assert '"path": "workspace/AGENT.md"' in rendered


def test_tool_call_stream_formatter_keeps_partial_json_raw():
    ui = ChatUI(verbose=False)
    raw = '{"path":"workspace/AGENT.md"'
    rendered = ui._format_tool_call_stream_content(raw)
    assert rendered == raw


def test_tool_call_live_uses_crop_vertical_overflow(monkeypatch):
    captured = {"kwargs": {}, "started": 0}

    class _FakeConsole:
        def __init__(self, *args, **kwargs):
            del args, kwargs
            self.file = sys.stdout

        def push_theme(self, theme):
            del theme

        def print(self, *args, **kwargs):
            del args, kwargs

    class _FakeLive:
        def __init__(self, renderable, **kwargs):
            del renderable
            captured["kwargs"] = kwargs

        def start(self):
            captured["started"] += 1

        def update(self, renderable, refresh):
            del renderable, refresh

        def stop(self):
            return None

    monkeypatch.setattr(ui_module, "HAS_RICH", True)
    monkeypatch.setattr(ui_module, "Console", _FakeConsole)
    monkeypatch.setattr(ui_module, "Live", _FakeLive)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)

    ui = ChatUI(verbose=False)
    ui.tool_call_stream_start("read_file")

    assert captured["started"] == 1
    assert captured["kwargs"]["vertical_overflow"] == "crop"
    assert ui._tool_call_stream_prefix_style == ui.palette.status_thinking


def test_tool_call_stream_start_styles_title_lane_as_thinking(monkeypatch):
    ui = ChatUI(verbose=False)
    emitted = []

    monkeypatch.setattr(
        ui,
        "_emit_branch",
        lambda prefix, message, **kwargs: emitted.append((prefix, message, kwargs)),
    )

    ui.tool_call_stream_start("write_file")

    assert emitted
    prefix, message, kwargs = emitted[0]
    assert prefix == "├─ "
    assert message == "tool: write_file"
    assert kwargs.get("prefix_style") == ui.palette.status_thinking


def test_tool_call_live_preview_tracks_tail_lines():
    ui = ChatUI(verbose=False)

    class _FakeConsole:
        class _Size:
            height = 12

        size = _Size()

    ui.console = _FakeConsole()
    text = "\n".join(f"line {idx}" for idx in range(20))
    preview = ui._tool_call_live_preview_content(text)

    assert preview.startswith("line 12")
    assert preview.endswith("line 19")
    assert "line 0" not in preview


def test_tool_call_live_refresh_throttles_rapid_updates(monkeypatch):
    ui = ChatUI(verbose=False)
    ui._tool_call_stream_buffer = '{"x": 1}'

    class _LiveStub:
        def __init__(self):
            self.calls = 0

        def update(self, renderable, refresh):
            del renderable, refresh
            self.calls += 1

        def stop(self):
            return None

    live = _LiveStub()
    ui._tool_call_stream_live = live

    ticks = iter([10.0, 10.001, 10.2])
    monkeypatch.setattr("agentforge.ui.time.perf_counter", lambda: next(ticks))

    ui._tool_call_stream_dirty = True
    ui._refresh_tool_call_live()
    ui._tool_call_stream_dirty = True
    ui._refresh_tool_call_live()
    ui._tool_call_stream_dirty = True
    ui._refresh_tool_call_live()

    assert live.calls == 2


def test_tool_call_live_tail_for_single_line_payload():
    ui = ChatUI(verbose=False)

    class _FakeConsole:
        class _Size:
            width = 80
            height = 20

        size = _Size()

    ui.console = _FakeConsole()
    long_line = "".join(f"{i:04d}" for i in range(2000))

    preview = ui._tool_call_live_preview_content(long_line)
    budget = ui._tool_call_live_single_line_char_budget(reserve_lines=4)

    assert len(preview) == budget
    expected_start = ((len(long_line) - budget) // 64) * 64
    assert preview == long_line[expected_start : expected_start + budget]


def test_tool_call_stream_end_transitions_prefix_to_success(monkeypatch):
    ui = ChatUI(verbose=False)
    ui._tool_call_stream_open = True
    ui._tool_call_stream_live = object()
    captured = {"stopped": False}

    monkeypatch.setattr(
        ui,
        "_stop_tool_call_live",
        lambda: captured.__setitem__("stopped", True),
    )

    ui.tool_call_stream_end()

    assert captured["stopped"] is True
    assert ui._tool_call_stream_prefix_style == ui.palette.status_success


def test_tool_call_live_final_flush_renders_full_block_once():
    ui = ChatUI(verbose=False)
    ui._tool_call_stream_buffer = '{"path":"workspace/AGENT.md"}'
    ui._tool_call_stream_live_show_full = True
    ui._tool_call_stream_dirty = True

    class _LiveStub:
        def __init__(self):
            self.updates = []
            self.stopped = False

        def update(self, renderable, refresh):
            self.updates.append((renderable, refresh))

        def stop(self):
            self.stopped = True

    live = _LiveStub()
    ui._tool_call_stream_live = live
    ui._stop_tool_call_live()

    assert live.stopped is True
    assert live.updates

    renderable, refresh = live.updates[-1]
    assert refresh is True

    console = Console(record=True, width=120)
    console.print(renderable)
    text = console.export_text()
    assert '"path": "workspace/AGENT.md"' in text


def test_tool_call_display_normalizes_escaped_newlines():
    ui = ChatUI(verbose=False)
    raw = '{"content":"line1\\\\nline2\\\\nline3\\\\nline4\\\\nline5\\\\nline6\\\\nline7\\\\nline8\\\\nline9"}'

    out = ui._normalize_tool_stream_display_content(raw)

    assert "line1\nline2" in out


def test_tool_call_display_normalizes_doubly_escaped_newlines():
    ui = ChatUI(verbose=False)
    raw = (
        '{"content":"line1\\\\\\\\nline2\\\\\\\\nline3\\\\\\\\nline4\\\\\\\\nline5\\\\\\\\n'
        'line6\\\\\\\\nline7\\\\\\\\nline8\\\\\\\\nline9"}'
    )

    out = ui._normalize_tool_stream_display_content(raw)

    assert "line1\nline2" in out
    assert "\\\n" not in out


def test_ensure_stream_closed_uses_finish_success_not_close(monkeypatch):
    ui = ChatUI(verbose=False)
    ui._renderer._active = True
    calls = {"finish": 0, "close": 0}

    monkeypatch.setattr(
        ui._renderer,
        "finish_success",
        lambda: calls.__setitem__("finish", calls["finish"] + 1),
    )
    monkeypatch.setattr(
        ui._renderer,
        "close",
        lambda: calls.__setitem__("close", calls["close"] + 1),
    )

    ui._ensure_stream_closed()

    assert calls["finish"] == 1
    assert calls["close"] == 0
