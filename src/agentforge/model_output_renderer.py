"""
Model output renderer for the legacy tree-lane console surface.

Responsibilities:
- Detect effective UI theme mode (auto/dark/light)
- Build palette used by terminal rendering
- Render processing/thinking/output states as a minimal lane:
  - status line starts with `├─`
  - assistant block starts with `├─`
- Stream markdown output in realtime with Rich Live updates
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass
from typing import Mapping, Optional

from rich.console import Console, Group, RenderResult, RenderableType
from rich.live import Live
from rich.markdown import BlockQuote, CodeBlock, Heading, HorizontalRule, Markdown
from rich.padding import Padding
from rich.segment import Segment
from rich.text import Text
from rich.theme import Theme


THEME_MODE_AUTO = "auto"
THEME_MODE_DARK = "dark"
THEME_MODE_LIGHT = "light"

_LIVE_REFRESH_INTERVAL_SECONDS = 1 / 24
_LIVE_PREVIEW_MAX_CHARS = 12_000
_LIVE_PREVIEW_MIN_LINES = 8
_LIVE_PREVIEW_MAX_LINES = 160


def detect_theme_mode(env: Optional[Mapping[str, str]] = None) -> str:
    """Detect UI theme mode with env override support."""
    source = env if env is not None else os.environ

    override = str(source.get("AGENTFORGE_UI_THEME", "")).strip().lower()
    if override in (THEME_MODE_DARK, THEME_MODE_LIGHT):
        return override
    if override and override != THEME_MODE_AUTO:
        return THEME_MODE_DARK

    colorfgbg = str(source.get("COLORFGBG", "")).strip()
    if colorfgbg:
        parts = colorfgbg.split(";")
        if parts:
            try:
                background_idx = int(parts[-1])
                # Conventional terminal palette: low indexes are dark backgrounds.
                return THEME_MODE_LIGHT if background_idx >= 8 else THEME_MODE_DARK
            except ValueError:
                pass

    term = " ".join(
        str(source.get(key, "")).strip().lower()
        for key in ("TERM", "COLORTERM", "TERM_PROGRAM")
    )
    if "light" in term:
        return THEME_MODE_LIGHT
    if "dark" in term:
        return THEME_MODE_DARK

    # Windows Terminal is overwhelmingly used with dark themes by default.
    if str(source.get("WT_SESSION", "")).strip():
        return THEME_MODE_DARK

    return THEME_MODE_DARK


@dataclass(frozen=True)
class UIPalette:
    mode: str
    code_theme: str
    lane: str
    status_processing: str
    status_thinking: str
    status_success: str
    status_error: str
    assistant: str
    reasoning_text: str
    text: str
    hint: str
    banner: str
    tool_title: str
    tool_body: str
    result_title: str
    result_body: str
    markdown_inline_code: str
    markdown_em: str
    markdown_strong: str
    markdown_heading_h1: str
    markdown_heading_h2: str
    markdown_heading_h3: str
    markdown_quote_bar: str
    markdown_quote_text: str
    markdown_code_border: str
    markdown_code_background: str
    markdown_code_text: str


def build_palette(mode: str) -> UIPalette:
    """Build palette for dark/light mode."""
    normalized = mode if mode in (THEME_MODE_DARK, THEME_MODE_LIGHT) else THEME_MODE_DARK
    if normalized == THEME_MODE_LIGHT:
        return UIPalette(
            mode=THEME_MODE_LIGHT,
            code_theme="friendly",
            lane="bold #1f7f3e",
            status_processing="bold #9a6700",
            status_thinking="bold #9a6700",
            status_success="bold #1f7f3e",
            status_error="bold #cf222e",
            assistant="bold #1f7f3e",
            reasoning_text="dim",
            text="#2f2f2f",
            hint="#6c727f",
            banner="bold #1f7f3e",
            tool_title="bold #9a6700",
            tool_body="#6c727f",
            result_title="bold #1f7f3e",
            result_body="#6c727f",
            markdown_inline_code="#2f2f2f on #e8e8e8",
            markdown_em="italic #6c727f",
            markdown_strong="bold #2f2f2f",
            markdown_heading_h1="bold",
            markdown_heading_h2="bold",
            markdown_heading_h3="bold",
            markdown_quote_bar="#1f7f3e",
            markdown_quote_text="#6c727f",
            markdown_code_border="",
            markdown_code_background="on #e8e8e8",
            markdown_code_text="dim #2f2f2f",
        )
    return UIPalette(
        mode=THEME_MODE_DARK,
        code_theme="monokai",
        lane="bold #38c172",
        status_processing="bold #d6b045",
        status_thinking="bold #d6b045",
        status_success="bold #38c172",
        status_error="bold #e05d5d",
        assistant="bold #38c172",
        reasoning_text="dim",
        text="#d0d0d0",
        hint="#8a8a8a",
        banner="bold #38c172",
        tool_title="bold #d6b045",
        tool_body="#8a8a8a",
        result_title="bold #38c172",
        result_body="#8a8a8a",
        markdown_inline_code="#c8c8c8 on #262626",
        markdown_em="italic #8a8a8a",
        markdown_strong="bold #d0d0d0",
        markdown_heading_h1="bold",
        markdown_heading_h2="bold",
        markdown_heading_h3="bold",
        markdown_quote_bar="#38c172",
        markdown_quote_text="#8a8a8a",
        markdown_code_border="",
        markdown_code_background="on #262626",
        markdown_code_text="dim #c8c8c8",
    )


class LaneRenderable:
    """Prefix every rendered line with lane marker."""

    def __init__(
        self,
        renderable: RenderableType,
        *,
        prefix: str = "│ ",
        prefix_style: str = "",
        content_style: str = "",
    ) -> None:
        self._renderable = renderable
        self._prefix = prefix
        self._prefix_style = prefix_style
        self._content_style = content_style

    def __rich_console__(self, console: Console, options) -> RenderResult:
        render_width = max(12, options.max_width - len(self._prefix))
        render_options = options.update(width=render_width, height=None)
        content_style = console.get_style(self._content_style, default="")
        prefix_style = console.get_style(self._prefix_style, default="")
        lines = console.render_lines(self._renderable, render_options, style=content_style)
        for line in lines:
            yield Segment(self._prefix, prefix_style)
            yield from line
            yield Segment.line()


def build_markdown_theme(palette: UIPalette) -> Theme:
    """Theme entries consumed by Rich markdown for inline styles."""
    return Theme(
        {
            "markdown.code": palette.markdown_inline_code,
            "markdown.em": palette.markdown_em,
            "markdown.strong": palette.markdown_strong,
            "markdown.link": "underline",
            "markdown.link_url": palette.hint,
            "markdown.item.bullet": palette.lane,
        }
    )


class LaneHeading(Heading):
    """Heading element aligned with tree-lane visual style."""

    @classmethod
    def create(cls, markdown: Markdown, token) -> "LaneHeading":
        palette = getattr(markdown, "palette", build_palette(THEME_MODE_DARK))
        return cls(token.tag, palette)

    def __init__(self, tag: str, palette: UIPalette) -> None:
        self.palette = palette
        super().__init__(tag)

    def __rich_console__(self, console: Console, options) -> RenderResult:
        raw = self.text.plain
        if self.tag == "h1":
            text = Text(raw.upper(), style=self.palette.markdown_heading_h1)
            yield Text("")
            yield text
            yield Text("")
            return
        if self.tag == "h2":
            text = Text(raw, style=self.palette.markdown_heading_h2)
            yield Text("")
            yield text
            return
        text = Text(raw, style=self.palette.markdown_heading_h3)
        yield text


class LaneCodeBlock(CodeBlock):
    """Code block with monochrome dim gray background (no box frame)."""

    @classmethod
    def create(cls, markdown: Markdown, token) -> "LaneCodeBlock":
        node_info = token.info or ""
        lexer_name = node_info.partition(" ")[0]
        palette = getattr(markdown, "palette", build_palette(THEME_MODE_DARK))
        return cls(lexer_name or "text", markdown.code_theme, palette)

    def __init__(self, lexer_name: str, theme: str, palette: UIPalette) -> None:
        super().__init__(lexer_name, theme)
        self.palette = palette

    def __rich_console__(self, console: Console, options) -> RenderResult:
        code = str(self.text).rstrip()
        code_style = f"{self.palette.markdown_code_text} {self.palette.markdown_code_background}".strip()
        code_text = Text(
            code,
            style=code_style,
            no_wrap=False,
            overflow="fold",
        )
        yield Padding(code_text, (0, 1), style=self.palette.markdown_code_background)


class LaneBlockQuote(BlockQuote):
    """Block quote with IDE-like vertical lane marker."""

    @classmethod
    def create(cls, markdown: Markdown, token) -> "LaneBlockQuote":
        palette = getattr(markdown, "palette", build_palette(THEME_MODE_DARK))
        return cls(palette)

    def __init__(self, palette: UIPalette) -> None:
        super().__init__()
        self.palette = palette

    def __rich_console__(self, console: Console, options) -> RenderResult:
        render_options = options.update(width=max(12, options.max_width - 4))
        quote_style = console.get_style(self.palette.markdown_quote_text, default="dim")
        lines = console.render_lines(self.elements, render_options, style=quote_style)
        bar_style = console.get_style(self.palette.markdown_quote_bar, default=quote_style)
        lane = Segment("│ ", bar_style)
        new_line = Segment("\n")
        for line in lines:
            yield lane
            yield from line
            yield new_line


class LaneHorizontalRule(HorizontalRule):
    """Render markdown hr as literal text separator (`---`)."""

    @classmethod
    def create(cls, markdown: Markdown, token) -> "LaneHorizontalRule":
        palette = getattr(markdown, "palette", build_palette(THEME_MODE_DARK))
        return cls(palette)

    def __init__(self, palette: UIPalette) -> None:
        super().__init__()
        self.palette = palette

    def __rich_console__(self, console: Console, options) -> RenderResult:
        del console, options
        yield Text("---", style=self.palette.hint)


class LaneMarkdown(Markdown):
    """Markdown renderer customized for the tree-lane console surface."""

    elements = dict(Markdown.elements)
    elements.update(
        {
            "heading_open": LaneHeading,
            "fence": LaneCodeBlock,
            "code_block": LaneCodeBlock,
            "blockquote_open": LaneBlockQuote,
            "hr": LaneHorizontalRule,
        }
    )

    def __init__(self, markup: str, palette: UIPalette) -> None:
        self.palette = palette
        super().__init__(
            markup=markup,
            code_theme=palette.code_theme,
            style=palette.text,
            inline_code_theme=palette.code_theme,
        )


class ModelOutputRenderer:
    """Render model processing/thinking/output as a tree-lane stream."""

    def __init__(
        self,
        *,
        console: Optional[Console],
        use_rich: bool,
        palette: UIPalette,
    ) -> None:
        self._console = console
        self._use_rich = bool(use_rich and console is not None)
        self._palette = palette
        self._live: Optional[Live] = None

        self._active = False
        self._status_state = "idle"  # idle|processing|thinking|success|error
        self._reasoning_buffer = ""
        self._output_buffer = ""
        self._error_message = ""

        self._plain_reasoning_started = False
        self._plain_output_started = False
        self._plain_processing_emitted = False
        self._plain_reasoning_line_open = False
        self._plain_output_line_open = False
        self._plain_reasoning_col = 0
        self._plain_output_col = 0

        self._last_live_refresh_at = 0.0
        self._live_show_full_output = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def status_state(self) -> str:
        return self._status_state

    @property
    def reasoning_text(self) -> str:
        return self._reasoning_buffer

    @property
    def output_text(self) -> str:
        return self._output_buffer

    @property
    def error_message(self) -> str:
        return self._error_message

    def begin_turn(self, user_input: str) -> None:
        del user_input
        self.close()
        self._active = True
        self._status_state = "processing"
        self._reasoning_buffer = ""
        self._output_buffer = ""
        self._error_message = ""
        self._plain_reasoning_started = False
        self._plain_output_started = False
        self._plain_processing_emitted = False
        self._plain_reasoning_line_open = False
        self._plain_output_line_open = False
        self._plain_reasoning_col = 0
        self._plain_output_col = 0
        self._last_live_refresh_at = 0.0
        self._live_show_full_output = False
        if self._use_rich:
            self._start_live()
            self._refresh(force=True)

    def set_processing(self) -> None:
        if not self._active:
            return
        if (
            self._status_state == "processing"
            and not self._reasoning_buffer
            and not self._output_buffer
            and not self._error_message
        ):
            # Skip no-op processing refreshes to avoid status-lane repaint artifacts
            # on terminals that append Live frames while auto-scrolling.
            if self._use_rich:
                return
            if self._plain_processing_emitted:
                return
        self._status_state = "processing"
        self._refresh(force=True)
        if not self._use_rich and not self._plain_reasoning_started and not self._plain_output_started:
            self._plain_status("processing...", self._status_style())
            self._plain_processing_emitted = True

    def append_reasoning(self, token: str) -> None:
        normalized = self._normalize_token(token)
        if not normalized:
            return
        if not self._active:
            self.begin_turn("")
        self._status_state = "thinking"
        self._reasoning_buffer += normalized
        self._plain_processing_emitted = False
        self._refresh()
        if not self._use_rich:
            if not self._plain_reasoning_started:
                print("│   ", end="", flush=True)
                self._plain_reasoning_started = True
                self._plain_reasoning_line_open = True
            self._plain_write_with_lane(
                normalized,
                lane_prefix="│   ",
                line_open_attr="_plain_reasoning_line_open",
                line_col_attr="_plain_reasoning_col",
            )

    def append_output(self, token: str) -> None:
        normalized = self._normalize_token(token)
        if not normalized:
            return
        if not self._active:
            self.begin_turn("")
        self._output_buffer += normalized
        self._plain_processing_emitted = False
        self._refresh()
        if not self._use_rich:
            if not self._plain_output_started:
                if self._plain_reasoning_line_open:
                    print("", flush=True)
                    self._plain_reasoning_line_open = False
                print("├─ Agent-02", flush=True)
                print("│ ", end="", flush=True)
                self._plain_output_started = True
                self._plain_output_line_open = True
            self._plain_write_with_lane(
                normalized,
                lane_prefix="│ ",
                line_open_attr="_plain_output_line_open",
                line_col_attr="_plain_output_col",
            )

    def finish_success(self) -> None:
        if not self._active:
            return
        had_visible_content = bool(self._reasoning_buffer.strip() or self._output_buffer.strip())
        self._status_state = "success"
        self._live_show_full_output = had_visible_content
        if had_visible_content:
            self._refresh(force=True)
        elif self._live is not None:
            # Avoid leaving repeated static `processing...` lines when turns
            # contain no streamed reasoning/output content.
            self._live.transient = True
        self._stop_live()
        if not self._use_rich:
            if self._plain_reasoning_line_open or self._plain_output_line_open:
                print("", flush=True)
                self._plain_reasoning_line_open = False
                self._plain_output_line_open = False
            if had_visible_content:
                self._plain_status("completed.", self._status_style())
        self._active = False

    def finish_error(self, message: str) -> None:
        if not self._active:
            return
        self._status_state = "error"
        self._error_message = message.strip()
        self._live_show_full_output = True
        self._refresh(force=True)
        self._stop_live()
        if not self._use_rich:
            if self._plain_reasoning_line_open or self._plain_output_line_open:
                print("", flush=True)
                self._plain_reasoning_line_open = False
                self._plain_output_line_open = False
            self._plain_status(f"error: {self._error_message}", self._status_style())
        self._active = False

    def close(self) -> None:
        if self._live is not None:
            has_visible_content = bool(
                self._reasoning_buffer.strip()
                or self._output_buffer.strip()
                or self._error_message.strip()
            )
            if not has_visible_content:
                self._live.transient = True
        self._stop_live()
        self._active = False
        self._status_state = "idle"
        self._reasoning_buffer = ""
        self._output_buffer = ""
        self._error_message = ""
        self._plain_reasoning_started = False
        self._plain_output_started = False
        self._plain_processing_emitted = False
        self._plain_reasoning_line_open = False
        self._plain_output_line_open = False
        self._plain_reasoning_col = 0
        self._plain_output_col = 0
        self._last_live_refresh_at = 0.0
        self._live_show_full_output = False

    def _start_live(self) -> None:
        if self._live is not None or self._console is None:
            return
        self._live = Live(
            self._build_renderable(),
            console=self._console,
            refresh_per_second=20,
            transient=False,
            auto_refresh=False,
            vertical_overflow="crop",
        )
        self._live.start()

    def _stop_live(self) -> None:
        if self._live is None:
            return
        self._live.stop()
        self._live = None

    def _refresh(self, *, force: bool = False) -> None:
        if not self._use_rich or self._live is None:
            return
        now = time.perf_counter()
        if not force and (now - self._last_live_refresh_at) < _LIVE_REFRESH_INTERVAL_SECONDS:
            return
        self._last_live_refresh_at = now
        self._live.update(self._build_renderable(), refresh=True)

    def _live_preview_line_budget(self, reserve_lines: int) -> int:
        available = max(_LIVE_PREVIEW_MIN_LINES, self._terminal_height() - reserve_lines)
        return max(_LIVE_PREVIEW_MIN_LINES, min(_LIVE_PREVIEW_MAX_LINES, available))

    def _live_preview_text(self, text: str, *, reserve_lines: int) -> str:
        if self._live_show_full_output:
            return text

        preview = text
        if len(preview) > _LIVE_PREVIEW_MAX_CHARS:
            preview = preview[-_LIVE_PREVIEW_MAX_CHARS:]

        max_lines = self._live_preview_line_budget(reserve_lines)
        if max_lines <= 0:
            return preview

        lines = preview.splitlines()
        if preview.endswith("\n"):
            lines.append("")
        if len(lines) <= max_lines:
            return preview
        return "\n".join(lines[-max_lines:])

    def _status_style(self) -> str:
        if self._status_state == "success":
            return self._palette.status_success
        if self._status_state == "error":
            return self._palette.status_error
        if self._status_state == "thinking":
            return self._palette.status_thinking
        return self._palette.hint

    def _status_text(self) -> str:
        if self._status_state == "success":
            return "completed."
        if self._status_state == "error":
            return f"error: {self._error_message}" if self._error_message else "error."
        if self._status_state == "thinking":
            return "thinking..."
        return "processing..."

    def _status_renderable(self) -> Text:
        prefix_style = self._palette.lane
        message_style = self._palette.hint
        if self._status_state == "thinking":
            prefix_style = self._palette.status_thinking
            message_style = self._palette.hint
        elif self._status_state == "error":
            prefix_style = self._palette.status_error
            message_style = self._palette.status_error
        elif self._status_state == "success":
            prefix_style = self._palette.status_success
            message_style = self._palette.status_success

        status = Text()
        status.append("├─ ", style=prefix_style)
        status.append(self._status_text(), style=message_style)
        return status

    def _reasoning_prefix_style(self) -> str:
        if self._status_state == "thinking":
            return self._palette.status_thinking
        if self._status_state == "error":
            return self._palette.status_error
        if self._status_state == "success":
            return self._palette.status_success
        return self._palette.lane

    def _model_turn_lane_style(self) -> str:
        if self._status_state == "error":
            return self._palette.status_error
        if self._status_state == "success":
            return self._palette.status_success
        if self._active:
            return self._palette.status_thinking
        return self._palette.lane

    def _build_renderable(self) -> RenderableType:
        blocks: list[RenderableType] = [
            self._status_renderable(),
        ]

        if self._reasoning_buffer:
            reasoning_preview = self._live_preview_text(
                self._reasoning_buffer,
                reserve_lines=10,
            )
            reasoning_text = Text(reasoning_preview, overflow="fold")
            blocks.append(
                LaneRenderable(
                    reasoning_text,
                    prefix="│   ",
                    prefix_style=self._reasoning_prefix_style(),
                    content_style=self._palette.reasoning_text,
                )
            )

        if self._output_buffer:
            output_preview = self._live_preview_text(
                self._output_buffer,
                reserve_lines=6,
            )
            blocks.append(Text("├─ Agent-02", style=self._model_turn_lane_style()))
            blocks.append(
                LaneRenderable(
                    LaneMarkdown(output_preview, self._palette),
                    prefix="│ ",
                    prefix_style=self._model_turn_lane_style(),
                    content_style=self._palette.text,
                )
            )
        elif self._status_state == "error" and self._error_message:
            blocks.append(Text(f"├─ {self._error_message}", style=self._palette.status_error))

        return Group(*blocks)

    def _plain_status(self, text: str, style: str) -> None:
        del style
        print(f"├─ {text}", flush=True)

    def _normalize_token(self, token: str) -> str:
        return token.replace("\r\n", "\n").replace("\r", "\n")

    def _terminal_width(self) -> int:
        return max(40, shutil.get_terminal_size(fallback=(120, 20)).columns)

    def _terminal_height(self) -> int:
        if self._console is not None:
            try:
                return max(12, int(self._console.size.height))
            except Exception:
                pass
        return max(12, shutil.get_terminal_size(fallback=(120, 20)).lines)

    def _plain_write_with_lane(
        self,
        text: str,
        *,
        lane_prefix: str,
        line_open_attr: str,
        line_col_attr: str,
    ) -> None:
        line_open = bool(getattr(self, line_open_attr))
        col = int(getattr(self, line_col_attr))
        available = max(10, self._terminal_width() - len(lane_prefix))
        for ch in text:
            if not line_open:
                print(lane_prefix, end="", flush=True)
                line_open = True
                col = 0
            if ch != "\n" and col >= available:
                print("", flush=True)
                line_open = False
                col = 0
                print(lane_prefix, end="", flush=True)
                line_open = True
            print(ch, end="", flush=True)
            if ch == "\n":
                line_open = False
                col = 0
            else:
                col += 1
        setattr(self, line_open_attr, line_open)
        setattr(self, line_col_attr, col)
