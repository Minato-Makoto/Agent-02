from __future__ import annotations

import json
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


PAIRING_EXPIRY_SECONDS = 3600
PAIRING_PENDING_LIMIT = 3
PAIRING_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


@dataclass
class PairingRequest:
    channel: str
    code: str
    sender_id: str
    sender_name: str = ""
    peer_id: str = ""
    created_at: float = 0.0
    expires_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        now = time.time()
        if self.created_at <= 0:
            self.created_at = now
        if self.expires_at <= 0:
            self.expires_at = self.created_at + PAIRING_EXPIRY_SECONDS

    @property
    def expired(self) -> bool:
        return self.expires_at <= time.time()


class PairingStore:
    def __init__(self, workspace_dir: str):
        self._credentials_dir = os.path.join(workspace_dir, "credentials")
        self._lock = threading.RLock()
        os.makedirs(self._credentials_dir, exist_ok=True)

    def _pending_path(self, channel: str) -> str:
        return os.path.join(self._credentials_dir, f"{channel}-pairing.json")

    def _allow_path(self, channel: str) -> str:
        return os.path.join(self._credentials_dir, f"{channel}-allowFrom.json")

    def _load_json(self, path: str, default: Dict[str, Any]) -> Dict[str, Any]:
        if not os.path.isfile(path):
            return dict(default)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                value = json.load(handle)
            return value if isinstance(value, dict) else dict(default)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return dict(default)

    def _save_json(self, path: str, payload: Dict[str, Any]) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    def _load_pending(self, channel: str) -> list[PairingRequest]:
        raw = self._load_json(self._pending_path(channel), {"pending": []})
        pending: list[PairingRequest] = []
        for item in raw.get("pending", []):
            if not isinstance(item, dict):
                continue
            request = PairingRequest(
                channel=channel,
                code=str(item.get("code", "")).strip(),
                sender_id=str(item.get("sender_id", "")).strip(),
                sender_name=str(item.get("sender_name", "")).strip(),
                peer_id=str(item.get("peer_id", "")).strip(),
                created_at=float(item.get("created_at", 0.0) or 0.0),
                expires_at=float(item.get("expires_at", 0.0) or 0.0),
                metadata=item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {},
            )
            if request.code and request.sender_id and not request.expired:
                pending.append(request)
        if len(pending) != len(raw.get("pending", [])):
            self._save_pending(channel, pending)
        return pending

    def _save_pending(self, channel: str, requests: list[PairingRequest]) -> None:
        payload = {
            "channel": channel,
            "pending": [asdict(request) for request in requests if not request.expired],
        }
        self._save_json(self._pending_path(channel), payload)

    def _load_allow_from(self, channel: str) -> list[str]:
        raw = self._load_json(self._allow_path(channel), {"approved": []})
        approved: list[str] = []
        for item in raw.get("approved", []):
            sender_id = str(item).strip()
            if sender_id and sender_id not in approved:
                approved.append(sender_id)
        if len(approved) != len(raw.get("approved", [])):
            self._save_allow_from(channel, approved)
        return approved

    def _save_allow_from(self, channel: str, approved: list[str]) -> None:
        payload = {
            "channel": channel,
            "updated_at": time.time(),
            "approved": approved,
        }
        self._save_json(self._allow_path(channel), payload)

    def _generate_code(self) -> str:
        return "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(8))

    def _known_channels(self) -> list[str]:
        channels = set()
        for filename in os.listdir(self._credentials_dir):
            if filename.endswith(".json") and "-" in filename:
                channels.add(filename.split("-", 1)[0])
        return sorted(channels)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            channels = {}
            for channel in self._known_channels():
                channels[channel] = {
                    "pending": [asdict(item) for item in self._load_pending(channel)],
                    "approved": self._load_allow_from(channel),
                }
            return {"channels": channels}

    def list_pending(self, channel: Optional[str] = None) -> list[Dict[str, Any]]:
        with self._lock:
            channels = [channel] if channel else self._known_channels()
            pending: list[Dict[str, Any]] = []
            for name in channels:
                pending.extend(asdict(item) for item in self._load_pending(name))
            return sorted(pending, key=lambda item: item.get("created_at", 0.0), reverse=True)

    def list_approved(self, channel: Optional[str] = None) -> Dict[str, list[str]]:
        with self._lock:
            channels = [channel] if channel else self._known_channels()
            return {name: self._load_allow_from(name) for name in channels}

    def is_allowed(self, channel: str, sender_id: str) -> bool:
        normalized = str(sender_id or "").strip()
        if not normalized:
            return False
        with self._lock:
            return normalized in self._load_allow_from(channel)

    def issue_request(
        self,
        channel: str,
        sender_id: str,
        *,
        sender_name: str = "",
        peer_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[PairingRequest], bool]:
        normalized_sender = str(sender_id or "").strip()
        if not normalized_sender:
            return None, False
        with self._lock:
            if self.is_allowed(channel, normalized_sender):
                return None, False
            pending = self._load_pending(channel)
            for existing in pending:
                if existing.sender_id == normalized_sender:
                    return existing, False
            if len(pending) >= PAIRING_PENDING_LIMIT:
                return None, False
            request = PairingRequest(
                channel=channel,
                code=self._generate_code(),
                sender_id=normalized_sender,
                sender_name=str(sender_name or "").strip(),
                peer_id=str(peer_id or "").strip(),
                metadata=metadata or {},
            )
            pending.append(request)
            self._save_pending(channel, pending)
            return request, True

    def approve(self, channel: str, code: str) -> Optional[PairingRequest]:
        normalized_code = str(code or "").strip().upper()
        if not normalized_code:
            return None
        with self._lock:
            pending = self._load_pending(channel)
            approved = self._load_allow_from(channel)
            selected: Optional[PairingRequest] = None
            remaining: list[PairingRequest] = []
            for request in pending:
                if selected is None and request.code.upper() == normalized_code:
                    selected = request
                    continue
                remaining.append(request)
            if selected is None:
                return None
            if selected.sender_id not in approved:
                approved.append(selected.sender_id)
            self._save_allow_from(channel, approved)
            self._save_pending(channel, remaining)
            return selected

    def reject(self, channel: str, code: str) -> bool:
        normalized_code = str(code or "").strip().upper()
        if not normalized_code:
            return False
        with self._lock:
            pending = self._load_pending(channel)
            remaining = [request for request in pending if request.code.upper() != normalized_code]
            if len(remaining) == len(pending):
                return False
            self._save_pending(channel, remaining)
            return True

    def revoke(self, channel: str, sender_id: str) -> bool:
        normalized_sender = str(sender_id or "").strip()
        if not normalized_sender:
            return False
        with self._lock:
            approved = self._load_allow_from(channel)
            if normalized_sender not in approved:
                return False
            approved = [item for item in approved if item != normalized_sender]
            self._save_allow_from(channel, approved)
            return True
