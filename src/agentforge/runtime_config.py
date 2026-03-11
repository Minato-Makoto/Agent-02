"""
Runtime configuration helpers (env-driven, validated, clamped).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def parse_int_env(
    name: str,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default

    if min_value is not None and value < min_value:
        value = min_value
    if max_value is not None and value > max_value:
        value = max_value
    return value


def parse_float_env(
    name: str,
    default: float,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        value = default
    else:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = default

    if min_value is not None and value < min_value:
        value = min_value
    if max_value is not None and value > max_value:
        value = max_value
    return value


def parse_bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return default
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    return default


@dataclass(frozen=True)
class ToolTimeoutConfig:
    browser_nav_ms: int = 60000
    browser_action_ms: int = 15000
    browser_wait_ms: int = 30000
    desktop_action_ms: int = 5000
    desktop_screenshot_s: int = 15
    web_request_s: int = 30
    web_search_s: int = 15
    photoshop_s: int = 30
    process_list_s: int = 10


@dataclass(frozen=True)
class ShellPolicyConfig:
    workspace_only: bool = True


def load_tool_timeout_config() -> ToolTimeoutConfig:
    return ToolTimeoutConfig(
        browser_nav_ms=parse_int_env(
            "TOOL_TIMEOUT_BROWSER_NAV_MS", 60000, min_value=500, max_value=300000
        ),
        browser_action_ms=parse_int_env(
            "TOOL_TIMEOUT_BROWSER_ACTION_MS", 15000, min_value=200, max_value=120000
        ),
        browser_wait_ms=parse_int_env(
            "TOOL_TIMEOUT_BROWSER_WAIT_MS", 30000, min_value=200, max_value=300000
        ),
        desktop_action_ms=parse_int_env(
            "TOOL_TIMEOUT_DESKTOP_ACTION_MS", 5000, min_value=50, max_value=120000
        ),
        desktop_screenshot_s=parse_int_env(
            "TOOL_TIMEOUT_DESKTOP_SCREENSHOT_S", 15, min_value=1, max_value=120
        ),
        web_request_s=parse_int_env("TOOL_TIMEOUT_WEB_REQUEST_S", 30, min_value=1, max_value=300),
        web_search_s=parse_int_env("TOOL_TIMEOUT_WEB_SEARCH_S", 15, min_value=1, max_value=120),
        photoshop_s=parse_int_env("TOOL_TIMEOUT_PHOTOSHOP_S", 30, min_value=1, max_value=300),
        process_list_s=parse_int_env("TOOL_TIMEOUT_PROCESS_LIST_S", 10, min_value=1, max_value=60),
    )


def load_shell_policy_config() -> ShellPolicyConfig:
    return ShellPolicyConfig(
        workspace_only=parse_bool_env("SHELL_WORKSPACE_ONLY", True),
    )
