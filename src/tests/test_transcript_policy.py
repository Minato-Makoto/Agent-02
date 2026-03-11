from agentforge.transcript_policy import (
    apply_transcript_policy,
    detect_provider_kind,
    resolve_transcript_policy,
)


def test_detect_provider_kind_basic_matrix():
    assert detect_provider_kind("local", "http://127.0.0.1:8080", "local") == "llama_cpp"
    assert detect_provider_kind("remote", "https://api.openai.com/v1", "gpt-4o") == "openai"
    assert (
        detect_provider_kind("remote", "https://openrouter.ai/api/v1", "google/gemini-2.0")
        == "openrouter"
    )
    assert (
        detect_provider_kind(
            "remote",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            "gemini-2.0-flash",
        )
        == "gemini"
    )


def test_gemini_policy_repairs_single_pending_tool_result_id():
    policy = resolve_transcript_policy("gemini")
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "content": "ok"},
    ]
    out, meta = apply_transcript_policy(messages, policy)

    assert out[0]["role"] == "assistant"
    assert out[0]["tool_calls"][0]["id"] == "call1"
    assert out[1]["role"] == "tool"
    assert out[1]["tool_call_id"] == "call1"
    assert meta["reassigned_tool_results"] == 1


def test_openai_policy_drops_orphan_tool_result():
    policy = resolve_transcript_policy("openai")
    messages = [
        {"role": "tool", "content": "orphan", "tool_call_id": "abc"},
        {"role": "user", "content": "hello"},
    ]
    out, meta = apply_transcript_policy(messages, policy)

    assert len(out) == 1
    assert out[0]["role"] == "user"
    assert meta["dropped_messages"] == 1


def test_gemini_policy_inserts_synthetic_tool_result_before_non_tool_turn():
    policy = resolve_transcript_policy("gemini")
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-9",
                    "type": "function",
                    "function": {"name": "search_web", "arguments": "{}"},
                }
            ],
        },
        {"role": "user", "content": "continue"},
    ]
    out, meta = apply_transcript_policy(messages, policy)

    assert out[0]["role"] == "assistant"
    assert out[1]["role"] == "tool"
    assert out[1]["tool_call_id"] == "call9"
    assert out[2]["role"] == "user"
    assert meta["synthetic_tool_results"] == 1
