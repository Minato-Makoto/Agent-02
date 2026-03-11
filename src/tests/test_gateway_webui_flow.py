import time

from fastapi.testclient import TestClient

from agentforge.agent_core import AgentConfig
from agentforge.gateway.channels import ChannelEnvelope
from agentforge.gateway.inference_host import InferenceHostConfig
from agentforge.gateway.model_proxy import ModelInfo
from agentforge.gateway.server import create_app
from agentforge.llm_inference import InferenceConfig, LLMInference


def _build_gateway_app(monkeypatch, workspace_dir):
    app = create_app(
        workspace_dir=str(workspace_dir),
        host_config=InferenceHostConfig(
            server_exe="llama-server.exe",
            models_dir=str(workspace_dir),
        ),
        agent_config=AgentConfig(
            max_iterations=8,
            max_repeats=3,
            timeout=30.0,
            workspace_dir=str(workspace_dir),
        ),
        inference_config=InferenceConfig(),
        llm_base_url="http://127.0.0.1:8080",
    )

    def fake_connect_remote(self, base_url, model_id, api_key="", config=None):
        if config is not None:
            self._config = config
        self._loaded = True
        self._mode = "remote"
        self._base_url = base_url.rstrip("/")
        self._config.model_id = model_id or "router-model"
        self._capabilities.supports_tools = True
        return True

    async def fake_execute_turn(*, agent, user_input, emit_fn):
        reply = f"Agent-02 reply: {user_input}"
        await emit_fn("assistant.done", {"content": reply})
        return reply

    monkeypatch.setattr(LLMInference, "connect_remote", fake_connect_remote)
    monkeypatch.setattr(app.state.model_proxy, "list_models", lambda: [ModelInfo(id="router-model")])
    monkeypatch.setattr(app.state.model_proxy, "get_model_ids", lambda: ["router-model"])
    monkeypatch.setattr(app.state.turn_executor, "execute_turn", fake_execute_turn)
    monkeypatch.setattr(app.state.inference_host, "health_check", lambda: True)
    monkeypatch.setattr(app.state.channel_manager, "start", lambda: None)
    monkeypatch.setattr(app.state.channel_manager, "stop", lambda: None)
    monkeypatch.setattr(
        app.state.channel_manager,
        "restart_channel",
        lambda channel: app.state.channel_manager.get_channel_state(channel),
    )
    return app


def _wait_for(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("Condition was not met before timeout.")


def test_webui_shell_loads_and_main_session_resets(monkeypatch, minimal_workspace):
    app = _build_gateway_app(monkeypatch, minimal_workspace)

    with TestClient(app) as client:
        web = client.get("/webchat")
        assert web.status_code == 200
        assert "Pairing" in web.text
        assert "Channels" in web.text

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["gateway"] is True

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "hello", "payload": {"client_type": "webui"}})
            hello = ws.receive_json()
            assert hello["type"] == "status"
            assert hello["payload"]["text"] == "Connected to Agent-02 Gateway."

            ws.send_json({"type": "session.attach", "session_key": "agent:main:main"})
            attached = ws.receive_json()
            assert attached["type"] == "session.snapshot"
            assert attached["payload"]["session_key"] == "agent:main:main"
            assert attached["payload"]["channel"] == "webchat"
            first_session_id = attached["payload"]["session_id"]

            ws.send_json({"type": "session.reset", "session_key": "agent:main:main"})
            reset = ws.receive_json()
            assert reset["type"] == "session.snapshot"
            assert reset["payload"]["session_key"] == "agent:main:main"
            assert reset["payload"]["channel"] == "webchat"
            assert reset["payload"]["session_id"] != first_session_id

        sessions = client.get("/api/sessions").json()["sessions"]
        assert any(item["session_key"] == "agent:main:main" for item in sessions)


