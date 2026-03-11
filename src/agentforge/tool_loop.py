"""
AgentForge — tool loop safety guards.

v1.0 hardening:
- Generic repeat detection
- No-progress detection
- Ping-pong detection
- Global circuit breaker
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .tools import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


def _stable_hash(value: Any) -> str:
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        serialized = str(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass
class ToolCallRecord:
    tool_name: str
    args_hash: str
    result_hash: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp <= 0:
            self.timestamp = time.time()


class ToolLoop:
    """Reusable tool execution loop with strict safety guards."""

    def __init__(
        self,
        registry: ToolRegistry,
        max_iterations: int,
        max_repeats: int,
        timeout: float,
        warning_threshold: int = 10,
        critical_threshold: int = 20,
        global_threshold: int = 30,
        history_size: int = 64,
    ):
        self._registry = registry
        self._max_iterations = max_iterations
        self._timeout = timeout
        self._max_repeats = max(1, max_repeats)
        self._warning_threshold = max(2, warning_threshold)
        self._critical_threshold = max(self._warning_threshold + 1, critical_threshold)
        self._global_threshold = max(self._critical_threshold + 1, global_threshold)
        self._history_size = max(16, history_size)
        self._history: List[ToolCallRecord] = []

    def _append_history(self, record: ToolCallRecord):
        self._history.append(record)
        if len(self._history) > self._history_size:
            self._history = self._history[-self._history_size :]

    def _count_identical_calls(self, tool_name: str, args_hash: str) -> int:
        return sum(1 for h in self._history if h.tool_name == tool_name and h.args_hash == args_hash)

    def _no_progress_streak(self, tool_name: str, args_hash: str) -> int:
        streak = 0
        last_result = None
        for h in reversed(self._history):
            if h.tool_name != tool_name or h.args_hash != args_hash:
                continue
            if not h.result_hash:
                continue
            if last_result is None:
                last_result = h.result_hash
                streak = 1
                continue
            if h.result_hash != last_result:
                break
            streak += 1
        return streak

    def _ping_pong_streak(self, next_args_hash: str) -> int:
        if len(self._history) < 2:
            return 0
        last = self._history[-1]
        prev = self._history[-2]
        if last.args_hash == prev.args_hash:
            return 0
        if next_args_hash != prev.args_hash:
            return 0

        expected = last.args_hash
        count = 0
        for h in reversed(self._history):
            if h.args_hash != expected:
                break
            count += 1
            expected = prev.args_hash if expected == last.args_hash else last.args_hash
        return count + 1

    def _loop_guard(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[ToolResult]:
        args_hash = _stable_hash(arguments)
        repeat_count = self._count_identical_calls(tool_name, args_hash) + 1
        if repeat_count >= self._max_repeats:
            logger.warning(
                "Loop guard: generic repeat triggered for %s (%d calls)",
                tool_name,
                repeat_count,
            )
            return ToolResult.error_result(
                f"Loop detected: `{tool_name}` called {repeat_count} times with the same arguments."
            )

        no_progress = self._no_progress_streak(tool_name, args_hash)
        if no_progress >= self._critical_threshold:
            logger.warning(
                "Loop guard: critical no-progress streak for %s (streak=%d)",
                tool_name,
                no_progress,
            )
        if no_progress >= self._global_threshold:
            logger.error(
                "Loop guard: global circuit breaker triggered for %s (streak=%d)",
                tool_name,
                no_progress,
            )
            return ToolResult.error_result(
                f"Global circuit breaker: `{tool_name}` repeated identical no-progress outcomes {no_progress} times."
            )

        ping_pong = self._ping_pong_streak(args_hash)
        if ping_pong >= self._warning_threshold:
            logger.warning(
                "Loop guard: ping-pong detected around %s (count=%d)",
                tool_name,
                ping_pong,
            )
            return ToolResult.error_result(
                f"Ping-pong loop detected ({ping_pong} alternating calls). Stop retrying and choose a different strategy."
            )

        return None

    def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any], tool_call_id: str = ""
    ) -> ToolResult:
        """Execute a single tool with strict loop guards."""
        guard_result = self._loop_guard(tool_name, arguments)
        if guard_result:
            self._append_history(
                ToolCallRecord(
                    tool_name=tool_name,
                    args_hash=_stable_hash(arguments),
                    result_hash=_stable_hash({"error": guard_result.error}),
                )
            )
            return guard_result

        tool = self._registry.find(tool_name)
        if not tool:
            missing = ToolResult.error_result(
                f"Tool '{tool_name}' not found. Available tools: {', '.join(t.name for t in self._registry.get_all())}"
            )
            self._append_history(
                ToolCallRecord(
                    tool_name=tool_name,
                    args_hash=_stable_hash(arguments),
                    result_hash=_stable_hash({"error": missing.error}),
                )
            )
            return missing

        result = tool.execute(arguments)
        self._append_history(
            ToolCallRecord(
                tool_name=tool_name,
                args_hash=_stable_hash(arguments),
                result_hash=_stable_hash(
                    {"success": result.success, "value": result.to_string(), "error": result.error}
                ),
            )
        )
        return result

    def should_continue(self, iteration: int, start_time: float) -> Tuple[bool, str]:
        if iteration >= self._max_iterations:
            return False, f"Max iterations reached ({self._max_iterations})"
        elapsed = time.time() - start_time
        if elapsed > self._timeout:
            return False, f"Timeout reached ({self._timeout}s)"
        return True, ""

    def reset(self) -> None:
        self._history.clear()

    @property
    def iteration_limit(self) -> int:
        return self._max_iterations
