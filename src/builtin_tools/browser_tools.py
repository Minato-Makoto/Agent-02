"""
AgentForge — Browser tools using Playwright.

Tools: browser_navigate, browser_click, browser_type, browser_screenshot,
       browser_get_content, browser_evaluate, browser_wait, browser_scroll,
       browser_select, browser_reset_context, browser_close

Uses a persistent browser context per session.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Tuple

from agentforge.runtime_config import load_tool_timeout_config
from agentforge.tools import Tool, ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages a persistent Playwright browser/context/page stack."""

    _playwright = None
    _browser = None
    _context = None
    _page = None

    @staticmethod
    def _headless_from_env() -> bool:
        value = os.environ.get("AGENTFORGE_BROWSER_HEADLESS", "0").strip().lower()
        return value in {"1", "true", "yes", "on"}

    @classmethod
    def get_page(cls):
        """Get or create the browser page."""
        if cls._page is None:
            try:
                from playwright.sync_api import sync_playwright

                if cls._playwright is None:
                    cls._playwright = sync_playwright().start()
                if cls._browser is None:
                    cls._browser = cls._playwright.chromium.launch(
                        headless=cls._headless_from_env()
                    )
                if cls._context is None:
                    cls._context = cls._browser.new_context()
                cls._page = cls._context.new_page()
            except ImportError as exc:
                raise ImportError(
                    "Playwright is not installed. Run: pip install playwright && playwright install chromium"
                ) from exc
        return cls._page

    @classmethod
    def reset_context(cls):
        """Reset browser context/page while keeping browser process alive."""
        if cls._browser is None:
            cls.get_page()
        if cls._page is not None:
            cls._page.close()
            cls._page = None
        if cls._context is not None:
            cls._context.close()
        cls._context = cls._browser.new_context()
        cls._page = cls._context.new_page()
        return cls._page

    @classmethod
    def close(cls):
        """Close the browser and clean up."""
        if cls._page:
            cls._page.close()
            cls._page = None
        if cls._context:
            cls._context.close()
            cls._context = None
        if cls._browser:
            cls._browser.close()
            cls._browser = None
        if cls._playwright:
            cls._playwright.stop()
            cls._playwright = None


def _workspace_root() -> str:
    raw = str(os.environ.get("AGENTFORGE_WORKSPACE", "")).strip()
    if raw:
        return os.path.abspath(raw)
    return os.path.abspath(os.path.join(os.getcwd(), "workspace"))


def _tool_timeouts():
    return load_tool_timeout_config()


