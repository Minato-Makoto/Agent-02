"""
AgentForge — Desktop computer-use tools (mouse/keyboard/screenshot).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from agentforge.runtime_config import load_tool_timeout_config
from agentforge.tools import Tool, ToolRegistry, ToolResult


def register(registry: ToolRegistry, skill_name: str = "computer-use-agents") -> None:
    tools = [
        Tool(
            name="desktop_screenshot",
            description="Capture desktop screenshot (full screen or region).",
            input_schema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Optional file name."},
                    "region": {
                        "type": "object",
                        "description": "Optional screenshot region.",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"},
                        },
                    },
                },
            },
            execute_fn=_desktop_screenshot,
        ),
        Tool(
            name="desktop_move_mouse",
            description="Move mouse cursor to absolute coordinates.",
            input_schema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "duration_ms": {"type": "integer", "default": 0},
                },
                "required": ["x", "y"],
            },
            execute_fn=_desktop_move_mouse,
        ),
        Tool(
            name="desktop_click",
            description="Click mouse at absolute coordinates.",
            input_schema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "default": "left"},
                    "clicks": {"type": "integer", "default": 1},
                    "interval_ms": {"type": "integer", "default": 0},
                },
                "required": ["x", "y"],
            },
            execute_fn=_desktop_click,
        ),
        Tool(
            name="desktop_type",
            description="Type text using keyboard.",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "interval_ms": {"type": "integer", "default": 20},
                },
                "required": ["text"],
            },
            execute_fn=_desktop_type,
        ),
        Tool(
            name="desktop_key",
            description="Press a key with optional modifier keys.",
            input_schema={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "modifiers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of modifiers, e.g. ['ctrl', 'shift'].",
                    },
                },
                "required": ["key"],
            },
            execute_fn=_desktop_key,
        ),
        Tool(
            name="desktop_scroll",
            description="Scroll mouse wheel by amount.",
            input_schema={
                "type": "object",
                "properties": {"amount": {"type": "integer", "default": -500}},
                "required": ["amount"],
            },
            execute_fn=_desktop_scroll,
        ),
    ]
    registry.register_skill(skill_name, tools)


def _workspace_root() -> Path:
    raw = str(os.environ.get("AGENTFORGE_WORKSPACE", "")).strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.cwd() / "workspace").resolve()


def _desktop_enabled() -> bool:
    value = str(os.environ.get("AGENTFORGE_DESKTOP_CONTROL", "1")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _ensure_enabled() -> ToolResult | None:
    if _desktop_enabled():
        return None
    return ToolResult.error_result(
        "Desktop control disabled. Set AGENTFORGE_DESKTOP_CONTROL=1 to enable."
    )


def _import_pyautogui():
    try:
        import pyautogui  # type: ignore

        return pyautogui, None
    except Exception as exc:
        return None, str(exc)


def _screen_size(pyautogui) -> Tuple[int, int]:
    width, height = pyautogui.size()
    return int(width), int(height)


def _validate_coords(x: int, y: int, width: int, height: int) -> bool:
    return 0 <= x < width and 0 <= y < height


def _screenshot_dir() -> Path:
    out = _workspace_root() / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    return out


def _desktop_screenshot(args: Dict[str, Any]) -> ToolResult:
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    pyautogui, error = _import_pyautogui()
    if pyautogui is None:
        return ToolResult.error_result(f"Failed to import pyautogui: {error}")

    region_raw = args.get("region")
    region = None
    if isinstance(region_raw, dict) and region_raw:
        try:
            x = int(region_raw["x"])
            y = int(region_raw["y"])
            width = int(region_raw["width"])
            height = int(region_raw["height"])
            if width <= 0 or height <= 0:
                return ToolResult.error_result("Region width/height must be > 0")
            screen_w, screen_h = _screen_size(pyautogui)
            if x < 0 or y < 0 or x + width > screen_w or y + height > screen_h:
                return ToolResult.error_result(
                    f"Region out of bounds for screen {screen_w}x{screen_h}"
                )
            region = (x, y, width, height)
        except (TypeError, KeyError, ValueError):
            return ToolResult.error_result("Invalid region. Expected x/y/width/height integers.")

    try:
        _ = load_tool_timeout_config().desktop_screenshot_s
        image = pyautogui.screenshot(region=region)
        filename = str(args.get("filename", "")).strip() or f"desktop_{int(time.time())}.png"
        if "/" in filename or "\\" in filename:
            return ToolResult.error_result("filename must not contain path separators")
        output_path = _screenshot_dir() / filename
        image.save(output_path)
        size = output_path.stat().st_size if output_path.exists() else 0
        return ToolResult(
            success=True,
            output={
                "path": str(output_path),
                "size": size,
                "region": region,
            },
        )
    except Exception as exc:
        return ToolResult.from_exception(exc, context="desktop_screenshot failed")


def _desktop_move_mouse(args: Dict[str, Any]) -> ToolResult:
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    pyautogui, error = _import_pyautogui()
    if pyautogui is None:
        return ToolResult.error_result(f"Failed to import pyautogui: {error}")
    try:
        x = int(args.get("x"))
        y = int(args.get("y"))
        duration_ms = max(0, int(args.get("duration_ms", 0)))
        screen_w, screen_h = _screen_size(pyautogui)
        if not _validate_coords(x, y, screen_w, screen_h):
            return ToolResult.error_result(f"Point ({x},{y}) out of bounds for {screen_w}x{screen_h}")
        _ = load_tool_timeout_config().desktop_action_ms
        pyautogui.moveTo(x, y, duration=duration_ms / 1000.0)
        return ToolResult(success=True, output=f"Mouse moved to ({x},{y})")
    except Exception as exc:
        return ToolResult.from_exception(exc, context="desktop_move_mouse failed")


def _desktop_click(args: Dict[str, Any]) -> ToolResult:
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    pyautogui, error = _import_pyautogui()
    if pyautogui is None:
        return ToolResult.error_result(f"Failed to import pyautogui: {error}")
    try:
        x = int(args.get("x"))
        y = int(args.get("y"))
        button = str(args.get("button", "left")).strip().lower() or "left"
        clicks = max(1, int(args.get("clicks", 1)))
        interval_ms = max(0, int(args.get("interval_ms", 0)))
        screen_w, screen_h = _screen_size(pyautogui)
        if not _validate_coords(x, y, screen_w, screen_h):
            return ToolResult.error_result(f"Point ({x},{y}) out of bounds for {screen_w}x{screen_h}")
        _ = load_tool_timeout_config().desktop_action_ms
        pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=interval_ms / 1000.0)
        return ToolResult(success=True, output=f"Clicked {button} at ({x},{y}) x{clicks}")
    except Exception as exc:
        return ToolResult.from_exception(exc, context="desktop_click failed")


def _desktop_type(args: Dict[str, Any]) -> ToolResult:
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    pyautogui, error = _import_pyautogui()
    if pyautogui is None:
        return ToolResult.error_result(f"Failed to import pyautogui: {error}")
    text = str(args.get("text", ""))
    if not text:
        return ToolResult.error_result("Missing 'text'")
    try:
        interval_ms = max(0, int(args.get("interval_ms", 20)))
        _ = load_tool_timeout_config().desktop_action_ms
        pyautogui.write(text, interval=interval_ms / 1000.0)
        return ToolResult(success=True, output=f"Typed {len(text)} characters")
    except Exception as exc:
        return ToolResult.from_exception(exc, context="desktop_type failed")


def _desktop_key(args: Dict[str, Any]) -> ToolResult:
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    pyautogui, error = _import_pyautogui()
    if pyautogui is None:
        return ToolResult.error_result(f"Failed to import pyautogui: {error}")
    key = str(args.get("key", "")).strip()
    if not key:
        return ToolResult.error_result("Missing 'key'")
    modifiers_raw = args.get("modifiers", [])
    modifiers: Iterable[str] = []
    if isinstance(modifiers_raw, list):
        modifiers = [str(v).strip() for v in modifiers_raw if str(v).strip()]
    try:
        _ = load_tool_timeout_config().desktop_action_ms
        for mod in modifiers:
            pyautogui.keyDown(mod)
        pyautogui.press(key)
        for mod in reversed(list(modifiers)):
            pyautogui.keyUp(mod)
        if modifiers:
            return ToolResult(success=True, output=f"Pressed {'+'.join(list(modifiers) + [key])}")
        return ToolResult(success=True, output=f"Pressed {key}")
    except Exception as exc:
        return ToolResult.from_exception(exc, context="desktop_key failed")


def _desktop_scroll(args: Dict[str, Any]) -> ToolResult:
    disabled = _ensure_enabled()
    if disabled:
        return disabled
    pyautogui, error = _import_pyautogui()
    if pyautogui is None:
        return ToolResult.error_result(f"Failed to import pyautogui: {error}")
    try:
        amount = int(args.get("amount", -500))
        _ = load_tool_timeout_config().desktop_action_ms
        pyautogui.scroll(amount)
        return ToolResult(success=True, output=f"Scrolled by {amount}")
    except Exception as exc:
        return ToolResult.from_exception(exc, context="desktop_scroll failed")

