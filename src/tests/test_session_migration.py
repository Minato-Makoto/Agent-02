import json

from agentforge.session import SessionManager


def test_load_legacy_session_and_persist_migrated_schema(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session_path = sessions_dir / "legacy123.json"

    legacy_payload = {
        "id": "legacy123",
        "created_at": 1,
        "updated_at": 2,
        "summary": "",
        "messages": [
            {"role": "user", "content": "open file"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {"name": "read_file", "arguments": {"path": "C:/a.txt"}},
                    }
                ],
            },
        ],
    }
    session_path.write_text(json.dumps(legacy_payload, ensure_ascii=False), encoding="utf-8")

    manager = SessionManager(str(sessions_dir))
    loaded = manager.load_session("legacy123")
    assert loaded is not None
    assert loaded.schema_version == 3
    assert loaded.previous_session_id == ""
    assert loaded.id == "legacy123"
    assert any(m.role == "user" and m.content == "open file" for m in loaded.messages)
    assert any(
        m.role == "tool" and m.tool_call_id == "call-1" and m.synthetic is True
        for m in loaded.messages
    )

    # Ensure migrated payload was persisted back to disk.
    persisted = json.loads(session_path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 3
    assert persisted["previous_session_id"] == ""
    assert any(
        msg.get("role") == "tool" and msg.get("tool_call_id") == "call-1" and msg.get("synthetic")
        for msg in persisted["messages"]
    )


def test_session_migration_v2_to_v3_adds_previous_session_id(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    session_path = sessions_dir / "v2session.json"
    payload_v2 = {
        "id": "v2session",
        "created_at": 10,
        "updated_at": 20,
        "schema_version": 2,
        "summary": "old summary",
        "metadata": {"owner": "test"},
        "messages": [{"role": "user", "content": "hello"}],
    }
    session_path.write_text(json.dumps(payload_v2, ensure_ascii=False), encoding="utf-8")

    manager = SessionManager(str(sessions_dir))
    loaded = manager.load_session("v2session")

    assert loaded is not None
    assert loaded.schema_version == 3
    assert loaded.previous_session_id == ""
    assert loaded.summary == "old summary"

    persisted = json.loads(session_path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 3
    assert persisted["previous_session_id"] == ""


def test_replace_transcript_keeps_session_identity_and_updates_summary(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    manager = SessionManager(str(sessions_dir))
    session = manager.new_session()
    old_id = session.id
    manager.add_message("user", "before replace")

    manager.replace_transcript(
        messages=[
            {"role": "system", "content": "Context memory note"},
            {"role": "user", "content": "latest user"},
            {"role": "assistant", "content": "latest assistant"},
        ],
        summary="updated summary",
        metadata_update={"last_compaction": "graceful"},
    )

    assert manager.session is not None
    assert manager.session.id == old_id
    assert manager.session.summary == "updated summary"
    assert manager.session.metadata.get("last_compaction") == "graceful"
    assert [m.role for m in manager.session.messages] == ["system", "user", "assistant"]
