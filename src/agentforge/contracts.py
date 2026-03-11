"""
AgentForge runtime contracts.

Shared dataclasses for provider/tool-calling interoperability.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _safe_json_dumps(value: Any) -> str:
    """
    Serialize tool arguments safely for provider payloads.

    Fallback keeps payload JSON-serializable even if a caller passes
    non-serializable objects by mistake.
    """
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({"raw": str(value)}, ensure_ascii=False)


@dataclass
class ToolCall:
    """Normalized tool call used by Agent core."""

    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    type: str = "function"

    def to_openai_message_tool_call(self) -> Dict[str, Any]:
        """Return OpenAI-compatible assistant.tool_calls item."""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": _safe_json_dumps(self.arguments),
            },
        }


@dataclass
class AssistantMessage:
    """Normalized assistant message payload."""

    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)

    def to_openai_message(self) -> Dict[str, Any]:
        msg: Dict[str, Any] = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [tc.to_openai_message_tool_call() for tc in self.tool_calls]
        return msg


@dataclass
class ToolMessage:
    """Normalized tool result message payload."""

    tool_call_id: str
    content: str
    tool_name: str = ""

    def to_openai_message(self) -> Dict[str, Any]:
        return {
            "role": "tool",
            "content": self.content,
            "tool_call_id": self.tool_call_id,
        }


@dataclass
class ProviderCapabilities:
    """Capabilities discovered at runtime for the active provider endpoint."""

    supports_tools: Optional[bool] = None
    supports_parallel_tool_calls: Optional[bool] = None
    supports_response_format: Optional[bool] = None
    supports_reasoning_effort: Optional[bool] = None
    supports_stream: Optional[bool] = None


@dataclass
class ChatCompletionResult:
    """Normalized chat completion result."""

    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    raw_response: Dict[str, Any] = field(default_factory=dict)
    used_tools_fallback: bool = False
    tool_calls_streamed: bool = False
    error: str = ""

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0
