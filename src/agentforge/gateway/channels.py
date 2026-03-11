from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

import requests

from .config_store import CHANNEL_NAMES, GatewayConfigStore
from .pairing import PairingRequest, PairingStore

logger = logging.getLogger(__name__)

try:
    import discord  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - optional dependency in tests
    discord = None


INBOUND_CALLBACK = Callable[["ChannelEnvelope"], None]


@dataclass
class ChannelEnvelope:
    channel: str
    peer_type: str
    peer_id: str
    sender_id: str
    text: str
    sender_name: str = ""
    account_id: str = "default"
    target_id: str = ""
    message_id: str = ""
    mentioned: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def route_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "peer_type": self.peer_type,
            "peer_id": self.peer_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "account_id": self.account_id,
            "target_id": self.target_id or self.peer_id,
            "message_id": self.message_id,
            "metadata": dict(self.metadata or {}),
        }


class ChannelAdapter:
    runtime_mode = "unknown"

    def __init__(self, channel_name: str, config_store: GatewayConfigStore):
        self.channel_name = channel_name
        self._config_store = config_store
        self._manager: Optional["ChannelManager"] = None
        self._running = False
        self._connected = False
        self._last_error = ""
        self._last_inbound_at = 0.0
        self._last_outbound_at = 0.0
        self._status_detail = ""

    def attach_manager(self, manager: "ChannelManager") -> None:
        self._manager = manager

    def runtime_state(self) -> Dict[str, Any]:
        status = "stopped"
        if self._running and self._connected:
            status = "running"
        elif self._running:
            status = "starting"
        elif self._last_error:
            status = "error"
        return {
            "status": status,
            "connected": self._connected,
            "running": self._running,
            "last_error": self._last_error,
            "last_inbound_at": self._last_inbound_at,
            "last_outbound_at": self._last_outbound_at,
            "detail": self._status_detail,
            "runtime_mode": self.runtime_mode,
        }

    def set_error(self, message: str) -> None:
        self._last_error = str(message or "").strip()
        self._connected = False
        if self._last_error:
            logger.warning("%s adapter error: %s", self.channel_name, self._last_error)

    def clear_error(self) -> None:
        self._last_error = ""

    def mark_inbound(self) -> None:
        self._last_inbound_at = time.time()

    def mark_outbound(self) -> None:
        self._last_outbound_at = time.time()

    def set_connected(self, connected: bool, detail: str = "") -> None:
        self._connected = connected
        self._status_detail = detail
        if connected:
            self.clear_error()

    def start(self) -> None:
        self._running = False

    def stop(self) -> None:
        self._running = False
        self._connected = False

    def probe(self) -> Dict[str, Any]:
        return {"ok": False, "error": "Probe not implemented."}

    def send_text(self, route: Dict[str, Any], text: str) -> bool:
        raise NotImplementedError


class PollingAdapter(ChannelAdapter):
    def __init__(self, channel_name: str, config_store: GatewayConfigStore):
        super().__init__(channel_name, config_store)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        token = self._config_store.resolve_token(self.channel_name)
        if not token:
            self.set_error("Channel token is not configured.")
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._run_wrapper,
            name=f"{self.channel_name}-adapter",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self._connected = False

    def _run_wrapper(self) -> None:
        try:
            self._run_loop()
        except Exception as exc:  # pragma: no cover
            self.set_error(str(exc))
        finally:
            self._running = False

    def _run_loop(self) -> None:
        raise NotImplementedError

    def _publish(self, envelope: ChannelEnvelope) -> None:
        if self._manager is None:
            return
        self.mark_inbound()
        self._manager.publish_inbound(envelope)


