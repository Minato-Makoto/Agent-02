"""
Provider-aware transcript policy and sanitization.

Capabilities:
- provider-specific turn sanitization
- optional tool-call-id normalization
- tool-use/result pairing repair for strict providers
"""

from dataclasses import dataclass
import json
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .session_repair import make_synthetic_tool_result, normalize_tool_calls
from .tool_id import sanitize_tool_call_id


@dataclass(frozen=True)
class TranscriptPolicy:
    provider: str
    sanitize_tool_call_ids: bool = False
    tool_call_id_mode: str = "strict"
    repair_tool_use_result_pairing: bool = False
    allow_synthetic_tool_results: bool = False
    drop_orphan_tool_results: bool = True


def detect_provider_kind(mode: str, base_url: str, model_id: str = "") -> str:
    if mode == "local":
        return "llama_cpp"
    host = ""
    base = (base_url or "").lower()
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except (ValueError, TypeError):
        host = ""
    model = (model_id or "").lower()

    if "openai.com" in host:
        return "openai"
    if "openrouter.ai" in host:
        return "openrouter"
    if "anthropic.com" in host:
        return "anthropic"
    if "googleapis.com" in host or "generativelanguage" in host:
        return "gemini"
    if "ollama" in host or (host in {"localhost", "127.0.0.1"} and ":11434" in base):
        return "ollama"
    if "vllm" in host:
        return "vllm"
    if "mistral" in host or "mistral" in model or "mixtral" in model:
        return "mistral"
    if "gemini" in model:
        return "gemini"
    if "claude" in model:
        return "anthropic"
    return "openai_compatible"


def resolve_transcript_policy(provider: str, model_id: str = "") -> TranscriptPolicy:
    normalized = (provider or "").strip().lower()
    model = (model_id or "").lower()

    if normalized in {"openai", "openrouter"}:
        return TranscriptPolicy(provider=normalized)

    if normalized in {"gemini", "anthropic"}:
        return TranscriptPolicy(
            provider=normalized,
            sanitize_tool_call_ids=True,
            tool_call_id_mode="strict",
            repair_tool_use_result_pairing=True,
            allow_synthetic_tool_results=True,
        )

    if normalized in {"mistral"} or "mistral" in model or "mixtral" in model:
        return TranscriptPolicy(
            provider="mistral",
            sanitize_tool_call_ids=True,
            tool_call_id_mode="strict9",
            repair_tool_use_result_pairing=True,
            allow_synthetic_tool_results=True,
        )

    if normalized in {"llama_cpp", "ollama", "vllm", "openai_compatible"}:
        return TranscriptPolicy(
            provider=normalized,
            sanitize_tool_call_ids=True,
            tool_call_id_mode="strict",
            repair_tool_use_result_pairing=False,
            allow_synthetic_tool_results=False,
        )

    return TranscriptPolicy(provider=normalized or "unknown")


def _normalize_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _normalize_assistant_tool_calls(
    raw_tool_calls: Any, policy: TranscriptPolicy
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    normalized = normalize_tool_calls(raw_tool_calls)
    pending: Dict[str, str] = {}
    out: List[Dict[str, Any]] = []
    for tc in normalized:
        tc_id = str(tc.get("id", "")).strip()
        function = tc.get("function", {})
        if not tc_id or not isinstance(function, dict):
            continue
        if policy.sanitize_tool_call_ids:
            tc_id = sanitize_tool_call_id(tc_id, mode=policy.tool_call_id_mode)
        name = str(function.get("name", "")).strip()
        if not name:
            continue
        args = function.get("arguments", "{}")
        if isinstance(args, dict):
            args = json.dumps(args, ensure_ascii=False)
        elif not isinstance(args, str):
            args = "{}"
        item = {
            "id": tc_id,
            "type": "function",
            "function": {"name": name, "arguments": args},
        }
        out.append(item)
        pending[tc_id] = name
    return out, pending


def apply_transcript_policy(
    messages: List[Dict[str, Any]], policy: TranscriptPolicy
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Sanitize conversation transcript according to provider policy.
    """
    sanitized: List[Dict[str, Any]] = []
    pending: Dict[str, str] = {}
    dropped = 0
    reassigned = 0
    synthetic_added = 0

    def flush_pending_if_needed(next_role: str) -> None:
        nonlocal synthetic_added
        if not pending:
            return
        if next_role == "tool":
            return
        if not policy.allow_synthetic_tool_results:
            return
        for tc_id, tc_name in list(pending.items()):
            synthetic = make_synthetic_tool_result(tc_id, tc_name)
            sanitized.append(
                {
                    "role": "tool",
                    "content": _normalize_content(synthetic.get("content", "")),
                    "tool_call_id": str(synthetic.get("tool_call_id", "")),
                }
            )
            synthetic_added += 1
        pending.clear()

    for raw in messages:
        if not isinstance(raw, dict):
            dropped += 1
            continue
        role = str(raw.get("role", "")).strip().lower()
        if role not in {"system", "user", "assistant", "tool"}:
            dropped += 1
            continue

        flush_pending_if_needed(role)

        if role in {"system", "user"}:
            sanitized.append({"role": role, "content": _normalize_content(raw.get("content", ""))})
            continue

        if role == "assistant":
            out_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": _normalize_content(raw.get("content", "")),
            }
            tc_list, tc_pending = _normalize_assistant_tool_calls(raw.get("tool_calls"), policy)
            if tc_list:
                out_msg["tool_calls"] = tc_list
                pending.update(tc_pending)
            sanitized.append(out_msg)
            continue

        # role == tool
        tc_id = str(raw.get("tool_call_id", "")).strip()
        if policy.sanitize_tool_call_ids and tc_id:
            tc_id = sanitize_tool_call_id(tc_id, mode=policy.tool_call_id_mode)

        if not tc_id and policy.repair_tool_use_result_pairing and len(pending) == 1:
            tc_id = next(iter(pending.keys()))
            reassigned += 1
        elif tc_id and tc_id not in pending and policy.repair_tool_use_result_pairing and len(pending) == 1:
            tc_id = next(iter(pending.keys()))
            reassigned += 1

        if not tc_id or tc_id not in pending:
            if policy.drop_orphan_tool_results:
                dropped += 1
                continue
            sanitized.append(
                {
                    "role": "tool",
                    "content": _normalize_content(raw.get("content", "")),
                    "tool_call_id": tc_id,
                }
            )
            continue

        pending.pop(tc_id, None)
        sanitized.append(
            {
                "role": "tool",
                "content": _normalize_content(raw.get("content", "")),
                "tool_call_id": tc_id,
            }
        )

    if pending and policy.allow_synthetic_tool_results:
        for tc_id, tc_name in list(pending.items()):
            synthetic = make_synthetic_tool_result(tc_id, tc_name)
            sanitized.append(
                {
                    "role": "tool",
                    "content": _normalize_content(synthetic.get("content", "")),
                    "tool_call_id": str(synthetic.get("tool_call_id", "")),
                }
            )
            synthetic_added += 1
        pending.clear()

    meta = {
        "dropped_messages": dropped,
        "reassigned_tool_results": reassigned,
        "synthetic_tool_results": synthetic_added,
    }
    return sanitized, meta