def register(registry: ToolRegistry, skill_name: str = "browser") -> None:
    """Register all browser tools."""
    locator_fields = {
        "selector": {"type": "string", "description": "CSS selector."},
        "text": {"type": "string", "description": "Visible text locator."},
        "role": {"type": "string", "description": "ARIA role (e.g. button, textbox)."},
        "name": {"type": "string", "description": "Accessible name/label."},
    }
    tools = [
        Tool(
            name="browser_navigate",
            description="Navigate to a URL.",
            input_schema={
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL to navigate to."}},
                "required": ["url"],
            },
            execute_fn=_navigate,
        ),
        Tool(
            name="browser_click",
            description="Click an element by selector, role/name, or text.",
            input_schema={"type": "object", "properties": locator_fields},
            execute_fn=_click,
        ),
        Tool(
            name="browser_type",
            description="Type text into an input element by selector or user-facing locator.",
            input_schema={
                "type": "object",
                "properties": {
                    **locator_fields,
                    "text": {
                        "type": "string",
                        "description": "Backward-compatible alias for text_to_type.",
                    },
                    "text_to_type": {
                        "type": "string",
                        "description": "Text to type into the target input.",
                    },
                },
                "required": ["text_to_type"],
            },
            execute_fn=_type,
        ),
        Tool(
            name="browser_screenshot",
            description="Take a screenshot of the page.",
            input_schema={
                "type": "object",
                "properties": {
                    "full_page": {
                        "type": "boolean",
                        "description": "Capture full page.",
                        "default": False,
                    }
                },
            },
            execute_fn=_screenshot,
        ),
        Tool(
            name="browser_get_content",
            description="Get page text or accessibility tree.",
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for specific element."},
                    "mode": {
                        "type": "string",
                        "description": "'text' or 'accessibility'.",
                        "default": "text",
                    },
                },
            },
            execute_fn=_get_content,
        ),
        Tool(
            name="browser_evaluate",
            description="Execute JavaScript on the page.",
            input_schema={
                "type": "object",
                "properties": {"js_code": {"type": "string", "description": "JavaScript code to execute."}},
                "required": ["js_code"],
            },
            execute_fn=_evaluate,
        ),
        Tool(
            name="browser_wait",
            description="Wait for an element by selector, role/name, or text.",
            input_schema={
                "type": "object",
                "properties": {
                    **locator_fields,
                    "timeout": {"type": "integer", "description": "Timeout in ms.", "default": 10000},
                },
            },
            execute_fn=_wait,
        ),
        Tool(
            name="browser_scroll",
            description="Scroll the page.",
            input_schema={
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "description": "'up' or 'down'."},
                    "amount": {"type": "integer", "description": "Pixels to scroll.", "default": 500},
                },
                "required": ["direction"],
            },
            execute_fn=_scroll,
        ),
        Tool(
            name="browser_select",
            description="Select a value from a dropdown.",
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of select element."},
                    "value": {"type": "string", "description": "Value to select."},
                },
                "required": ["selector", "value"],
            },
            execute_fn=_select,
        ),
        Tool(
            name="browser_reset_context",
            description="Reset browser context/page for a clean automation state.",
            input_schema={"type": "object", "properties": {}},
            execute_fn=_reset_context,
        ),
        Tool(
            name="browser_close",
            description="Close the browser instance.",
            input_schema={"type": "object", "properties": {}},
            execute_fn=_close,
        ),
    ]
    registry.register_skill(skill_name, tools)


def _locator_from_args(page, args: Dict[str, Any]) -> Tuple[Any, str]:
    selector = str(args.get("selector", "")).strip()
    text = str(args.get("text", "")).strip()
    role = str(args.get("role", "")).strip()
    name = str(args.get("name", "")).strip()

    if selector:
        return page.locator(selector).first, f"selector='{selector}'"
    if role:
        kwargs: Dict[str, Any] = {}
        if name:
            kwargs["name"] = name
        return page.get_by_role(role, **kwargs).first, f"role='{role}' name='{name}'"
    if text:
        return page.get_by_text(text).first, f"text='{text}'"
    if name:
        return page.get_by_label(name).first, f"label='{name}'"
    return None, ""


def _navigate(args: Dict[str, Any]) -> ToolResult:
    url = str(args.get("url", "")).strip()
    if not url:
        return ToolResult(success=False, output=None, error="Missing 'url'")
    try:
        page = BrowserManager.get_page()
        page.goto(url, wait_until="domcontentloaded", timeout=_tool_timeouts().browser_nav_ms)
        return ToolResult(success=True, output={"title": page.title(), "url": page.url})
    except Exception as exc:
        return ToolResult.from_exception(exc, context="browser_navigate failed", logger=logger)


def _click(args: Dict[str, Any]) -> ToolResult:
    try:
        page = BrowserManager.get_page()
        locator, label = _locator_from_args(page, args)
        if locator is None:
            return ToolResult.error_result("Provide one locator: selector, role, text, or name")
        locator.click(timeout=_tool_timeouts().browser_action_ms)
        return ToolResult(success=True, output=f"Clicked {label}")
    except Exception as exc:
        return ToolResult.from_exception(exc, context="browser_click failed", logger=logger)


def _type(args: Dict[str, Any]) -> ToolResult:
    text = str(args.get("text_to_type", args.get("text", ""))).strip()
    if not text:
        return ToolResult.error_result("Missing 'text_to_type'")
    try:
        page = BrowserManager.get_page()
        locator, label = _locator_from_args(page, args)
        if locator is None:
            return ToolResult.error_result("Provide one locator: selector, role, text, or name")
        locator.fill(text, timeout=_tool_timeouts().browser_action_ms)
        return ToolResult(success=True, output=f"Typed {len(text)} chars into {label}")
    except Exception as exc:
        return ToolResult.from_exception(exc, context="browser_type failed", logger=logger)