class TelegramAdapter(PollingAdapter):
    runtime_mode = "polling"

    def __init__(self, config_store: GatewayConfigStore):
        super().__init__("telegram", config_store)
        self._offset = 0
        self._bot_username = ""

    def probe(self) -> Dict[str, Any]:
        token = self._config_store.resolve_token("telegram")
        if not token:
            return {"ok": False, "error": "missing token"}
        base = f"https://api.telegram.org/bot{token}"
        started = time.time()
        try:
            response = requests.get(f"{base}/getMe", timeout=5)
            payload = response.json()
            if response.status_code != 200 or not payload.get("ok"):
                return {
                    "ok": False,
                    "error": payload.get("description", f"getMe failed ({response.status_code})"),
                    "status": response.status_code,
                    "elapsedMs": int((time.time() - started) * 1000),
                }
            result = payload.get("result", {}) if isinstance(payload.get("result"), dict) else {}
            self._bot_username = str(result.get("username", "") or "")
            return {
                "ok": True,
                "bot": {"id": result.get("id"), "username": result.get("username")},
                "elapsedMs": int((time.time() - started) * 1000),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "elapsedMs": int((time.time() - started) * 1000)}

    def _run_loop(self) -> None:
        token = self._config_store.resolve_token("telegram")
        if not token:
            self.set_error("Channel token is not configured.")
            return
        probe = self.probe()
        if not probe.get("ok"):
            self.set_error(str(probe.get("error", "Probe failed")))
            return
        self.set_connected(True, "Polling Telegram Bot API")
        base = f"https://api.telegram.org/bot{token}"
        while not self._stop_event.is_set():
            try:
                payload: Dict[str, Any] = {"timeout": 25}
                if self._offset > 0:
                    payload["offset"] = self._offset
                response = requests.post(f"{base}/getUpdates", json=payload, timeout=35)
                data = response.json()
                if response.status_code != 200 or not data.get("ok"):
                    self.set_error(str(data.get("description", f"getUpdates failed ({response.status_code})")))
                    time.sleep(3)
                    continue
                self.set_connected(True, "Polling Telegram Bot API")
                for item in data.get("result", []):
                    try:
                        update_id = int(item.get("update_id", 0) or 0)
                    except (TypeError, ValueError):
                        update_id = 0
                    if update_id > 0:
                        self._offset = max(self._offset, update_id + 1)
                    envelope = self._parse_update(item)
                    if envelope is not None:
                        self._publish(envelope)
            except Exception as exc:
                self.set_error(str(exc))
                time.sleep(3)

    def _parse_update(self, update: Dict[str, Any]) -> Optional[ChannelEnvelope]:
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            return None
        chat = message.get("chat", {})
        sender = message.get("from", {})
        if not isinstance(chat, dict) or not isinstance(sender, dict):
            return None
        text = str(message.get("text") or message.get("caption") or "").strip()
        if not text:
            if message.get("photo"):
                text = "[Image]"
            elif message.get("document"):
                text = "[Attachment]"
            else:
                return None
        chat_id = str(chat.get("id", "")).strip()
        sender_id = str(sender.get("id", "")).strip()
        if not chat_id or not sender_id:
            return None
        chat_type = str(chat.get("type", "")).strip().lower()
        peer_type = "dm" if chat_type == "private" else "group"
        sender_name = (
            str(sender.get("username") or "").strip()
            or " ".join(
                part
                for part in [
                    str(sender.get("first_name") or "").strip(),
                    str(sender.get("last_name") or "").strip(),
                ]
                if part
            )
            or sender_id
        )
        mentioned = peer_type == "dm" or self._message_mentions_bot(message, text)
        return ChannelEnvelope(
            channel="telegram",
            peer_type=peer_type,
            peer_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
            text=text,
            target_id=chat_id,
            message_id=str(message.get("message_id", "")).strip(),
            mentioned=mentioned,
            metadata={"chat_type": chat_type, "update_id": str(update.get("update_id", ""))},
        )

    def _message_mentions_bot(self, message: Dict[str, Any], text: str) -> bool:
        if not self._bot_username:
            return False
        mention_text = f"@{self._bot_username.lower()}"
        if mention_text in text.lower():
            return True
        entities = message.get("entities")
        if not isinstance(entities, list):
            return False
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            if str(entity.get("type", "")).strip().lower() != "mention":
                continue
            offset = int(entity.get("offset", 0) or 0)
            length = int(entity.get("length", 0) or 0)
            if text[offset : offset + length].lower() == mention_text:
                return True
        return False

    def send_text(self, route: Dict[str, Any], text: str) -> bool:
        token = self._config_store.resolve_token("telegram")
        target_id = str(route.get("target_id") or route.get("peer_id") or "").strip()
        if not token or not target_id:
            return False
        base = f"https://api.telegram.org/bot{token}"
        for chunk in _chunk_text(text, limit=4096):
            payload = {"chat_id": target_id, "text": chunk}
            reply_to_id = str(route.get("message_id") or "").strip()
            if reply_to_id.isdigit():
                payload["reply_to_message_id"] = int(reply_to_id)
            try:
                response = requests.post(f"{base}/sendMessage", json=payload, timeout=15)
                data = response.json()
                if response.status_code != 200 or not data.get("ok"):
                    self.set_error(str(data.get("description", f"sendMessage failed ({response.status_code})")))
                    return False
            except Exception as exc:
                self.set_error(str(exc))
                return False
        self.mark_outbound()
        return True


