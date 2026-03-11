"""
AgentForge — Context Window Summarizer.

3-tier compression:
1. Soft trim: Prune long tool results (keep head/tail, replace middle)
2. Graceful summarization: LLM-based summary of old messages
3. Emergency compression: aggressive truncation when context overflows
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class Summarizer:
    """Manages context window compression via summarization."""

    def __init__(self, max_tokens: int = 8192, chars_per_token: int = 4):
        self._max_tokens = max_tokens
        self._chars_per_token = chars_per_token
        self._soft_trim_threshold = 0.6   # prune tool results at 60%
        self._summary_threshold = 0.7     # summarize at 70% capacity
        # Max length for a single tool result before pruning
        self._max_tool_result_chars = 2000
        self._graceful_min_keep_messages = 8
        self._graceful_max_keep_messages = 24
        self._emergency_min_keep_messages = 6
        self._emergency_max_keep_messages = 10

    @property
    def max_chars(self) -> int:
        return self._max_tokens * self._chars_per_token

    @property
    def threshold_chars(self) -> int:
        return int(self.max_chars * self._summary_threshold)

    @property
    def soft_trim_chars(self) -> int:
        return int(self.max_chars * self._soft_trim_threshold)

    def estimate_tokens(self, messages: List[Dict[str, Any]], system_prompt: str = "") -> int:
        """Estimate total token count for messages + system prompt."""
        total_chars = len(system_prompt)
        for msg in messages:
            total_chars += len(str(msg.get("content", ""))) + len(msg.get("role", "")) + 20
            if msg.get("tool_calls"):
                total_chars += len(json.dumps(msg["tool_calls"]))
        return total_chars // self._chars_per_token

    def needs_summarization(self, messages: List[Dict[str, Any]], system_prompt: str = "") -> bool:
        """Check if messages exceed the summarization threshold."""
        total_chars = len(system_prompt)
        for msg in messages:
            total_chars += len(str(msg.get("content", ""))) + len(msg.get("role", "")) + 20
            if msg.get("tool_calls"):
                total_chars += len(json.dumps(msg["tool_calls"]))
        return total_chars > self.threshold_chars

    def prune_tool_results(self, messages: List[Dict[str, Any]], system_prompt: str = "") -> List[Dict[str, Any]]:
        """
        Tier 0.5: Soft trim — prune long tool results in-place.
        
        When total context exceeds soft_trim_threshold, replace long tool
        outputs with head/tail excerpts. Preserves recent messages.
        Soft-trim pattern.
        """
        total_chars = len(system_prompt)
        for msg in messages:
            total_chars += len(str(msg.get("content", ""))) + 20
            if msg.get("tool_calls"):
                total_chars += len(json.dumps(msg["tool_calls"]))

        if total_chars < self.soft_trim_chars:
            return messages  # No pruning needed

        # Prune ALL long tool results (LLM already saw full output)
        pruned = []
        for msg in messages:
            if msg.get("role") == "tool" and len(str(msg.get("content", ""))) > self._max_tool_result_chars:
                # Truncate: keep first 500 + last 500 chars
                content = str(msg.get("content", ""))
                head = content[:500]
                tail = content[-500:]
                trimmed_content = f"{head}\n\n[... {len(content) - 1000} chars pruned ...]\n\n{tail}"
                pruned.append({**msg, "content": trimmed_content})
            else:
                pruned.append(msg)

        return pruned

    def graceful_summarize(
        self,
        messages: List[Dict[str, Any]],
        existing_summary: str,
        llm_fn: Optional[Callable] = None,
    ) -> tuple:
        """
        Tier 1: Graceful summarization.
        
        Keeps recent messages, compresses older ones into a summary.
        If llm_fn is provided, uses it to generate the summary.
        Otherwise, does a simple text-based compression.
        
        Returns: (summary_text, remaining_messages)
        """
        if len(messages) < (self._graceful_min_keep_messages + 2):
            return existing_summary, messages

        keep_count = self._dynamic_keep_count(
            messages,
            min_keep=self._graceful_min_keep_messages,
            max_keep=self._graceful_max_keep_messages,
            target_ratio=0.42,
        )
        keep_count = min(max(1, keep_count), max(1, len(messages) - 1))
        old_messages = messages[:-keep_count]
        recent_messages = messages[-keep_count:]

        # Build summary text from old messages
        old_text = self._messages_to_text(old_messages)

        if llm_fn:
            prompt = f"""You are Agent-02 preparing a continuation summary because context limit was reached.