def _screenshot(args: Dict[str, Any]) -> ToolResult:
    full_page = bool(args.get("full_page", False))
    try:
        page = BrowserManager.get_page()
        screenshot_bytes = page.screenshot(full_page=full_page)
        screenshot_dir = os.path.join(_workspace_root(), "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        filename = f"screenshot_{int(time.time())}.png"
        filepath = os.path.join(screenshot_dir, filename)
        with open(filepath, "wb") as handle:
            handle.write(screenshot_bytes)
        return ToolResult(
            success=True,
            output={
                "path": filepath,
                "size": len(screenshot_bytes),
                "url": page.url,
            },
        )
    except Exception as exc:
        return ToolResult.from_exception(exc, context="browser_screenshot failed", logger=logger)


def _get_content(args: Dict[str, Any]) -> ToolResult:
    selector = str(args.get("selector", "")).strip()
    mode = str(args.get("mode", "text")).strip().lower()
    try:
        page = BrowserManager.get_page()
        action_timeout = _tool_timeouts().browser_action_ms
        if mode == "accessibility":
            snapshot = page.accessibility.snapshot()
            return ToolResult(success=True, output=snapshot)
        if selector:
            content = page.locator(selector).inner_text(timeout=action_timeout)
        else:
            content = page.locator("body").inner_text(timeout=action_timeout)
        return ToolResult(success=True, output=content[:10000])
    except Exception as exc:
        return ToolResult.from_exception(exc, context="browser_get_content failed", logger=logger)


def _evaluate(args: Dict[str, Any]) -> ToolResult:
    js_code = str(args.get("js_code", "")).strip()
    if not js_code:
        return ToolResult(success=False, output=None, error="Missing 'js_code'")
    try:
        page = BrowserManager.get_page()
        result = page.evaluate(js_code)
        return ToolResult(success=True, output=result)
    except Exception as exc:
        return ToolResult.from_exception(exc, context="browser_evaluate failed", logger=logger)


def _wait(args: Dict[str, Any]) -> ToolResult:
    default_timeout = _tool_timeouts().browser_wait_ms
    try:
        timeout = int(args.get("timeout", default_timeout))
    except (TypeError, ValueError):
        timeout = default_timeout
    try:
        page = BrowserManager.get_page()
        locator, label = _locator_from_args(page, args)
        if locator is None:
            return ToolResult.error_result("Provide one locator: selector, role, text, or name")
        locator.wait_for(state="visible", timeout=timeout)
        return ToolResult(success=True, output=f"Element visible: {label}")
    except Exception as exc:
        return ToolResult.from_exception(exc, context="browser_wait failed", logger=logger)


def _scroll(args: Dict[str, Any]) -> ToolResult:
    direction = str(args.get("direction", "down")).strip().lower()
    amount = int(args.get("amount", 500))
    try:
        page = BrowserManager.get_page()
        delta = amount if direction == "down" else -amount
        page.mouse.wheel(0, delta)
        return ToolResult(success=True, output=f"Scrolled {direction} by {amount}px")
    except Exception as exc:
        return ToolResult.from_exception(exc, context="browser_scroll failed", logger=logger)


def _select(args: Dict[str, Any]) -> ToolResult:
    selector = str(args.get("selector", "")).strip()
    value = str(args.get("value", "")).strip()
    if not selector or not value:
        return ToolResult.error_result("Missing 'selector' or 'value'")
    try:
        page = BrowserManager.get_page()
        page.select_option(selector, value, timeout=_tool_timeouts().browser_action_ms)
        return ToolResult(success=True, output=f"Selected '{value}' in {selector}")
    except Exception as exc:
        return ToolResult.from_exception(exc, context="browser_select failed", logger=logger)


def _reset_context(args: Dict[str, Any]) -> ToolResult:
    del args
    try:
        page = BrowserManager.reset_context()
        return ToolResult(success=True, output={"status": "reset", "url": page.url})
    except Exception as exc:
        return ToolResult.from_exception(exc, context="browser_reset_context failed", logger=logger)


def _close(args: Dict[str, Any]) -> ToolResult:
    del args
    try:
        BrowserManager.close()
        return ToolResult(success=True, output="Browser closed")
    except Exception as exc:
        return ToolResult.from_exception(exc, context="browser_close failed", logger=logger)
