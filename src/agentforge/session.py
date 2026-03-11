"""
AgentForge — SessionManager for persistent conversation state.

v1.0 adds:
- schema_version
- legacy transcript migration and repair
v1.1 adds:
- previous_session_id linkage for continuation branches
"""

import json
import time
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path

from .session_repair import (
    collect_pending_tool_calls,
    make_synthetic_assistant_tool_call,
    make_synthetic_tool_result,
    normalize_tool_calls,
    repair_session_messages,
)


SESSION_SCHEMA_VERSION = 3


@dataclass
class SessionMessage:
    """A single message in the session."""

    role: str
    content: str
    timestamp: float = 0.0
    tool_call_id: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_name: str = ""
    synthetic: bool = False

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "tool_call_id": self.tool_call_id,
            "tool_calls": self.tool_calls,
            "tool_name": self.tool_name,
            "synthetic": self.synthetic,
        }

    def to_transcript_entry(self) -> Dict[str, Any]:
        """
        Minimal normalized transcript shape used by repair/pairing helpers.
        """
        return {
            "role": self.role,
            "content": self.content,
            "tool_call_id": self.tool_call_id,
            "tool_calls": self.tool_calls,
            "tool_name": self.tool_name,
        }

    @staticmethod
    def from_dict(raw: Any) -> Optional["SessionMessage"]:
        if not isinstance(raw, dict):
            return None
        try:
            return SessionMessage(
                role=str(raw.get("role", "")),
                content=str(raw.get("content", "")),
                timestamp=float(raw.get("timestamp", 0.0) or 0.0),
                tool_call_id=str(raw.get("tool_call_id", "")),
                tool_calls=raw.get("tool_calls")
                if isinstance(raw.get("tool_calls"), list)
                else None,
                tool_name=str(raw.get("tool_name", "")),
                synthetic=bool(raw.get("synthetic", False)),
            )
        except (TypeError, ValueError):
            return None


@dataclass
class SessionData:
    """Persistent session data."""

    id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    schema_version: int = SESSION_SCHEMA_VERSION
    messages: List[SessionMessage] = field(default_factory=list)
    summary: str = ""
    previous_session_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if self.created_at == 0.0:
            self.created_at = time.time()
        if self.schema_version <= 0:
            self.schema_version = SESSION_SCHEMA_VERSION


