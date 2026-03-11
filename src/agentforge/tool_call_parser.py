"""
AgentForge — Dual-format tool call parser (JSON + XML).
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class ParsedToolCall:
    """A single parsed tool call."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class ParseResult:
    """Result of parsing an LLM response."""
    text_content: str = ""
    tool_calls: List[ParsedToolCall] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class ToolCallParser:
    """Dual-format tool call parser — tries JSON first, then XML."""

    def __init__(self):
        self._id_counter = 0
        self._parse_errors: List[str] = []

    @property
    def parse_errors(self) -> List[str]:
        return list(self._parse_errors)

    def _gen_id(self) -> str:
        self._id_counter += 1
        return f"call_{self._id_counter}"

    def parse(self, raw: str) -> ParseResult:
        """Parse raw LLM response — native XML format first, JSON fallback."""
        self._parse_errors.clear()
        # Try native format first: <tool_call>{"name": "...", "arguments": {...}}</tool_call>
        result = self.parse_xml(raw)
        if result.has_tool_calls:
            return result
        # Fallback: bare JSON {"name": "...", "arguments": {...}}
        result = self.parse_json(raw)
        if result.has_tool_calls:
            return result
        return ParseResult(text_content=raw)

    def parse_json(self, raw: str) -> ParseResult:
        """Parse JSON-format tool calls.
        
        Accepts both formats:
        - {"tool": "name", "arguments": {...}}   (AGENT.md format)
        - {"name": "name", "arguments": {...}}   (Qwen/Llama native format)
        """
        result = ParseResult()
        text_parts = []
        last_end = 0

        for match in self._find_json_objects(raw):
            start, end, obj = match
            # Accept both "tool" and "name" keys for the tool name
            tool_name = obj.get("tool") or obj.get("name")
            if tool_name and isinstance(tool_name, str) and "arguments" in obj:
                text_parts.append(raw[last_end:start])
                result.tool_calls.append(ParsedToolCall(
                    id=self._gen_id(),
                    name=tool_name,
                    arguments=obj.get("arguments", {}),
                ))
                last_end = end

        remaining = raw[last_end:].strip()
        text_before = "".join(text_parts).strip()
        result.text_content = (text_before + " " + remaining).strip() if text_before else remaining

        if not result.tool_calls:
            result.text_content = raw

        return result

    def parse_xml(self, raw: str) -> ParseResult:
        """Parse XML-format tool calls: <tool_call>...</tool_call>
        
        Handles two formats:
        1. Pure XML:  <tool_call><name>X</name><arguments>{...}</arguments></tool_call>
        2. JSON-in-XML: <tool_call>{"name": "X", "arguments": {...}}</tool_call>
        """
        result = ParseResult()

        # Pattern 1: Pure XML with <name> and <arguments> tags
        pattern_xml = re.compile(
            r"<tool_call>\s*<name>(.*?)</name>\s*<arguments>(.*?)</arguments>\s*</tool_call>",
            re.DOTALL,
        )
        # Pattern 2: JSON object inside <tool_call> tags
        pattern_json = re.compile(
            r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
            re.DOTALL,
        )

        last_end = 0
        text_parts = []

        # Try pure XML first
        for match in pattern_xml.finditer(raw):
            text_parts.append(raw[last_end:match.start()])
            name = match.group(1).strip()
            args_str = match.group(2).strip()

            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {"raw": args_str}

            result.tool_calls.append(ParsedToolCall(
                id=self._gen_id(),
                name=name,
                arguments=args,
            ))
            last_end = match.end()

        # If no pure XML found, try JSON-in-XML
        if not result.tool_calls:
            for match in pattern_json.finditer(raw):
                try:
                    obj = json.loads(match.group(1))
                    tool_name = obj.get("name") or obj.get("tool")
                    if tool_name and isinstance(tool_name, str):
                        text_parts.append(raw[last_end:match.start()])
                        result.tool_calls.append(ParsedToolCall(
                            id=self._gen_id(),
                            name=tool_name,
                            arguments=obj.get("arguments", {}),
                        ))
                        last_end = match.end()
                except json.JSONDecodeError:
                    self._parse_errors.append("Invalid JSON payload inside <tool_call> block")
                    continue

        remaining = raw[last_end:].strip()
        text_before = "".join(text_parts).strip()
        result.text_content = (text_before + " " + remaining).strip() if text_before else remaining

        return result

    def _find_json_objects(self, text: str) -> List[Tuple[int, int, dict]]:
        """Find all valid JSON objects in text."""
        results = []
        i = 0
        while i < len(text):
            if text[i] == "{":
                # Find matching }
                depth = 0
                in_string = False
                escape = False
                j = i
                while j < len(text):
                    c = text[j]
                    if escape:
                        escape = False
                        j += 1
                        continue
                    if c == "\\" and in_string:
                        escape = True
                        j += 1
                        continue
                    if c == '"':
                        in_string = not in_string
                    elif not in_string:
                        if c == "{":
                            depth += 1
                        elif c == "}":
                            depth -= 1
                            if depth == 0:
                                candidate = text[i : j + 1]
                                try:
                                    obj = json.loads(candidate)
                                    if isinstance(obj, dict):
                                        results.append((i, j + 1, obj))
                                except json.JSONDecodeError:
                                    self._parse_errors.append("Invalid JSON object candidate")
                                break
                    j += 1
            i += 1
        return results
