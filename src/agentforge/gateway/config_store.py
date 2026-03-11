from __future__ import annotations

import copy
import json
import os
import threading
from typing import Any, Dict


CHANNEL_NAMES = ("telegram", "discord", "zalo")
DM_POLICIES = {"pairing", "allowlist", "open", "disabled"}
GROUP_POLICIES = {"allowlist", "open", "disabled"}

SECRET_FIELDS = {
    "telegram": "botToken",
    "discord": "token",
    "zalo": "botToken",
}

ENV_FALLBACKS = {
    "telegram": "TELEGRAM_BOT_TOKEN",
    "discord": "DISCORD_BOT_TOKEN",
    "zalo": "ZALO_BOT_TOKEN",
}


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _normalize_int(value: Any, default: int, *, minimum: int = 1, maximum: int = 300) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _normalize_policy(value: Any, *, allowed: set[str], default: str) -> str:
    normalized = _normalize_string(value).lower()
    return normalized if normalized in allowed else default


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    normalized: list[str] = []
    for item in raw_items:
        rendered = _normalize_string(item)
        if rendered and rendered not in normalized:
            normalized.append(rendered)
    return normalized


def _normalize_scope_config(value: Any, *, default_require_mention: bool) -> Dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    allow_from = _normalize_string_list(data.get("allowFrom"))
    if not allow_from:
        allow_from = _normalize_string_list(data.get("users"))
    return {
        "requireMention": _normalize_bool(data.get("requireMention"), default_require_mention),
        "allowFrom": allow_from,
        "groupPolicy": _normalize_policy(
            data.get("groupPolicy"),
            allowed=GROUP_POLICIES,
            default="allowlist",
        ),
        "title": _normalize_string(data.get("title")),
    }


def _normalize_scope_map(value: Any, *, default_require_mention: bool) -> Dict[str, Dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_key, raw_value in value.items():
        key = _normalize_string(raw_key)
        if not key:
            continue
        normalized[key] = _normalize_scope_config(
            raw_value,
            default_require_mention=default_require_mention,
        )
    return normalized


def _default_channel_config(channel: str) -> Dict[str, Any]:
    base = {
        "enabled": False,
        "dmPolicy": "pairing",
        "allowFrom": [],
        "groupPolicy": "allowlist",
        "groupAllowFrom": [],
        "requireMention": True,
        "pollIntervalSeconds": 3,
        "webhookUrl": "",
        "webhookSecret": "",
        "webhookPath": "",
        "proxy": "",
    }
    if channel == "discord":
        base["token"] = ""
        base["guilds"] = {}
    else:
        base["botToken"] = ""
        base["groups"] = {}
    return base


def normalize_channel_config(channel: str, value: Any) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    normalized = _default_channel_config(channel)
    normalized["enabled"] = _normalize_bool(raw.get("enabled"), False)
    normalized["dmPolicy"] = _normalize_policy(
        raw.get("dmPolicy"),
        allowed=DM_POLICIES,
        default="pairing",
    )
    normalized["allowFrom"] = _normalize_string_list(raw.get("allowFrom"))
    normalized["groupPolicy"] = _normalize_policy(
        raw.get("groupPolicy"),
        allowed=GROUP_POLICIES,
        default="allowlist",
    )
    normalized["groupAllowFrom"] = _normalize_string_list(raw.get("groupAllowFrom"))
    normalized["requireMention"] = _normalize_bool(raw.get("requireMention"), True)
    normalized["pollIntervalSeconds"] = _normalize_int(
        raw.get("pollIntervalSeconds"),
        3,
        minimum=1,
        maximum=60,
    )
    normalized["webhookUrl"] = _normalize_string(raw.get("webhookUrl"))
    normalized["webhookSecret"] = _normalize_string(raw.get("webhookSecret"))
    normalized["webhookPath"] = _normalize_string(raw.get("webhookPath"))
    normalized["proxy"] = _normalize_string(raw.get("proxy"))

    secret_field = SECRET_FIELDS[channel]
    normalized[secret_field] = _normalize_string(raw.get(secret_field))

    if channel == "discord":
        normalized["guilds"] = _normalize_scope_map(
            raw.get("guilds"),
            default_require_mention=normalized["requireMention"],
        )
    else:
        normalized["groups"] = _normalize_scope_map(
            raw.get("groups"),
            default_require_mention=normalized["requireMention"],
        )
    return normalized


def normalize_gateway_config(value: Any) -> Dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    channels = raw.get("channels", {}) if isinstance(raw.get("channels"), dict) else {}
    normalized = {
        "version": 1,
        "channels": {},
    }
    for channel in CHANNEL_NAMES:
        normalized["channels"][channel] = normalize_channel_config(channel, channels.get(channel))
    return normalized


def _json_copy(value: Any) -> Any:
    return copy.deepcopy(value)


class GatewayConfigStore:
    def __init__(self, workspace_dir: str):
        self._gateway_dir = os.path.join(workspace_dir, "gateway")
        self._path = os.path.join(self._gateway_dir, "config.json")
        self._lock = threading.RLock()
        os.makedirs(self._gateway_dir, exist_ok=True)
        self._config = normalize_gateway_config({})
        self._load()
        self._save()

    @property
    def path(self) -> str:
        return self._path

    def _load(self) -> None:
        if not os.path.isfile(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                self._config = normalize_gateway_config(json.load(handle))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self._config = normalize_gateway_config({})

    def _save(self) -> None:
        payload = _json_copy(self._config)
        tmp_path = self._path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self._path)

    def get_config(self) -> Dict[str, Any]:
        with self._lock:
            return _json_copy(self._config)

    def get_channel_config(self, channel: str) -> Dict[str, Any]:
        if channel not in CHANNEL_NAMES:
            raise KeyError(f"Unknown channel: {channel}")
        with self._lock:
            return _json_copy(self._config["channels"][channel])

    def update_channel(self, channel: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        if channel not in CHANNEL_NAMES:
            raise KeyError(f"Unknown channel: {channel}")
        current = self.get_channel_config(channel)
        merged = dict(current)
        merged.update(patch if isinstance(patch, dict) else {})
        normalized = normalize_channel_config(channel, merged)
        with self._lock:
            self._config["channels"][channel] = normalized
            self._save()
            return _json_copy(normalized)

    def resolve_token(self, channel: str) -> str:
        channel_cfg = self.get_channel_config(channel)
        secret_field = SECRET_FIELDS[channel]
        configured = _normalize_string(channel_cfg.get(secret_field))
        if configured:
            return configured
        env_name = ENV_FALLBACKS[channel]
        return _normalize_string(os.environ.get(env_name))

    def is_configured(self, channel: str) -> bool:
        return bool(self.resolve_token(channel))

    def public_channel_config(self, channel: str) -> Dict[str, Any]:
        cfg = self.get_channel_config(channel)
        cfg.pop(SECRET_FIELDS[channel], None)
        cfg["configured"] = self.is_configured(channel)
        return cfg