def _chunk_text(text: str, *, limit: int) -> list[str]:
    rendered = str(text or "").strip()
    if not rendered:
        return [""]
    chunks: list[str] = []
    remaining = rendered
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at <= 0:
            split_at = limit
        chunk = remaining[:split_at].strip()
        if not chunk:
            chunk = remaining[:limit]
            split_at = limit
        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks or [rendered]


class ZaloAdapter(PollingAdapter):
    runtime_mode = "polling"

    def __init__(self, config_store: GatewayConfigStore):
        super().__init__("zalo", config_store)
        self._bot_name = ""

    def probe(self) -> Dict[str, Any]:
        token = self._config_store.resolve_token("zalo")
        if not token:
            return {"ok": False, "error": "missing token"}
        started = time.time()
        try:
            response = requests.post(
                f"https://bot-api.zaloplatforms.com/bot{token}/getMe",
                timeout=5,
            )
            payload = response.json()
            if response.status_code != 200 or not payload.get("ok"):
                return {
                    "ok": False,
                    "error": payload.get("description", f"getMe failed ({response.status_code})"),
                    "status": response.status_code,
                    "elapsedMs": int((time.time() - started) * 1000),
                }
            result = payload.get("result", {}) if isinstance(payload.get("result"), dict) else {}
            self._bot_name = str(result.get("name", "") or "")
            return {
                "ok": True,
                "bot": result,
                "elapsedMs": int((time.time() - started) * 1000),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "elapsedMs": int((time.time() - started) * 1000)}

    def _run_loop(self) -> None:
        token = self._config_store.resolve_token("zalo")
        if not token:
            self.set_error("Channel token is not configured.")
            return
        probe = self.probe()
        if not probe.get("ok"):
            self.set_error(str(probe.get("error", "Probe failed")))
            return
        self.set_connected(True, "Polling Zalo Bot API")
        base = f"https://bot-api.zaloplatforms.com/bot{token}"
        while not self._stop_event.is_set():
            try:
                response = requests.post(
                    f"{base}/getUpdates",
                    json={"timeout": "30"},
                    timeout=35,
                )
                payload = response.json()
                if response.status_code != 200 or not payload.get("ok"):
                    description = payload.get("description", f"getUpdates failed ({response.status_code})")
                    if payload.get("error_code") != 408:
                        self.set_error(str(description))
                        time.sleep(3)
                    continue
                self.set_connected(True, "Polling Zalo Bot API")
                update = payload.get("result")
                if isinstance(update, dict):
                    envelope = self._parse_update(update)
                    if envelope is not None:
                        self._publish(envelope)
            except Exception as exc:
                self.set_error(str(exc))
                time.sleep(3)

    def _parse_update(self, update: Dict[str, Any]) -> Optional[ChannelEnvelope]:
        message = update.get("message")
        if not isinstance(message, dict):
            return None
        text = str(message.get("text") or message.get("caption") or "").strip()
        if not text:
            if message.get("photo"):
                text = "[Image]"
            elif message.get("sticker"):
                text = "[Sticker]"
            else:
                return None
        sender = message.get("from", {})
        chat = message.get("chat", {})
        if not isinstance(sender, dict) or not isinstance(chat, dict):
            return None
        chat_id = str(chat.get("id", "")).strip()
        sender_id = str(sender.get("id", "")).strip()
        if not chat_id or not sender_id:
            return None
        chat_type = str(chat.get("chat_type", "")).strip().upper()
        peer_type = "dm" if chat_type == "PRIVATE" else "group"
        sender_name = str(sender.get("name") or "").strip() or sender_id
        bot_name = self._bot_name.lower()
        mentioned = peer_type == "dm" or (bool(bot_name) and bot_name in text.lower())
        return ChannelEnvelope(
            channel="zalo",
            peer_type=peer_type,
            peer_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
            text=text,
            target_id=chat_id,
            message_id=str(message.get("message_id", "")).strip(),
            mentioned=mentioned,
            metadata={
                "event_name": str(update.get("event_name", "")),
                "chat_type": chat_type,
            },
        )

    def send_text(self, route: Dict[str, Any], text: str) -> bool:
        token = self._config_store.resolve_token("zalo")
        target_id = str(route.get("target_id") or route.get("peer_id") or "").strip()
        if not token or not target_id:
            return False
        base = f"https://bot-api.zaloplatforms.com/bot{token}"
        for chunk in _chunk_text(text, limit=2000):
            try:
                response = requests.post(
                    f"{base}/sendMessage",
                    json={"chat_id": target_id, "text": chunk},
                    timeout=15,
                )
                payload = response.json()
                if response.status_code != 200 or not payload.get("ok"):
                    self.set_error(str(payload.get("description", f"sendMessage failed ({response.status_code})")))
                    return False
            except Exception as exc:
                self.set_error(str(exc))
                return False
        self.mark_outbound()
        return True


