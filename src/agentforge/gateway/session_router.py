"""
SessionRouter — logical session routing and index persistence.

Maps ``session_key`` (e.g. ``main``) to a ``session_id`` (UUID) and
maintains a JSON index at ``workspace/gateway/session_index.json``.
Each logical session holds an ``AgentRuntimeHandle`` containing the
live ``Agent``, ``SessionManager``, and related components.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..agent_core import Agent, AgentConfig
from ..context import ContextBuilder
from ..llm_inference import InferenceConfig, LLMInference
from ..session import SessionManager
from ..skills import SkillLoader
from ..summarizer import Summarizer
from ..tools import ToolRegistry

logger = logging.getLogger(__name__)


@dataclass
class SessionEntry:
    """Persisted session index entry."""

    session_key: str
    session_id: str
    channel: str = "webchat"
    peer_type: str = "dm"
    peer_id: str = "main"
    account_id: str = "default"
    title: str = ""
    selected_model_id: str = ""
    last_route: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_key": self.session_key,
            "session_id": self.session_id,
            "channel": self.channel,
            "peer_type": self.peer_type,
            "peer_id": self.peer_id,
            "account_id": self.account_id,
            "title": self.title,
            "selected_model_id": self.selected_model_id,
            "last_route": self.last_route,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionEntry":
        return cls(
            session_key=str(data.get("session_key", "")),
            session_id=str(data.get("session_id", "")),
            channel=str(data.get("channel", "webchat")),
            peer_type=str(data.get("peer_type", "dm")),
            peer_id=str(data.get("peer_id", "main")),
            account_id=str(data.get("account_id", "default")),
            title=str(data.get("title", "")),
            selected_model_id=str(data.get("selected_model_id", "")),
            last_route=data.get("last_route", {}) if isinstance(data.get("last_route"), dict) else {},
            created_at=float(data.get("created_at", 0)),
            updated_at=float(data.get("updated_at", 0)),
        )


@dataclass
class AgentRuntimeHandle:
    """Live runtime state for one logical session."""

    entry: SessionEntry
    agent: Agent
    session_mgr: SessionManager
    tools: ToolRegistry
    skill_loader: SkillLoader
    context_builder: ContextBuilder
    summarizer: Summarizer
    llm: LLMInference


class SessionRouter:
    """Manages the mapping of session_key -> Agent runtime handles."""

    def __init__(self, workspace_dir: str, agent_config: AgentConfig):
        self._workspace_dir = workspace_dir
        self._agent_config = agent_config
        self._gateway_dir = os.path.join(workspace_dir, "gateway")
        self._index_path = os.path.join(self._gateway_dir, "session_index.json")
        self._handles: Dict[str, AgentRuntimeHandle] = {}
        self._entries: Dict[str, SessionEntry] = {}

        os.makedirs(self._gateway_dir, exist_ok=True)
        self._load_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create(
        self,
        session_key: str,
        *,
        llm_factory: Any,
        inference_config: InferenceConfig,
        channel: str = "webchat",
        peer_type: str = "dm",
        peer_id: str = "main",
        account_id: str = "default",
        title: str = "",
    ) -> AgentRuntimeHandle:
        """Return the existing handle or create a new one for *session_key*."""
        entry = self._entries.get(session_key)
        if entry is None:
            entry = SessionEntry(
                session_key=session_key,
                session_id=uuid.uuid4().hex[:8],
                channel=channel,
                peer_type=peer_type,
                peer_id=peer_id,
                account_id=account_id,
                title=title,
                created_at=time.time(),
                updated_at=time.time(),
            )
            self._entries[session_key] = entry
            self._save_index()
        else:
            updated = False
            for field_name, field_value in {
                "channel": channel,
                "peer_type": peer_type,
                "peer_id": peer_id,
                "account_id": account_id,
            }.items():
                if field_value and getattr(entry, field_name) != field_value:
                    setattr(entry, field_name, field_value)
                    updated = True
            if title and entry.title != title:
                entry.title = title
                updated = True
            if updated:
                entry.updated_at = time.time()
                self._save_index()

        if session_key in self._handles:
            return self._handles[session_key]

        handle = self._build_handle(entry, llm_factory, inference_config)
        self._handles[session_key] = handle
        return handle

    def reset_session(
        self,
        session_key: str,
        *,
        llm_factory: Any,
        inference_config: InferenceConfig,
    ) -> AgentRuntimeHandle:
        """Reset a session: new transcript, same session_key."""
        old_entry = self._entries.get(session_key)
        model_id = old_entry.selected_model_id if old_entry else ""

        new_entry = SessionEntry(
            session_key=session_key,
            session_id=uuid.uuid4().hex[:8],
            channel=old_entry.channel if old_entry else "webchat",
            peer_type=old_entry.peer_type if old_entry else "dm",
            peer_id=old_entry.peer_id if old_entry else "main",
            account_id=old_entry.account_id if old_entry else "default",
            title=old_entry.title if old_entry else "",
            selected_model_id=model_id,
            last_route=dict(old_entry.last_route) if old_entry else {},
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._entries[session_key] = new_entry
        self._save_index()

        handle = self._build_handle(new_entry, llm_factory, inference_config)
        self._handles[session_key] = handle
        return handle

    def set_model(self, session_key: str, model_id: str) -> bool:
        """Update the selected model for a logical session."""
        entry = self._entries.get(session_key)
        if entry is None:
            return False
        entry.selected_model_id = model_id
        entry.updated_at = time.time()
        self._save_index()
        return True

    def update_route(
        self,
        session_key: str,
        *,
        channel: str,
        peer_type: str,
        peer_id: str,
        account_id: str = "default",
        title: str = "",
        route: Optional[Dict[str, Any]] = None,
    ) -> bool:
        entry = self._entries.get(session_key)
        if entry is None:
            return False
        entry.channel = channel or entry.channel
        entry.peer_type = peer_type or entry.peer_type
        entry.peer_id = peer_id or entry.peer_id
        entry.account_id = account_id or entry.account_id
        if title:
            entry.title = title
        if isinstance(route, dict) and route:
            entry.last_route = dict(route)
        entry.updated_at = time.time()
        self._save_index()
        return True

    def list_sessions(self) -> List[Dict[str, Any]]:
        return [entry.to_dict() for entry in self._entries.values()]

    def get_entry(self, session_key: str) -> Optional[SessionEntry]:
        return self._entries.get(session_key)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_handle(
        self,
        entry: SessionEntry,
        llm_factory: Any,
        inference_config: InferenceConfig,
    ) -> AgentRuntimeHandle:
        sessions_dir = os.path.join(self._workspace_dir, "sessions")
        session_mgr = SessionManager(sessions_dir)
        session = session_mgr.load_session(entry.session_id)
        if not session:
            session = session_mgr.new_session(session_id=entry.session_id)

        skill_loader = SkillLoader(self._workspace_dir)
        context_builder = ContextBuilder(self._workspace_dir)
        summarizer = Summarizer(max_tokens=inference_config.n_ctx)
        tools = ToolRegistry()

        skill_loader.discover()

        llm: LLMInference = llm_factory()

        agent = Agent(
            config=self._agent_config,
            llm=llm,
            tools=tools,
            session_mgr=session_mgr,
            summarizer=summarizer,
            skill_loader=skill_loader,
            context_builder=context_builder,
        )

        return AgentRuntimeHandle(
            entry=entry,
            agent=agent,
            session_mgr=session_mgr,
            tools=tools,
            skill_loader=skill_loader,
            context_builder=context_builder,
            summarizer=summarizer,
            llm=llm,
        )

    def _load_index(self) -> None:
        if not os.path.isfile(self._index_path):
            return
        try:
            with open(self._index_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for item in data.get("sessions", []):
                entry = SessionEntry.from_dict(item)
                self._entries[entry.session_key] = entry
        except Exception:
            logger.exception("Failed to load session index.")

    def _save_index(self) -> None:
        payload = {"sessions": [e.to_dict() for e in self._entries.values()]}
        tmp = self._index_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self._index_path)
        except Exception:
            logger.exception("Failed to save session index.")