This summary will be injected back into the SAME session transcript to continue the same task.
Be concise but decision-complete.

Output format (plain text headings):
1) Goal
2) Decisions made
3) File/tool state
4) Pending work
5) Constraints and risks

Rules:
- Preserve concrete facts, paths, command outcomes, and tool outputs that affect next actions.
- Keep unresolved blockers explicit.
- Do not invent details.
- Keep under 280 words.

Previous summary:
{existing_summary or '(none)'}

New messages to summarize:
{old_text}

Write the continuation summary now."""
            try:
                summary = llm_fn(prompt)
                if summary:
                    return summary.strip(), recent_messages
            except Exception as exc:
                logger.warning("LLM summarization failed; falling back to local summary: %s", exc)

        # Fallback: simple text concatenation
        parts = []
        if existing_summary:
            parts.append(existing_summary)
        parts.append(f"[Compressed {len(old_messages)} messages]")

        # Extract key content from old messages
        for msg in old_messages:
            role = msg.get("role", "unknown")
            content = str(msg.get("content", ""))[:100]
            if content.strip():
                parts.append(f"- {role}: {content}")

        summary = "\n".join(parts)
        return summary, recent_messages

    def emergency_compress(
        self,
        messages: List[Dict[str, Any]],
        existing_summary: str = "",
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Tier 2: Emergency compression.

        Aggressively shrinks context but keeps a broader recent tail and
        injects a compact memory note instead of hard-resetting to 2 messages.
        """
        if len(messages) <= self._emergency_min_keep_messages:
            return messages, {"dropped_count": 0, "summary_hint": ""}

        keep_count = self._dynamic_keep_count(
            messages,
            min_keep=self._emergency_min_keep_messages,
            max_keep=self._emergency_max_keep_messages,
            target_ratio=0.28,
        )
        keep_count = min(max(1, keep_count), len(messages))

        dropped_messages = messages[:-keep_count]
        recent_messages = messages[-keep_count:]
        summary_hint = self._build_emergency_summary(dropped_messages, existing_summary)

        compacted: List[Dict[str, Any]] = []
        if summary_hint:
            compacted.append({"role": "system", "content": summary_hint})
        compacted.extend(recent_messages)
        return compacted, {
            "dropped_count": len(dropped_messages),
            "kept_count": len(recent_messages),
            "summary_hint": summary_hint,
        }

    def _dynamic_keep_count(
        self,
        messages: List[Dict[str, Any]],
        *,
        min_keep: int,
        max_keep: int,
        target_ratio: float,
    ) -> int:
        if not messages:
            return 0
        upper = max(1, min(int(max_keep), len(messages)))
        lower = max(1, min(int(min_keep), upper))
        target_chars = max(256, int(self.max_chars * float(target_ratio)))
        kept_chars = 0
        kept_count = 0

        for msg in reversed(messages):
            msg_chars = self._estimate_message_chars(msg)
            if kept_count >= lower and (kept_chars + msg_chars) > target_chars:
                break
            kept_chars += msg_chars
            kept_count += 1
            if kept_count >= upper:
                break

        return max(lower, kept_count)

    def _estimate_message_chars(self, msg: Dict[str, Any]) -> int:
        role = str(msg.get("role", ""))
        content = str(msg.get("content", ""))
        tool_calls = msg.get("tool_calls")
        extra = len(json.dumps(tool_calls, ensure_ascii=False)) if tool_calls else 0
        return len(role) + len(content) + extra + 24

    def _build_emergency_summary(self, dropped: List[Dict[str, Any]], existing_summary: str) -> str:
        parts: List[str] = []
        if existing_summary.strip():
            parts.append(f"existing_summary: {existing_summary.strip()[:800]}")
        if dropped:
            parts.append(f"dropped_messages: {len(dropped)}")
            for msg in dropped[-6:]:
                role = str(msg.get("role", "unknown"))
                content = " ".join(str(msg.get("content", "")).split())
                if content:
                    parts.append(f"- {role}: {content[:160]}")
        summary_body = "\n".join(parts).strip()
        if not summary_body:
            return ""
        summary = (
            "Context memory note (emergency compaction). "
            "Use this as prior context for continuity.\n"
            f"{summary_body}"
        )
        return summary[:1600]

    def _messages_to_text(self, messages: List[Dict[str, Any]]) -> str:
        """Convert messages to readable text for summarization."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = str(msg.get("content", ""))
            if content.strip():
                lines.append(f"{role}: {content}")
        return "\n".join(lines)
