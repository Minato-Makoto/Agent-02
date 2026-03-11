"""
ConnectionManager — WebSocket connection tracking and broadcast.

Keeps a set of active WebSocket connections and provides helpers to
broadcast structured JSON events.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Track active WebSocket connections and broadcast events."""

    def __init__(self):
        self._connections: Set[WebSocket] = set()
        # session_key -> set of websockets attached to that session
        self._session_subs: Dict[str, Set[WebSocket]] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        for subs in self._session_subs.values():
            subs.discard(ws)

    def attach_to_session(self, ws: WebSocket, session_key: str) -> None:
        """Subscribe a WebSocket to events for a specific session."""
        # Detach from any current session first
        for subs in self._session_subs.values():
            subs.discard(ws)
        self._session_subs.setdefault(session_key, set()).add(ws)

    async def send_to(self, ws: WebSocket, msg: Dict[str, Any]) -> None:
        """Send a JSON message to one WebSocket."""
        try:
            await ws.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            logger.debug("Failed to send to WebSocket.", exc_info=True)
            self.disconnect(ws)

    async def broadcast_to_session(self, session_key: str, msg: Dict[str, Any]) -> None:
        """Broadcast a JSON message to all subscribers of a session."""
        targets = list(self._session_subs.get(session_key, set()))
        for ws in targets:
            await self.send_to(ws, msg)

    async def broadcast_all(self, msg: Dict[str, Any]) -> None:
        """Broadcast a JSON message to all connected WebSockets."""
        for ws in list(self._connections):
            await self.send_to(ws, msg)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
