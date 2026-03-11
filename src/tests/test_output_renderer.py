from rich.console import Console

from agentforge.model_output_renderer import (
    LaneMarkdown,
    ModelOutputRenderer,
    build_palette,
    detect_theme_mode,
)


def test_detect_theme_mode_override():
    assert detect_theme_mode({"AGENTFORGE_UI_THEME": "dark"}) == "dark"
    assert detect_theme_mode({"AGENTFORGE_UI_THEME": "light"}) == "light"
    assert detect_theme_mode({"AGENTFORGE_UI_THEME": "invalid"}) == "dark"


def test_detect_theme_mode_from_colorfgbg():
    assert detect_theme_mode({"AGENTFORGE_UI_THEME": "auto", "COLORFGBG": "0;15"}) == "light"
    assert detect_theme_mode({"AGENTFORGE_UI_THEME": "auto", "COLORFGBG": "15;0"}) == "dark"


def test_build_palette_returns_mode_specific_defaults():
    dark = build_palette("dark")
    light = build_palette("light")
    assert dark.mode == "dark"
    assert light.mode == "light"
    assert dark.code_theme != light.code_theme


def test_renderer_state_transitions_without_rich():
    renderer = ModelOutputRenderer(
        console=None,
        use_rich=False,
        palette=build_palette("dark"),
    )
    renderer.begin_turn("hello")
    renderer.set_processing()
    renderer.append_reasoning("r1")
    renderer.append_output("ok")
    assert renderer.active is True
    assert renderer.status_state == "thinking"
    assert renderer.reasoning_text == "r1"
    assert renderer.output_text == "ok"

    renderer.finish_success()
    assert renderer.active is False
    assert renderer.status_state == "success"


def test_reasoning_lane_prefix_switches_from_thinking_to_done():
    renderer = ModelOutputRenderer(
        console=None,
        use_rich=False,
        palette=build_palette("dark"),
    )
    renderer.begin_turn("hello")
    renderer.append_reasoning("r1")
    assert renderer._reasoning_prefix_style() == renderer._palette.status_thinking

    renderer.finish_success()
    assert renderer._reasoning_prefix_style() == renderer._palette.lane


def test_output_lane_stays_thinking_color_until_stream_end():
    renderer = ModelOutputRenderer(
        console=None,
        use_rich=False,
        palette=build_palette("dark"),
    )
    renderer.begin_turn("hello")
    renderer.append_reasoning("plan")
    renderer.append_output("partial")

    assert renderer._model_turn_lane_style() == renderer._palette.status_thinking

    renderer.finish_success()

    assert renderer._model_turn_lane_style() == renderer._palette.status_success


def test_finish_success_with_processing_only_marks_live_transient(monkeypatch):
    renderer = ModelOutputRenderer(
        console=None,
        use_rich=True,
        palette=build_palette("dark"),
    )

    class _LiveStub:
        def __init__(self):
            self.transient = False
            self.stopped = False

        def stop(self):
            self.stopped = True

    live = _LiveStub()
    renderer._live = live
    renderer._use_rich = True
    renderer._active = True
    renderer._status_state = "processing"

    renderer.finish_success()

    assert live.transient is True
    assert live.stopped is True


def test_finish_success_with_whitespace_only_marks_live_transient():
    renderer = ModelOutputRenderer(
        console=None,
        use_rich=True,
        palette=build_palette("dark"),
    )

    class _LiveStub:
        def __init__(self):
            self.transient = False
            self.stopped = False

        def stop(self):
            self.stopped = True

    live = _LiveStub()
    renderer._live = live
    renderer._use_rich = True
    renderer._active = True
    renderer._status_state = "processing"
    renderer._output_buffer = "   \n\t  "

    renderer.finish_success()

    assert live.transient is True
    assert live.stopped is True


def test_close_with_processing_only_marks_live_transient():
    renderer = ModelOutputRenderer(
        console=None,
        use_rich=True,
        palette=build_palette("dark"),
    )

    class _LiveStub:
        def __init__(self):
            self.transient = False
            self.stopped = False

        def stop(self):
            self.stopped = True

    live = _LiveStub()
    renderer._live = live
    renderer._use_rich = True
    renderer._active = True
    renderer._status_state = "processing"

    renderer.close()

    assert live.transient is True
    assert live.stopped is True


def test_set_processing_skips_noop_refresh_in_rich_mode(monkeypatch):
    renderer = ModelOutputRenderer(
        console=None,
        use_rich=True,
        palette=build_palette("dark"),
    )
    renderer._active = True
    renderer._use_rich = True
    renderer._status_state = "processing"
    renderer._reasoning_buffer = ""
    renderer._output_buffer = ""
    renderer._error_message = ""

    calls = {"refresh": 0}

    def _count_refresh(*, force=False):
        del force
        calls["refresh"] += 1

    monkeypatch.setattr(renderer, "_refresh", _count_refresh)

    renderer.set_processing()

    assert calls["refresh"] == 0


def test_lane_markdown_quote_codeblock_and_hr_rendering():
    palette = build_palette("dark")
    markdown = LaneMarkdown("> quoted line\n\n---\n\n```text\nprint('x')\n```", palette)
    console = Console(record=True, width=80)
    console.print(markdown)
    text = console.export_text()
    assert "│ quoted line" in text
    assert "---" in text
    assert "╭" not in text and "┌" not in text
    assert "╰" not in text and "└" not in text


def test_code_block_wraps_long_lines_and_keeps_background_style():
    palette = build_palette("dark")
    long_line = "x" * 120
    markdown = LaneMarkdown(f"```text\n{long_line}\n```", palette)

    console = Console(record=True, width=60, force_terminal=True, color_system="truecolor")
    console.print(markdown)

    ansi = console.export_text(styles=True, clear=False)
    plain = console.export_text()

    assert plain.count("x") == 120
    assert "[48;" in ansi
    assert "╭" not in plain and "┌" not in plain