def test_websocket_stream_events_surface_reasoning_and_tokens(monkeypatch, minimal_workspace):
    app = _build_gateway_app(monkeypatch, minimal_workspace)

    async def fake_execute_turn(*, agent, user_input, emit_fn):
        await emit_fn("status", {"text": "Thinking..."})
        await emit_fn("assistant.reasoning", {"token": "step 1"})
        await emit_fn("assistant.delta", {"token": "Hello"})
        await emit_fn("assistant.delta", {"token": " world"})
        await emit_fn("assistant.done", {"content": "Hello world"})
        return "Hello world"

    monkeypatch.setattr(app.state.turn_executor, "execute_turn", fake_execute_turn)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "session.attach", "session_key": "agent:main:main"})
            attached = ws.receive_json()
            assert attached["type"] == "session.snapshot"

            ws.send_json(
                {
                    "type": "chat.submit",
                    "session_key": "agent:main:main",
                    "payload": {"content": "hi"},
                }
            )

            event_types = []
            event_payloads = []
            for _ in range(4):
                event = ws.receive_json()
                event_types.append(event["type"])
                event_payloads.append(event["payload"])

            assert event_types == [
                "status",
                "assistant.reasoning",
                "assistant.delta",
                "assistant.delta",
            ]
            assert event_payloads[0]["text"] == "Thinking..."
            assert event_payloads[1]["token"] == "step 1"
            assert "".join(item["token"] for item in event_payloads[2:]) == "Hello world"

            done = ws.receive_json()
            assert done["type"] == "assistant.done"
            assert done["payload"]["content"] == "Hello world"


