"""
Tool-call ID normalization utilities.
"""

import hashlib
import re
from typing import Dict


_ALNUM_RE = re.compile(r"[^a-zA-Z0-9]")


def sanitize_tool_call_id(raw_id: str, mode: str = "strict") -> str:
    """
    Sanitize tool call ID for strict providers.

    Modes:
    - strict: alphanumeric only
    - strict9: alphanumeric exactly 9 chars
    """
    normalized_mode = (mode or "strict").strip().lower()
    if not isinstance(raw_id, str) or not raw_id:
        return "defaultid" if normalized_mode == "strict9" else "defaulttoolid"

    cleaned = _ALNUM_RE.sub("", raw_id)
    if not cleaned:
        cleaned = "sanitized"

    if normalized_mode == "strict9":
        # Keep predictable prefix and deterministic hash tail to reduce collisions.
        if len(cleaned) >= 9:
            return cleaned[:9]
        digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()
        return (cleaned + digest)[:9]

    return cleaned


def remap_tool_call_ids(ids: Dict[str, str], mode: str = "strict") -> Dict[str, str]:
    """
    Build stable remapping with collision avoidance.
    """
    used = set()
    out: Dict[str, str] = {}
    for original in ids.keys():
        base = sanitize_tool_call_id(original, mode=mode)
        candidate = base or "toolcall"
        if candidate in used:
            digest = hashlib.sha1(str(original).encode("utf-8")).hexdigest()
            if (mode or "").strip().lower() == "strict9":
                candidate = (candidate[:3] + digest)[:9]
            else:
                candidate = f"{candidate}{digest[:6]}"
            while candidate in used:
                candidate = f"{candidate}{digest[-1]}"
        used.add(candidate)
        out[original] = candidate
    return out