class DiscordAdapter(ChannelAdapter):
    runtime_mode = "gateway"

    def __init__(self, config_store: GatewayConfigStore):
        super().__init__("discord", config_store)
        self._loop = None
        self._client = None
        self._thread: Optional[threading.Thread] = None
        self._user_id = ""

    def probe(self) -> Dict[str, Any]:
        token = self._config_store.resolve_token("discord")
        if not token:
            return {"ok": False, "error": "missing token"}
        headers = {"Authorization": f"Bot {token}"}
        started = time.time()
        try:
            response = requests.get("https://discord.com/api/v10/users/@me", headers=headers, timeout=5)
            payload = response.json()
            if response.status_code != 200:
                return {
                    "ok": False,
                    "error": payload.get("message", f"getMe failed ({response.status_code})"),
                    "status": response.status_code,
                    "elapsedMs": int((time.time() - started) * 1000),
                }
            return {
                "ok": True,
                "bot": {
                    "id": payload.get("id"),
                    "username": payload.get("username"),
                },
                "elapsedMs": int((time.time() - started) * 1000),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "elapsedMs": int((time.time() - started) * 1000)}

    def start(self) -> None:
        if self._running:
            return
        token = self._config_store.resolve_token("discord")
        if not token:
            self.set_error("Channel token is not configured.")
            return
        if discord is None:
            self.set_error("discord.py is not installed.")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_client, name="discord-adapter", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._loop is not None and self._client is not None:
            try:
                import asyncio

                future = asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
                future.result(timeout=5)
            except Exception:
                logger.debug("Failed to close Discord client cleanly.", exc_info=True)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self._loop = None
        self._client = None
        self._connected = False

    def _run_client(self) -> None:
        import asyncio

        token = self._config_store.resolve_token("discord")
        if not token:
            self.set_error("Channel token is not configured.")
            self._running = False
            return
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        intents.members = True

        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready() -> None:
            self._user_id = str(client.user.id) if client.user else ""
            detail = f"Connected as {client.user}" if client.user else "Connected"
            self.set_connected(True, detail)

        @client.event
        async def on_message(message) -> None:
            if not self._running:
                return
            if client.user and message.author.id == client.user.id:
                return
            content = str(message.content or "").strip()
            if not content:
                if message.attachments:
                    content = "[Attachment]"
                else:
                    return
            guild_id = str(message.guild.id) if message.guild else ""
            peer_type = "dm" if message.guild is None else "channel"
            mentioned = (
                peer_type == "dm"
                or any(getattr(member, "id", None) == getattr(client.user, "id", None) for member in message.mentions)
                or f"<@{self._user_id}>" in content
                or f"<@!{self._user_id}>" in content
            )
            envelope = ChannelEnvelope(
                channel="discord",
                peer_type=peer_type,
                peer_id=str(message.channel.id),
                sender_id=str(message.author.id),
                sender_name=getattr(message.author, "display_name", None) or message.author.name,
                text=content,
                target_id=str(message.channel.id),
                message_id=str(message.id),
                mentioned=mentioned,
                metadata={
                    "guild_id": guild_id,
                    "channel_name": getattr(message.channel, "name", ""),
                },
            )
            self.mark_inbound()
            if self._manager is not None:
                self._manager.publish_inbound(envelope)

        try:
            loop.run_until_complete(client.start(token))
        except Exception as exc:
            self.set_error(str(exc))
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                logger.debug("Failed to shut down Discord async generators.", exc_info=True)
            loop.close()
            self._running = False
            self._connected = False

    def send_text(self, route: Dict[str, Any], text: str) -> bool:
        if not self._loop or not self._client:
            return False
        target_id = str(route.get("target_id") or route.get("peer_id") or "").strip()
        if not target_id:
            return False
        try:
            channel_id = int(target_id)
        except (TypeError, ValueError):
            self.set_error("Invalid Discord channel id.")
            return False

        async def _send() -> None:
            channel = self._client.get_channel(channel_id)
            if channel is None:
                channel = await self._client.fetch_channel(channel_id)
            for chunk in _chunk_text(text, limit=1900):
                await channel.send(chunk)

        try:
            import asyncio

            future = asyncio.run_coroutine_threadsafe(_send(), self._loop)
            future.result(timeout=30)
            self.mark_outbound()
            return True
        except Exception as exc:
            self.set_error(str(exc))
            return False


