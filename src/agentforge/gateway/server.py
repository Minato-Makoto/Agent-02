from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import requests

from ..agent_core import AgentConfig
from ..llm_inference import InferenceConfig, LLMInference
from ..session import SessionManager
from .channels import ChannelEnvelope, ChannelManager
from .config_store import CHANNEL_NAMES, GatewayConfigStore
from .connection_manager import ConnectionManager
from .inference_host import InferenceHost, InferenceHostConfig
from .model_proxy import ModelProxy
from .pairing import PairingStore
from .session_router import AgentRuntimeHandle, SessionEntry, SessionRouter
from .turn_executor import TurnExecutor

logger = logging.getLogger(__name__)


class GatewayServerHandle:
    def __init__(self, *, server: Any, thread: threading.Thread):
        self._server = server
        self._thread = thread

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            self._server.force_exit = True
            self._thread.join(timeout=5)


def create_app(
    *,
    workspace_dir: str,
    host_config: InferenceHostConfig,
    agent_config: AgentConfig,
    inference_config: InferenceConfig,
    llm_base_url: str = "http://127.0.0.1:8080",
) -> FastAPI:
    conn_mgr = ConnectionManager()
    turn_executor = TurnExecutor()
    model_proxy = ModelProxy(llm_base_url)
    inference_host = InferenceHost(host_config)
    session_router = SessionRouter(workspace_dir, agent_config)
    config_store = GatewayConfigStore(workspace_dir)
    pairing_store = PairingStore(workspace_dir)
    channel_manager = ChannelManager(config_store=config_store, pairing_store=pairing_store)

    def _llm_factory() -> LLMInference:
        return LLMInference()

    sessions_dir = os.path.join(workspace_dir, "sessions")

    def _list_model_ids() -> list[str]:
        return model_proxy.get_model_ids()

    def _session_snapshot(entry: SessionEntry) -> Dict[str, Any]:
        model_ids = _list_model_ids()
        return {
            "session_key": entry.session_key,
            "session_id": entry.session_id,
            "selected_model_id": entry.selected_model_id,
            "available_model_ids": model_ids,
            "model_required": (not entry.selected_model_id and len(model_ids) > 1),
            "channel": entry.channel,
            "peer_type": entry.peer_type,
            "peer_id": entry.peer_id,
            "account_id": entry.account_id,
            "title": entry.title,
        }

    def _entry_title(entry: SessionEntry) -> str:
        if entry.title:
            return entry.title
        if entry.session_key == "agent:main:main":
            return "Main"
        if entry.channel == "discord":
            return f"Discord #{entry.peer_id}"
        return f"{entry.channel}:{entry.peer_id}"

    def _load_session_data(entry: SessionEntry) -> Dict[str, Any]:
        handle = session_router._handles.get(entry.session_key)  # type: ignore[attr-defined]
        if handle is not None and handle.session_mgr.session and handle.session_mgr.session.id == entry.session_id:
            session = handle.session_mgr.session
        else:
            mgr = SessionManager(sessions_dir)
            session = mgr.load_session(entry.session_id)
        if session is None:
            return {"messages": [], "summary": "", "message_count": 0, "preview": ""}

        messages = [message.to_dict() for message in session.messages]
        preview = ""
        for message in reversed(session.messages):
            content = str(message.content or "").strip()
            if content:
                preview = content[:140]
                break
        return {
            "messages": messages,
            "summary": session.summary,
            "message_count": len(messages),
            "preview": preview,
        }

    def _serialize_session(entry: SessionEntry) -> Dict[str, Any]:
        session_data = _load_session_data(entry)
        payload = entry.to_dict()
        payload.update(
            {
                "title": _entry_title(entry),
                "preview": session_data["preview"],
                "message_count": session_data["message_count"],
            }
        )
        return payload

    def _session_defaults(session_key: str) -> Dict[str, Any]:
        existing = session_router.get_entry(session_key)
        if existing is not None:
            return {
                "channel": existing.channel,
                "peer_type": existing.peer_type,
                "peer_id": existing.peer_id,
                "account_id": existing.account_id,
                "title": _entry_title(existing),
            }
        if session_key == "agent:main:main":
            return {
                "channel": "webchat",
                "peer_type": "dm",
                "peer_id": "main",
                "account_id": "default",
                "title": "Main",
            }
        return {
            "channel": "webchat",
            "peer_type": "dm",
            "peer_id": session_key,
            "account_id": "default",
            "title": session_key,
        }

    async def _emit_to_session(session_key: str, event_type: str, payload: Dict[str, Any]) -> None:
        await conn_mgr.broadcast_to_session(
            session_key,
            {
                "type": event_type,
                "session_key": session_key,
                "payload": payload,
            },
        )

    def _ensure_entry(
        session_key: str,
        *,
        channel: str,
        peer_type: str,
        peer_id: str,
        account_id: str = "default",
        title: str = "",
    ) -> AgentRuntimeHandle:
        handle = session_router.get_or_create(
            session_key,
            llm_factory=_llm_factory,
            inference_config=inference_config,
            channel=channel,
            peer_type=peer_type,
            peer_id=peer_id,
            account_id=account_id,
            title=title,
        )
        session_router.update_route(
            session_key,
            channel=channel,
            peer_type=peer_type,
            peer_id=peer_id,
            account_id=account_id,
            title=title,
        )
        return handle

    async def _execute_turn(
        session_key: str,
        content: str,
        *,
        route: Optional[Dict[str, Any]] = None,
        title: str = "",
        channel: str = "webchat",
        peer_type: str = "dm",
        peer_id: str = "main",
        account_id: str = "default",
    ) -> str:
        handle = _ensure_entry(
            session_key,
            channel=channel,
            peer_type=peer_type,
            peer_id=peer_id,
            account_id=account_id,
            title=title,
        )
        if route:
            session_router.update_route(
                session_key,
                channel=channel,
                peer_type=peer_type,
                peer_id=peer_id,
                account_id=account_id,
                title=title,
                route=route,
            )
        _ensure_llm_connected(handle.llm, inference_config, llm_base_url)

        if not handle.entry.selected_model_id:
            model_ids = _list_model_ids()
            if not model_ids:
                message = "No models are available."
                if route:
                    channel_manager.send_reply(route, f"Agent-02 is unavailable: {message}")
                else:
                    await _emit_to_session(session_key, "error", {"message": message})
                return "[No models]"
            if len(model_ids) == 1:
                session_router.set_model(session_key, model_ids[0])
                handle.entry.selected_model_id = model_ids[0]
            else:
                message = "Please select a model in WebUI for this session."
                if route:
                    channel_manager.send_reply(route, f"Agent-02 is waiting for setup: {message}")
                else:
                    await _emit_to_session(session_key, "error", {"message": message, "model_required": True})
                return "[Model required]"

        if handle.entry.selected_model_id:
            handle.llm.set_model_id(handle.entry.selected_model_id)

        async def emit_fn(event_type: str, event_payload: Dict[str, Any]) -> None:
            await _emit_to_session(session_key, event_type, event_payload)

        result = await turn_executor.execute_turn(
            agent=handle.agent,
            user_input=content,
            emit_fn=emit_fn,
        )

        if route and result and not result.startswith("["):
            channel_manager.send_reply(route, result)
        return result

    def _channel_title(envelope: ChannelEnvelope) -> str:
        if envelope.peer_type == "dm":
            return "Main"
        label = envelope.metadata.get("channel_name") or envelope.peer_id
        if envelope.channel == "discord":
            return f"Discord #{label}"
        return f"{envelope.channel}:{label}"

    async def _handle_channel_inbound(envelope: ChannelEnvelope) -> None:
        session_key = channel_manager.session_key_for_envelope(envelope)
        entry_peer_id = "main" if envelope.peer_type == "dm" else envelope.peer_id
        await _execute_turn(
            session_key,
            envelope.text,
            route=envelope.route_dict(),
            title=_channel_title(envelope),
            channel=envelope.channel,
            peer_type=envelope.peer_type,
            peer_id=entry_peer_id,
            account_id=envelope.account_id,
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        loop = asyncio.get_running_loop()

        def _dispatch_inbound(envelope: ChannelEnvelope) -> None:
            asyncio.run_coroutine_threadsafe(_handle_channel_inbound(envelope), loop)

        channel_manager.set_inbound_handler(_dispatch_inbound)
        try:
            channel_manager.start()
            yield
        finally:
            channel_manager.stop()
            inference_host.stop()

    app = FastAPI(title="Agent-02 Gateway", version="2.1.0", lifespan=lifespan)
    app.state.workspace_dir = workspace_dir
    app.state.inference_host = inference_host
    app.state.conn_mgr = conn_mgr
    app.state.turn_executor = turn_executor
    app.state.model_proxy = model_proxy
    app.state.session_router = session_router
    app.state.channel_manager = channel_manager
    app.state.config_store = config_store

    web_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "web"))
    if os.path.isdir(web_dir):
        app.mount("/webchat/static", StaticFiles(directory=web_dir), name="webchat")

    @app.get("/health")
    async def health():
        backend_ok = inference_host.health_check() if inference_host.is_running else True
        return JSONResponse(
            {
                "status": "ok",
                "gateway": True,
                "backend": backend_ok,
                "connections": conn_mgr.connection_count,
                "workspace": workspace_dir,
                "channels": channel_manager.list_channel_states(),
            }
        )

    @app.get("/api/models")
    async def api_models():
        models = model_proxy.list_models()
        return JSONResponse({"models": [m.to_dict() for m in models]})

    @app.get("/api/sessions")
    async def api_sessions():
        sessions = [
            _serialize_session(entry)
            for entry in sorted(
                (SessionEntry.from_dict(item) for item in session_router.list_sessions()),
                key=lambda entry: entry.updated_at,
                reverse=True,
            )
        ]
        return JSONResponse({"sessions": sessions})

    @app.get("/api/sessions/{session_key}/transcript")
    async def api_session_transcript(session_key: str):
        entry = session_router.get_entry(session_key)
        if entry is None:
            return JSONResponse({"error": "Session not found."}, status_code=404)
        payload = _serialize_session(entry)
        payload.update(_load_session_data(entry))
        payload["snapshot"] = _session_snapshot(entry)
        return JSONResponse(payload)

    @app.get("/api/admin/channels")
    async def api_admin_channels():
        return JSONResponse({"channels": channel_manager.list_channel_states()})

    @app.put("/api/admin/channels/{channel}")
    async def api_admin_channel_update(channel: str, request: Request):
        if channel not in CHANNEL_NAMES:
            return JSONResponse({"error": "Unknown channel."}, status_code=404)
        payload = await request.json()
        if not isinstance(payload, dict):
            return JSONResponse({"error": "Invalid JSON payload."}, status_code=400)
        return JSONResponse(channel_manager.update_channel(channel, payload))

    @app.post("/api/admin/channels/{channel}/probe")
    async def api_admin_channel_probe(channel: str):
        if channel not in CHANNEL_NAMES:
            return JSONResponse({"error": "Unknown channel."}, status_code=404)
        return JSONResponse(channel_manager.probe_channel(channel))

    @app.get("/api/admin/pairing")
    async def api_admin_pairing():
        return JSONResponse(channel_manager.pairing_snapshot())

    @app.post("/api/admin/pairing/{channel}/{code}/approve")
    async def api_admin_pairing_approve(channel: str, code: str):
        approved = channel_manager.approve_pairing(channel, code)
        if approved is None:
            return JSONResponse({"error": "Pairing code not found."}, status_code=404)
        return JSONResponse({"ok": True, "approved": approved.__dict__})

    @app.post("/api/admin/pairing/{channel}/{code}/reject")
    async def api_admin_pairing_reject(channel: str, code: str):
        if not channel_manager.reject_pairing(channel, code):
            return JSONResponse({"error": "Pairing code not found."}, status_code=404)
        return JSONResponse({"ok": True})

    @app.delete("/api/admin/pairing/{channel}/{sender_id}")
    async def api_admin_pairing_revoke(channel: str, sender_id: str):
        if not channel_manager.revoke_sender(channel, sender_id):
            return JSONResponse({"error": "Sender not found."}, status_code=404)
        return JSONResponse({"ok": True})

    @app.get("/webchat")
    async def webchat_index():
        index_path = os.path.join(web_dir, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path, media_type="text/html")
        return HTMLResponse("<h1>WebChat not found</h1>", status_code=404)

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await conn_mgr.connect(ws)
        current_session_key = "agent:main:main"
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await conn_mgr.send_to(ws, {"type": "error", "payload": {"message": "Invalid JSON"}})
                    continue

                msg_type = str(msg.get("type", ""))
                payload = msg.get("payload", {}) if isinstance(msg.get("payload"), dict) else {}
                session_key = str(msg.get("session_key", current_session_key) or current_session_key)

                if msg_type == "ping":
                    await conn_mgr.send_to(ws, {"type": "pong"})
                    continue

                if msg_type == "hello":
                    await conn_mgr.send_to(
                        ws,
                        {"type": "status", "payload": {"text": "Connected to Agent-02 Gateway."}},
                    )
                    continue

                if msg_type == "session.list":
                    sessions = [
                        _serialize_session(SessionEntry.from_dict(item))
                        for item in session_router.list_sessions()
                    ]
                    await conn_mgr.send_to(ws, {"type": "session.list", "payload": {"sessions": sessions}})
                    continue

                if msg_type == "models.list":
                    models = model_proxy.list_models()
                    await conn_mgr.send_to(
                        ws,
                        {"type": "models.snapshot", "payload": {"models": [m.to_dict() for m in models]}},
                    )
                    continue

                if msg_type == "session.attach":
                    current_session_key = session_key
                    defaults = _session_defaults(session_key)
                    handle = _ensure_entry(session_key, **defaults)
                    conn_mgr.attach_to_session(ws, session_key)
                    await conn_mgr.send_to(
                        ws,
                        {"type": "session.snapshot", "session_key": session_key, "payload": _session_snapshot(handle.entry)},
                    )
                    continue

                if msg_type == "session.reset":
                    current_session_key = session_key
                    handle = session_router.reset_session(
                        session_key,
                        llm_factory=_llm_factory,
                        inference_config=inference_config,
                    )
                    defaults = _session_defaults(session_key)
                    session_router.update_route(session_key, route=handle.entry.last_route, **defaults)
                    _ensure_llm_connected(handle.llm, inference_config, llm_base_url)
                    conn_mgr.attach_to_session(ws, session_key)
                    await conn_mgr.send_to(
                        ws,
                        {"type": "session.snapshot", "session_key": session_key, "payload": _session_snapshot(handle.entry)},
                    )
                    continue

                if msg_type == "session.model.set":
                    model_id = str(payload.get("model_id", "")).strip()
                    if not model_id:
                        await conn_mgr.send_to(ws, {"type": "error", "payload": {"message": "Missing model_id"}})
                        continue
                    handle = _ensure_entry(session_key, **_session_defaults(session_key))
                    model_ids = _list_model_ids()
                    if model_id not in model_ids:
                        await conn_mgr.send_to(
                            ws,
                            {"type": "error", "payload": {"message": f"Unknown model: {model_id}"}},
                        )
                        continue
                    session_router.set_model(session_key, model_id)
                    handle.entry.selected_model_id = model_id
                    if handle.llm.is_connected:
                        handle.llm.set_model_id(model_id)
                    await conn_mgr.send_to(
                        ws,
                        {"type": "session.snapshot", "session_key": session_key, "payload": _session_snapshot(handle.entry)},
                    )
                    continue

                if msg_type == "chat.submit":
                    content = str(payload.get("content", "")).strip()
                    if not content:
                        await conn_mgr.send_to(ws, {"type": "error", "payload": {"message": "Empty message"}})
                        continue
                    defaults = _session_defaults(session_key)
                    await _execute_turn(session_key, content, **defaults)
                    continue

                await conn_mgr.send_to(
                    ws,
                    {"type": "error", "payload": {"message": f"Unknown message type: {msg_type}"}},
                )
        except WebSocketDisconnect:
            logger.debug("WebSocket disconnected.")
        except Exception:
            logger.exception("WebSocket error.")
        finally:
            conn_mgr.disconnect(ws)

    return app