def migrate_session_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Migrate raw persisted payload to schema v3.
    """
    data = dict(raw)
    version = int(data.get("schema_version", 1))

    messages = data.get("messages", [])
    if isinstance(messages, list):
        repaired = repair_session_messages([m for m in messages if isinstance(m, dict)])
    else:
        repaired = []

    # Always run transcript repair pass for safety.
    data["messages"] = repaired
    data["schema_version"] = 3 if version < 3 else max(3, version)

    metadata = data.get("metadata", {})
    data["metadata"] = metadata if isinstance(metadata, dict) else {}
    data["summary"] = str(data.get("summary", ""))
    data["previous_session_id"] = str(data.get("previous_session_id", ""))
    data.setdefault("created_at", 0.0)
    data.setdefault("updated_at", 0.0)
    return data


class SessionManager:
    """Manages persistent session state with atomic file I/O."""

    def __init__(self, sessions_dir: str):
        self._dir = Path(sessions_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        # Reentrant lock is required because migration path may call _save()
        # while already holding the lock in load_session().
        self._lock = threading.RLock()
        self._session: Optional[SessionData] = None

    @property
    def session(self) -> Optional[SessionData]:
        return self._session

    def new_session(self, session_id: str = "") -> SessionData:
        self._session = SessionData(id=session_id) if session_id else SessionData()
        self._save()
        return self._session

    def load_session(self, session_id: str) -> Optional[SessionData]:
        path = self._dir / f"{session_id}.json"
        if not path.exists():
            return None
        with self._lock:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                data = migrate_session_payload(raw)
                messages = [SessionMessage.from_dict(m) for m in data.get("messages", [])]
                messages = [m for m in messages if m is not None]
                self._session = SessionData(
                    id=str(data.get("id", session_id)),
                    created_at=float(data.get("created_at", 0.0)),
                    updated_at=float(data.get("updated_at", 0.0)),
                    schema_version=int(data.get("schema_version", SESSION_SCHEMA_VERSION)),
                    messages=messages,
                    summary=str(data.get("summary", "")),
                    previous_session_id=str(data.get("previous_session_id", "")),
                    metadata=data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {},
                )
                # persist migrated structure if changed
                self._save()
                return self._session
            except (json.JSONDecodeError, TypeError, ValueError):
                return None

    def branch_session(
        self,
        summary: str,
        old_id: str,
        continuation_messages: List[Dict[str, Any]],
    ) -> SessionData:
        """Create a continuation branch session linked to the previous session ID."""
        source_id = str(old_id).strip()
        if not source_id and self._session:
            source_id = self._session.id

        new_session = SessionData(
            summary=str(summary or ""),
            previous_session_id=source_id,
        )
        new_session.messages.append(
            SessionMessage(
                role="system",
                content=self._build_continuation_message(source_id, summary),
            )
        )
        for raw in continuation_messages:
            msg = self._coerce_prompt_message(raw)
            if msg is not None:
                new_session.messages.append(msg)
        new_session.updated_at = time.time()

        self._session = new_session
        self._save()
        return new_session

    def load_latest(self) -> Optional[SessionData]:
        sessions = list(self._dir.glob("*.json"))
        if not sessions:
            return None
        latest = max(sessions, key=lambda p: p.stat().st_mtime)
        return self.load_session(latest.stem)

    def add_message(self, role: str, content: str, **kwargs) -> None:
        if not self._session:
            self.new_session()
        if role != "tool":
            self._flush_pending_tool_results()
        msg = SessionMessage(role=role, content=content, **kwargs)
        self._session.messages.append(msg)
        self._session.updated_at = time.time()
        self._save()

    def add_assistant_tool_calls(self, tool_calls: List[Dict[str, Any]], content: str = "") -> None:
        if not self._session:
            return
        self._flush_pending_tool_results()
        normalized_calls = normalize_tool_calls(tool_calls)
        if not normalized_calls:
            # Keep transcript valid by avoiding malformed assistant tool-call turns.
            self._session.messages.append(SessionMessage(role="assistant", content=content))
            self._session.updated_at = time.time()
            self._save()
            return
        self._session.messages.append(
            SessionMessage(role="assistant", content=content, tool_calls=normalized_calls)
        )
        self._session.updated_at = time.time()
        self._save()

    def add_tool_call(self, call_id: str, name: str, arguments: Dict[str, Any]) -> None:
        if not self._session:
            return
        tc = {
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
        }
        self.add_assistant_tool_calls([tc], content="")

    def add_tool_result(self, call_id: str, name: str, result: Any) -> None:
        if not self._session:
            return
        pending = self._pending_tool_calls()
        normalized_id = str(call_id or "").strip()
        if not normalized_id:
            if len(pending) == 1:
                normalized_id = next(iter(pending.keys()))
            else:
                normalized_id = f"synthetic_{int(time.time() * 1000)}"

        if normalized_id not in pending:
            if len(pending) == 1:
                normalized_id = next(iter(pending.keys()))
            else:
                synth_call = make_synthetic_assistant_tool_call(normalized_id, name)
                self._session.messages.append(
                    SessionMessage(
                        role="assistant",
                        content=str(synth_call.get("content", "")),
                        tool_calls=synth_call.get("tool_calls"),
                        synthetic=True,
                    )
                )
                self._session.updated_at = time.time()

        resolved_name = name or pending.get(normalized_id, "")
        content = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
        self._session.messages.append(
            SessionMessage(
                role="tool",
                content=content,
                tool_call_id=normalized_id,
                tool_name=resolved_name,
            )
        )
        self._session.updated_at = time.time()
        self._save()

    def set_summary(self, summary: str) -> None:
        if self._session:
            self._session.summary = summary
            self._session.updated_at = time.time()
            self._save()

    def replace_transcript(
        self,
        messages: List[Dict[str, Any]],
        summary: str = "",
        metadata_update: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Replace transcript in-place while keeping the same session identity."""
        if not self._session:
            self.new_session()
        if not self._session:
            return

        rewritten: List[SessionMessage] = []
        for raw in messages:
            msg = self._coerce_prompt_message(raw)
            if msg is not None:
                rewritten.append(msg)

        self._session.messages = rewritten
        self._session.summary = str(summary or "")
        if isinstance(metadata_update, dict) and metadata_update:
            merged = dict(self._session.metadata or {})
            merged.update(metadata_update)
            self._session.metadata = merged
        self._session.updated_at = time.time()
        self._save()

    def get_messages(self, limit: int = 0) -> List[SessionMessage]:
        if not self._session:
            return []
        if limit <= 0:
            return self._session.messages
        return self._session.messages[-limit:]

    def get_message_count(self) -> int:
        if not self._session:
            return 0
        return len(self._session.messages)

    def clear_messages(self) -> None:
        if self._session:
            self._session.messages.clear()
            self._session.updated_at = time.time()
            self._save()

    def _pending_tool_calls(self) -> Dict[str, str]:
        if not self._session:
            return {}
        raw_messages = [
            m.to_transcript_entry()
            for m in self._session.messages
        ]
        return collect_pending_tool_calls(raw_messages)

    def _flush_pending_tool_results(self) -> None:
        if not self._session:
            return
        pending = self._pending_tool_calls()
        if not pending:
            return
        for tc_id, tool_name in pending.items():
            synthetic = make_synthetic_tool_result(tc_id, tool_name)
            self._session.messages.append(
                SessionMessage(
                    role="tool",
                    content=str(synthetic.get("content", "")),
                    tool_call_id=str(synthetic.get("tool_call_id", "")),
                    tool_name=str(synthetic.get("tool_name", "")),
                    synthetic=True,
                )
            )
        self._session.updated_at = time.time()

    def list_sessions(self) -> List[Dict[str, Any]]:
        sessions = []
        for path in self._dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sessions.append(
                    {
                        "id": data.get("id", path.stem),
                        "created_at": data.get("created_at", 0),
                        "updated_at": data.get("updated_at", 0),
                        "schema_version": data.get("schema_version", 1),
                        "previous_session_id": data.get("previous_session_id", ""),
                        "message_count": len(data.get("messages", [])),
                    }
                )
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return sorted(sessions, key=lambda s: s["updated_at"], reverse=True)

    def _save(self) -> None:
        if not self._session:
            return
        with self._lock:
            path = self._dir / f"{self._session.id}.json"
            tmp_path = path.with_suffix(".tmp")
            data = {
                "id": self._session.id,
                "created_at": self._session.created_at,
                "updated_at": self._session.updated_at,
                "schema_version": self._session.schema_version,
                "summary": self._session.summary,
                "previous_session_id": self._session.previous_session_id,
                "metadata": self._session.metadata,
                "messages": [m.to_dict() for m in self._session.messages],
            }
            tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(path)

    def _build_continuation_message(self, source_id: str, summary: str) -> str:
        source_path = self._dir / f"{source_id}.json" if source_id else None
        safe_summary = str(summary or "").strip() or "(no summary generated)"
        lines = [
            "This is a continuation session after context summarization.",
            f"previous_session_id: {source_id or '(unknown)'}",
        ]
        if source_path is not None:
            lines.append(f"previous_session_path: {source_path.resolve()}")
        lines.append("Use this summary as prior context for follow-up decisions.")
        lines.append("summary:")
        lines.append(safe_summary)
        return "\n".join(lines)

    @staticmethod
    def _coerce_prompt_message(raw: Any) -> Optional[SessionMessage]:
        if not isinstance(raw, dict):
            return None
        role = str(raw.get("role", "")).strip()
        if role not in {"system", "user", "assistant", "tool"}:
            return None

        content_raw = raw.get("content", "")
        if isinstance(content_raw, str):
            content = content_raw
        elif isinstance(content_raw, (dict, list)):
            content = json.dumps(content_raw, ensure_ascii=False)
        elif content_raw is None:
            content = ""
        else:
            content = str(content_raw)

        tool_calls = None
        if role == "assistant":
            tool_calls = normalize_tool_calls(raw.get("tool_calls"))

        tool_call_id = str(raw.get("tool_call_id", "")).strip()
        tool_name = str(raw.get("tool_name", raw.get("name", ""))).strip()
        synthetic = bool(raw.get("synthetic", False))

        return SessionMessage(
            role=role,
            content=content,
            tool_call_id=tool_call_id,
            tool_calls=tool_calls,
            tool_name=tool_name,
            synthetic=synthetic,
        )

    @staticmethod
    def _coerce_session_message(raw: Any) -> Optional[SessionMessage]:
        return SessionMessage.from_dict(raw)