def test_admin_channel_endpoints_mask_tokens_and_probe(monkeypatch, minimal_workspace):
    app = _build_gateway_app(monkeypatch, minimal_workspace)
    monkeypatch.setattr(
        app.state.channel_manager._adapters["telegram"],
        "probe",
        lambda: {"ok": True, "bot": {"username": "agent02bot"}},
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/admin/channels/telegram",
            json={
                "enabled": True,
                "botToken": "secret-token",
                "dmPolicy": "pairing",
                "allowFrom": ["dm-user"],
                "groupAllowFrom": ["group-user"],
                "groups": {
                    "group-1": {
                        "groupPolicy": "open",
                        "requireMention": False,
                    }
                },
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["channel"] == "telegram"
        assert payload["configured"] is True
        assert "botToken" not in payload
        assert payload["allowFrom"] == ["dm-user"]
        assert payload["groups"]["group-1"]["groupPolicy"] == "open"

        probe = client.post("/api/admin/channels/telegram/probe")
        assert probe.status_code == 200
        assert probe.json()["probe"]["ok"] is True

        channels = client.get("/api/admin/channels").json()["channels"]
        telegram = next(item for item in channels if item["channel"] == "telegram")
        assert telegram["configured"] is True
        assert "botToken" not in telegram

        stored = app.state.config_store.get_channel_config("telegram")
        assert stored["botToken"] == "secret-token"


def test_pairing_endpoints_approve_and_revoke_dm_access(monkeypatch, minimal_workspace):
    app = _build_gateway_app(monkeypatch, minimal_workspace)
    manager = app.state.channel_manager
    manager.config_store.update_channel("telegram", {"enabled": True, "botToken": "secret-token"})

    sent_messages = []
    monkeypatch.setattr(
        manager._adapters["telegram"],
        "send_text",
        lambda route, text: sent_messages.append({"route": route, "text": text}) or True,
    )

    envelope = ChannelEnvelope(
        channel="telegram",
        peer_type="dm",
        peer_id="chat-42",
        sender_id="user-42",
        sender_name="Alice",
        text="hello",
        target_id="chat-42",
    )

    assert manager.publish_inbound(envelope) is False
    assert len(sent_messages) == 1
    assert "pairing code" in sent_messages[0]["text"].lower()

    with TestClient(app) as client:
        pairing = client.get("/api/admin/pairing")
        assert pairing.status_code == 200
        pending = pairing.json()["channels"]["telegram"]["pending"]
        assert len(pending) == 1
        code = pending[0]["code"]

        approve = client.post(f"/api/admin/pairing/telegram/{code}/approve")
        assert approve.status_code == 200
        assert approve.json()["ok"] is True

        snapshot = client.get("/api/admin/pairing").json()["channels"]["telegram"]
        assert snapshot["pending"] == []
        assert "user-42" in snapshot["approved"]

        revoke = client.delete("/api/admin/pairing/telegram/user-42")
        assert revoke.status_code == 200
        assert revoke.json()["ok"] is True

    captured = []
    manager.set_inbound_handler(lambda incoming: captured.append(incoming))
    manager.pairing_store._save_allow_from("telegram", ["user-42"])
    assert manager.publish_inbound(envelope) is True
    assert captured and captured[0].sender_id == "user-42"


def test_channel_routing_uses_main_dm_session_and_distinct_group_sessions(monkeypatch, minimal_workspace):
    app = _build_gateway_app(monkeypatch, minimal_workspace)
    manager = app.state.channel_manager
    replies = []

    manager.config_store.update_channel(
        "telegram",
        {
            "enabled": True,
            "botToken": "secret-token",
            "dmPolicy": "open",
            "groups": {"tg-group": {"groupPolicy": "open", "requireMention": False}},
        },
    )
    manager.config_store.update_channel(
        "discord",
        {
            "enabled": True,
            "token": "secret-token",
            "dmPolicy": "open",
            "guilds": {"guild-1": {"groupPolicy": "open", "requireMention": False}},
        },
    )

    monkeypatch.setattr(
        manager._adapters["telegram"],
        "send_text",
        lambda route, text: replies.append(("telegram", route, text)) or True,
    )
    monkeypatch.setattr(
        manager._adapters["discord"],
        "send_text",
        lambda route, text: replies.append(("discord", route, text)) or True,
    )

    with TestClient(app) as client:
        dm_envelope = ChannelEnvelope(
            channel="telegram",
            peer_type="dm",
            peer_id="chat-1",
            sender_id="user-1",
            sender_name="Alice",
            text="hello from dm",
            target_id="chat-1",
        )
        assert manager.publish_inbound(dm_envelope) is True
        _wait_for(
            lambda: (
                app.state.session_router.get_entry("agent:main:main") is not None
                and app.state.session_router.get_entry("agent:main:main").last_route.get("peer_id") == "chat-1"
            )
        )

        main_entry = app.state.session_router.get_entry("agent:main:main")
        assert main_entry is not None
        assert main_entry.channel == "telegram"
        assert main_entry.peer_type == "dm"
        assert main_entry.peer_id == "main"
        assert main_entry.last_route["peer_id"] == "chat-1"
        before_session_id = main_entry.session_id
        before_route = dict(main_entry.last_route)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "session.attach", "session_key": "agent:main:main"})
            attached = ws.receive_json()
            assert attached["payload"]["channel"] == "telegram"

            ws.send_json({"type": "session.reset", "session_key": "agent:main:main"})
            reset = ws.receive_json()
            assert reset["payload"]["session_key"] == "agent:main:main"
            assert reset["payload"]["channel"] == "telegram"
            assert reset["payload"]["session_id"] != before_session_id

        main_after = app.state.session_router.get_entry("agent:main:main")
        assert main_after is not None
        assert main_after.last_route == before_route

        group_envelope = ChannelEnvelope(
            channel="telegram",
            peer_type="group",
            peer_id="tg-group",
            sender_id="user-2",
            sender_name="Bob",
            text="@agent hi",
            target_id="tg-group",
            mentioned=True,
        )
        assert manager.publish_inbound(group_envelope) is True
        _wait_for(
            lambda: app.state.session_router.get_entry("agent:main:telegram:group:tg-group") is not None
        )
        tg_group_entry = app.state.session_router.get_entry("agent:main:telegram:group:tg-group")
        assert tg_group_entry is not None
        assert tg_group_entry.channel == "telegram"
        assert tg_group_entry.peer_type == "group"
        assert tg_group_entry.peer_id == "tg-group"

        discord_envelope = ChannelEnvelope(
            channel="discord",
            peer_type="channel",
            peer_id="channel-7",
            sender_id="user-3",
            sender_name="Cara",
            text="<@agent> hi",
            target_id="channel-7",
            mentioned=True,
            metadata={"guild_id": "guild-1", "channel_name": "general"},
        )
        assert manager.publish_inbound(discord_envelope) is True
        _wait_for(
            lambda: app.state.session_router.get_entry("agent:main:discord:channel:channel-7") is not None
        )
        discord_entry = app.state.session_router.get_entry("agent:main:discord:channel:channel-7")
        assert discord_entry is not None
        assert discord_entry.channel == "discord"
        assert discord_entry.peer_type == "channel"
        assert discord_entry.peer_id == "channel-7"

        _wait_for(lambda: len(replies) >= 3)
        assert any(item[0] == "telegram" for item in replies)
        assert any(item[0] == "discord" for item in replies)
