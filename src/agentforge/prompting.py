"""
AgentForge — structured conversation message builder.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import json

from .contracts import ToolCall


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({"raw": str(value)}, ensure_ascii=False)


@dataclass
class ChatMessage:
    """A single normalized message in conversation history."""

    role: str  # "system", "user", "assistant", "tool"
    content: str = ""
    tool_call_id: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_name: str = ""

    def to_openai_message(self) -> Dict[str, Any]:
        msg: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.role == "tool" and self.tool_name:
            msg["name"] = self.tool_name
        return msg


class PromptBuilder:
    """Builds and manages structured message history for chat-completions APIs."""

    def __init__(self):
        self.system_message: str = ""
        self.messages: List[ChatMessage] = []

    def set_system(self, msg: str):
        self.system_message = msg

    def add_user(self, msg: str):
        self.messages.append(ChatMessage(role="user", content=msg))

    def add_assistant(self, msg: str):
        self.messages.append(ChatMessage(role="assistant", content=msg))

    def add_assistant_tool_calls(self, tool_calls: List[ToolCall], content: str = ""):
        serialized = [tc.to_openai_message_tool_call() for tc in tool_calls]
        self.messages.append(
            ChatMessage(role="assistant", content=content, tool_calls=serialized)
        )

    def add_tool_call(self, call_id: str, name: str, arguments: Dict[str, Any]):
        """Backward-compatible helper for single tool call append."""
        self.add_assistant_tool_calls([ToolCall(id=call_id, name=name, arguments=arguments)])

    def add_tool_result(self, call_id: str, name: str, result: Any):
        serialized = result if isinstance(result, str) else _safe_json(result)
        self.messages.append(
            ChatMessage(
                role="tool",
                content=serialized,
                tool_call_id=call_id,
                tool_name=name,
            )
        )

    def clear(self):
        """Clear messages but keep system prompt."""
        self.messages.clear()

    @property
    def count(self) -> int:
        return len(self.messages)

    def truncate(self, max_tokens: int, chars_per_token: int = 4):
        """Remove oldest message pairs to fit within token budget."""
        max_chars = max_tokens * chars_per_token
        total = len(self.system_message)
        for m in self.messages:
            total += len(m.content) + len(m.role) + 20
            if m.tool_calls:
                total += len(_safe_json(m.tool_calls))

        while total > max_chars and len(self.messages) >= 2:
            removed = self.messages.pop(0)
            total -= len(removed.content) + len(removed.role) + 20
            if removed.tool_calls:
                total -= len(_safe_json(removed.tool_calls))

            if self.messages:
                removed2 = self.messages.pop(0)
                total -= len(removed2.content) + len(removed2.role) + 20
                if removed2.tool_calls:
                    total -= len(_safe_json(removed2.tool_calls))

    def build_messages(self, include_system: bool = True) -> List[Dict[str, Any]]:
        """Build API-ready messages list."""
        out: List[Dict[str, Any]] = []
        if include_system and self.system_message:
            out.append({"role": "system", "content": self.system_message})
        for m in self.messages:
            out.append(m.to_openai_message())
        return out

    def build(self, chat_template: str = "", tools_registry=None) -> List[Dict[str, Any]]:
        """
        Backward-compatible alias for tests/callers.

        In v1.0+ this returns structured message dicts.
        """
        return self.build_messages(include_system=True)