def _ensure_llm_connected(llm: LLMInference, config: InferenceConfig, base_url: str) -> None:
    if llm.is_connected:
        return
    llm.connect_remote(
        base_url=f"{base_url}/v1",
        model_id="auto",
        api_key="",
        config=config,
    )


def run_gateway(app: FastAPI, *, host: str = "127.0.0.1", port: int = 18789) -> None:
    import uvicorn

    logger.info("Starting Agent-02 Gateway on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)


def start_gateway_in_thread(
    app: FastAPI,
    *,
    host: str = "127.0.0.1",
    port: int = 18789,
    startup_timeout: float = 15.0,
) -> GatewayServerHandle:
    import uvicorn

    config = uvicorn.Config(app, host=host, port=port, log_level="info", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    health_url = f"http://{probe_host}:{port}/health"
    deadline = time.time() + max(1.0, startup_timeout)
    last_error: Optional[BaseException] = None

    while time.time() < deadline:
        if not thread.is_alive():
            raise RuntimeError("Gateway server exited during startup.")
        try:
            resp = requests.get(health_url, timeout=1)
            if resp.status_code == 200:
                return GatewayServerHandle(server=server, thread=thread)
        except Exception as exc:
            last_error = exc
        time.sleep(0.1)

    server.should_exit = True
    thread.join(timeout=5)
    if last_error is not None:
        raise RuntimeError(f"Gateway did not become ready: {last_error}")
    raise RuntimeError("Gateway did not become ready before the startup timeout.")