class ChannelManager:
    def __init__(
        self,
        *,
        config_store: GatewayConfigStore,
        pairing_store: PairingStore,
    ):
        self.config_store = config_store
        self.pairing_store = pairing_store
        self._inbound_handler: Optional[INBOUND_CALLBACK] = None
        self._adapters: Dict[str, ChannelAdapter] = {
            "telegram": TelegramAdapter(config_store),
            "discord": DiscordAdapter(config_store),
            "zalo": ZaloAdapter(config_store),
        }
        for adapter in self._adapters.values():
            adapter.attach_manager(self)

    def set_inbound_handler(self, callback: INBOUND_CALLBACK) -> None:
        self._inbound_handler = callback

    def start(self) -> None:
        for channel in CHANNEL_NAMES:
            cfg = self.config_store.get_channel_config(channel)
            if cfg.get("enabled"):
                self._adapters[channel].start()

    def stop(self) -> None:
        for adapter in self._adapters.values():
            adapter.stop()

    def restart_channel(self, channel: str) -> Dict[str, Any]:
        adapter = self._adapters[channel]
        adapter.stop()
        cfg = self.config_store.get_channel_config(channel)
        if cfg.get("enabled"):
            adapter.start()
        return self.get_channel_state(channel)

    def list_channel_states(self) -> list[Dict[str, Any]]:
        return [self.get_channel_state(channel) for channel in CHANNEL_NAMES]

    def get_channel_state(self, channel: str) -> Dict[str, Any]:
        cfg = self.config_store.public_channel_config(channel)
        cfg.update(self._adapters[channel].runtime_state())
        cfg["channel"] = channel
        return cfg

    def update_channel(self, channel: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        self.config_store.update_channel(channel, patch)
        return self.restart_channel(channel)

    def probe_channel(self, channel: str) -> Dict[str, Any]:
        state = self.get_channel_state(channel)
        state["probe"] = self._adapters[channel].probe()
        return state

    def pairing_snapshot(self) -> Dict[str, Any]:
        return self.pairing_store.snapshot()

    def approve_pairing(self, channel: str, code: str) -> Optional[PairingRequest]:
        return self.pairing_store.approve(channel, code)

    def reject_pairing(self, channel: str, code: str) -> bool:
        return self.pairing_store.reject(channel, code)

    def revoke_sender(self, channel: str, sender_id: str) -> bool:
        return self.pairing_store.revoke(channel, sender_id)

    def publish_inbound(self, envelope: ChannelEnvelope) -> bool:
        if envelope.channel not in self._adapters:
            return False
        allowed, pairing_request, created = self._authorize(envelope)
        if not allowed:
            if pairing_request and created:
                self._send_pairing_message(envelope, pairing_request)
            return False
        if self._inbound_handler is not None:
            self._inbound_handler(envelope)
            return True
        return False

    def session_key_for_envelope(self, envelope: ChannelEnvelope) -> str:
        if envelope.channel == "webchat" or envelope.peer_type == "dm":
            return "agent:main:main"
        if envelope.channel == "discord":
            return f"agent:main:discord:channel:{envelope.peer_id}"
        return f"agent:main:{envelope.channel}:group:{envelope.peer_id}"

    def send_reply(self, route: Dict[str, Any], text: str) -> bool:
        channel = str(route.get("channel", "")).strip()
        if channel not in self._adapters:
            return False
        return self._adapters[channel].send_text(route, text)

    def _send_pairing_message(self, envelope: ChannelEnvelope, request: PairingRequest) -> None:
        message = (
            f"Agent-02 pairing code: {request.code}\n"
            "Approve this code in WebUI > Pairing within 1 hour."
        )
        self.send_reply(envelope.route_dict(), message)

    def _authorize(
        self,
        envelope: ChannelEnvelope,
    ) -> tuple[bool, Optional[PairingRequest], bool]:
        cfg = self.config_store.get_channel_config(envelope.channel)
        if not cfg.get("enabled"):
            return False, None, False

        if envelope.peer_type == "dm":
            policy = str(cfg.get("dmPolicy", "pairing"))
            if policy == "disabled":
                return False, None, False
            if policy == "open":
                return True, None, False
            allow_from = set(cfg.get("allowFrom") or [])
            if "*" in allow_from or envelope.sender_id in allow_from:
                return True, None, False
            if self.pairing_store.is_allowed(envelope.channel, envelope.sender_id):
                return True, None, False
            if policy == "allowlist":
                return False, None, False
            request, created = self.pairing_store.issue_request(
                envelope.channel,
                envelope.sender_id,
                sender_name=envelope.sender_name,
                peer_id=envelope.peer_id,
                metadata=envelope.metadata,
            )
            return False, request, created

        peer_cfg, scope_matched = self._resolve_peer_config(cfg, envelope)
        base_policy = str(peer_cfg.get("groupPolicy") or cfg.get("groupPolicy") or "allowlist")
        if base_policy == "disabled":
            return False, None, False
        if base_policy == "allowlist" and not scope_matched:
            return False, None, False
        require_mention = bool(peer_cfg.get("requireMention", cfg.get("requireMention", True)))
        if require_mention and not envelope.mentioned:
            return False, None, False
        allow_from = set(peer_cfg.get("allowFrom") or cfg.get("groupAllowFrom") or [])
        if allow_from and "*" not in allow_from and envelope.sender_id not in allow_from:
            return False, None, False
        return True, None, False

    def _resolve_peer_config(
        self,
        cfg: Dict[str, Any],
        envelope: ChannelEnvelope,
    ) -> tuple[Dict[str, Any], bool]:
        if envelope.channel == "discord":
            scope_key = str(envelope.metadata.get("guild_id", "")).strip()
            scopes = cfg.get("guilds") if isinstance(cfg.get("guilds"), dict) else {}
        else:
            scope_key = envelope.peer_id
            scopes = cfg.get("groups") if isinstance(cfg.get("groups"), dict) else {}
        if scope_key and scope_key in scopes:
            return dict(scopes[scope_key]), True
        if "*" in scopes:
            return dict(scopes["*"]), True
        return {}, False
