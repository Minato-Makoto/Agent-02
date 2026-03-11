"""
Session transcript repair helpers.
"""

import json
from typing import Any, Dict, List


def normalize_tool_calls(raw_tool_calls: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_tool_calls, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for item in raw_tool_calls:
        if not isinstance(item, dict):
            continue
        tc_id = str(item.get("id", "")).strip()
        function = item.get("function")
        if not tc_id or not isinstance(function, dict):
            continue
        name = str(function.get("name", "")).strip()
        if not name:
            continue
        args = function.get("arguments", "{}")
        if isinstance(args, dict):
            args = json.dumps(args, ensure_ascii=False)
        elif isinstance(args, str):
            args = args.strip() or "{}"
        else:
            args = "{}"
        normalized.append(
            {
                "id": tc_id,
                "type": "function",
                "function": {"name": name, "arguments": args},
            }
        )
    return normalized


def make_synthetic_tool_result(tool_call_id: str, tool_name: str = "") -> Dict[str, Any]:
    return {
        "role": "tool",
        "content": "[Synthetic tool result inserted during session migration to preserve tool-call pairing.]",
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "synthetic": True,
    }


def make_synthetic_assistant_tool_call(tool_call_id: str, tool_name: str) -> Dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": tool_call_id,
                "type": "function",
                "function": {"name": tool_name or "unknown_tool", "arguments": "{}"},
            }
        ],
        "synthetic": True,
    }


def collect_pending_tool_calls(messages: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Return unresolved tool-call ids in transcript order.
    """
    pending: Dict[str, str] = {}
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", ""))
        if role == "assistant":
            for tc in normalize_tool_calls(msg.get("tool_calls")):
                pending[tc["id"]] = tc["function"]["name"]
            continue
        if role == "tool":
            tc_id = str(msg.get("tool_call_id", "")).strip()
            if tc_id:
                pending.pop(tc_id, None)
    return pending


def repair_session_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Repair legacy/malformed transcripts.

    - Normalizes assistant tool_call blocks.
    - Ensures tool results are paired to known tool_call ids when possible.
    - Inserts synthetic tool results for missing pairs.
    """
    pending: Dict[str, str] = {}
    repaired: List[Dict[str, Any]] = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", ""))
        item = dict(msg)

        if role == "assistant":
            tool_calls = normalize_tool_calls(item.get("tool_calls"))
            if tool_calls:
                item["tool_calls"] = tool_calls
                for tc in tool_calls:
                    pending[tc["id"]] = tc["function"]["name"]
            repaired.append(item)
            continue

        if role == "tool":
            tc_id = str(item.get("tool_call_id", "")).strip()
            if not tc_id:
                if len(pending) == 1:
                    tc_id = next(iter(pending.keys()))
                    item["tool_call_id"] = tc_id
                    item.setdefault("tool_name", pending.get(tc_id, ""))
                else:
                    # Ambiguous unmatched tool result; keep as-is.
                    repaired.append(item)
                    continue
            pending.pop(tc_id, None)
            repaired.append(item)
            continue

        repaired.append(item)

    for tc_id, name in pending.items():
        repaired.append(make_synthetic_tool_result(tc_id, name))

    return repaired
