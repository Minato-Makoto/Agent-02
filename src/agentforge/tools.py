"""
AgentForge — Tool definitions and ToolRegistry.

Supports:
- Tool: basic tool with execute function
- ContextualTool: tool that receives context (channel, chatID)
- AsyncTool: tool that runs asynchronously
- ToolResult: structured result from tool execution
- ToolRegistry: manages tools with skill-based registration
"""

import json
import logging
import time
import asyncio
import inspect
import uuid
import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from .schema_normalizer import normalize_tool_schema

logger = logging.getLogger(__name__)


def _safe_json(value: Any, *, pretty: bool = False) -> str:
    kwargs: Dict[str, Any] = {"ensure_ascii": False}
    if pretty:
        kwargs["indent"] = 2
    try:
        return json.dumps(value, **kwargs)
    except (TypeError, ValueError):
        return json.dumps({"raw": str(value)}, **kwargs)


def _resolve_tool_return(value: Any) -> Any:
    """
    Normalize sync/async tool return value for the current synchronous runtime.

    If a tool returns an awaitable, execute it in a fresh event loop.
    """
    if not inspect.isawaitable(value):
        return value

    async def _await_any(awaitable: Any) -> Any:
        return await awaitable

    def _run_in_worker(awaitable: Any) -> Any:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(asyncio.run, _await_any(awaitable))
            return fut.result()

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await_any(value))
    # Event loop is already running in this thread (e.g., FastAPI/Discord wrapper):
    # run awaitable in a worker thread with its own loop instead of hard-failing.
    return _run_in_worker(value)


@dataclass
class ToolResult:
    """Structured result from a tool execution.
    
    Dual-output pattern:
    - for_llm: Content for LLM context (if set, overrides output in to_string)
    - for_user: Content shown to user (empty = no user display)
    - silent: Suppress user display even if for_user is set
    - is_async: Result represents a background operation
    """
    success: bool
    output: Any
    error: str = ""
    execution_time: float = 0.0
    # Dual-output fields
    for_llm: str = ""
    for_user: str = ""
    silent: bool = False
    is_async: bool = False

    def to_string(self) -> str:
        """Content for LLM context. Prefers for_llm if set."""
        if self.for_llm:
            return self.for_llm
        if self.success:
            if isinstance(self.output, str):
                return self.output
            return _safe_json(self.output, pretty=True)
        return f"Error: {self.error}"

    @staticmethod
    def llm_result(for_llm: str, for_user: str = "") -> "ToolResult":
        """Result with separate LLM/user content."""
        return ToolResult(success=True, output=None, for_llm=for_llm, for_user=for_user)

    @staticmethod
    def silent_result(for_llm: str) -> "ToolResult":
        """Result visible only to LLM, not shown to user."""
        return ToolResult(success=True, output=None, for_llm=for_llm, silent=True)

    @staticmethod
    def error_result(message: str) -> "ToolResult":
        """Standard error result."""
        return ToolResult(success=False, output=None, error=message)

    @staticmethod
    def from_exception(
        exc: BaseException,
        *,
        context: str = "",
        logger: Optional[logging.Logger] = None,
    ) -> "ToolResult":
        """
        Standardized error envelope for exceptions.

        Keeps a short user-safe error while preserving traceback in logs
        with a reference ID for debugging.
        """
        ref = uuid.uuid4().hex[:10]
        msg = str(exc).strip() or exc.__class__.__name__
        prefix = f"{context}: " if context else ""
        if logger is not None:
            logger.exception("%s [ref=%s]", context or "Tool exception", ref)
        return ToolResult(
            success=False,
            output=None,
            error=f"{prefix}{msg} [ref:{ref}]",
        )


@dataclass
class Tool:
    """Represents a single tool the agent can invoke."""
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema
    execute_fn: Callable[[Dict[str, Any]], Any]
    preferred_format: str = "auto"  # "json", "xml", or "auto"
    skill_name: str = ""  # which skill this tool belongs to

    def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        """Execute the tool and return a structured result."""
        start = time.time()
        try:
            result = _resolve_tool_return(self.execute_fn(arguments))
            elapsed = time.time() - start
            if isinstance(result, ToolResult):
                result.execution_time = elapsed
                return result
            return ToolResult(success=True, output=result, execution_time=elapsed)
        except Exception as e:
            elapsed = time.time() - start
            failure = ToolResult.from_exception(
                e,
                context=f"Tool '{self.name}' execution failed",
                logger=logger,
            )
            failure.execution_time = elapsed
            return failure


@runtime_checkable
class ContextualTool(Protocol):
    """Interface for tools that need context (channel, chatID)."""
    def set_context(self, channel: str, chat_id: str) -> None: ...


@runtime_checkable
class AsyncTool(Protocol):
    """Interface for tools that run asynchronously."""
    async def execute_async(self, arguments: Dict[str, Any]) -> ToolResult: ...


class ToolRegistry:
    """Registry for managing available tools with skill-based grouping."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._skill_tools: Dict[str, List[str]] = {}  # skill_name -> [tool_names]

    def register(self, tool: Tool) -> None:
        """Register a single tool."""
        if tool.name in self._tools:
            logger.warning("Replacing existing tool registration for '%s'", tool.name)
        self._tools[tool.name] = tool
        if tool.skill_name:
            if tool.skill_name not in self._skill_tools:
                self._skill_tools[tool.skill_name] = []
            if tool.name not in self._skill_tools[tool.skill_name]:
                self._skill_tools[tool.skill_name].append(tool.name)

    def register_skill(self, skill_name: str, tools: List[Tool]) -> None:
        """Register all tools for a skill at once."""
        for tool in tools:
            tool.skill_name = skill_name
            self.register(tool)

    def unregister_skill(self, skill_name: str) -> None:
        """Remove all tools belonging to a skill."""
        if skill_name in self._skill_tools:
            for tool_name in self._skill_tools[skill_name]:
                self._tools.pop(tool_name, None)
            del self._skill_tools[skill_name]

    def find(self, name: str) -> Optional[Tool]:
        """Find a tool by name."""
        return self._tools.get(name)

    def get(self, name: str) -> Optional[Tool]:
        """Alias for find."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def get_all(self) -> List[Tool]:
        return list(self._tools.values())

    def get_skill_tools(self, skill_name: str) -> List[Tool]:
        """Get all tools for a specific skill."""
        if skill_name not in self._skill_tools:
            return []
        return [self._tools[n] for n in self._skill_tools[skill_name] if n in self._tools]

    def get_active_skills(self) -> List[str]:
        """Get names of all active skills."""
        return list(self._skill_tools.keys())

    @property
    def size(self) -> int:
        return len(self._tools)

    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """Export tool definitions as OpenAI-compatible tools array."""
        out: List[Dict[str, Any]] = []
        for t in sorted(self._tools.values(), key=lambda item: item.name):
            schema = t.input_schema if isinstance(t.input_schema, dict) else {}
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": normalize_tool_schema(schema),
                    },
                }
            )
        return out

    def to_json(self) -> List[Dict[str, Any]]:
        """
        Backward-compatible alias.

        Returns OpenAI-compatible tool definitions in v1.0+.
        """
        return self.to_openai_tools()
