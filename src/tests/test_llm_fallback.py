from agentforge.llm_inference import InferenceConfig, LLMInference


def _connect_remote(url: str, config: InferenceConfig | None = None) -> LLMInference:
    llm = LLMInference()
    ok = llm.connect_remote(
        base_url=url,
        model_id="mock-model",
        config=config or InferenceConfig(max_tokens=128),
    )
    assert ok
    return llm


def test_chat_completion_auto_fallback_when_tools_are_rejected(mock_chat_server):
    llm = _connect_remote(mock_chat_server.url)
    llm.capabilities.supports_tools = True

    mock_chat_server.enqueue_error("Unsupported param: tools", status=400)
    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "fallback ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    result = llm.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "noop",
                    "description": "noop",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )

    assert result.error == ""
    assert result.content == "fallback ok"
    assert result.used_tools_fallback is True
    assert llm.capabilities.supports_tools is False
    assert len(mock_chat_server.requests) == 2
    assert "tools" in mock_chat_server.requests[0]["payload"]
    assert "tools" not in mock_chat_server.requests[1]["payload"]


def test_chat_completion_skips_preflight_probe_and_falls_back_inline_for_unsupported_tools(
    mock_chat_server,
):
    llm = _connect_remote(mock_chat_server.url)
    assert llm.capabilities.supports_tools is None

    mock_chat_server.enqueue_error("Unsupported param: tools", status=400)
    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "no-tools mode"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    result = llm.chat_completion(
        messages=[{"role": "user", "content": "hello"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "noop",
                    "description": "noop",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )

    assert result.error == ""
    assert result.content == "no-tools mode"
    assert llm.capabilities.supports_tools is False
    assert len(mock_chat_server.requests) == 2
    assert "tools" in mock_chat_server.requests[0]["payload"]
    assert mock_chat_server.requests[0]["payload"]["max_tokens"] == 128
    assert "tools" not in mock_chat_server.requests[1]["payload"]


def test_chat_completion_fallback_when_reasoning_effort_is_rejected(mock_chat_server):
    llm = _connect_remote(
        mock_chat_server.url,
        config=InferenceConfig(max_tokens=128, reasoning_effort="medium"),
    )

    mock_chat_server.enqueue_error("Unsupported param: reasoning_effort", status=400)
    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "reasoning fallback ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    result = llm.chat_completion(messages=[{"role": "user", "content": "hello"}])
    assert result.error == ""
    assert result.content == "reasoning fallback ok"
    assert llm.capabilities.supports_reasoning_effort is False
    assert len(mock_chat_server.requests) == 2
    assert "reasoning_effort" in mock_chat_server.requests[0]["payload"]
    assert "reasoning_effort" not in mock_chat_server.requests[1]["payload"]


def test_chat_completion_openai_provider_sends_reasoning_effort_only(mock_chat_server):
    llm = _connect_remote(
        mock_chat_server.url,
        config=InferenceConfig(max_tokens=128, reasoning_effort="medium"),
    )
    llm._provider_kind = "openai"

    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    result = llm.chat_completion(messages=[{"role": "user", "content": "hello"}])
    assert result.error == ""
    assert result.content == "ok"
    assert mock_chat_server.requests[0]["payload"]["reasoning_effort"] == "medium"


def test_chat_completion_openai_provider_prefers_reasoning_effort(mock_chat_server):
    llm = _connect_remote(
        mock_chat_server.url,
        config=InferenceConfig(max_tokens=128, reasoning_effort="medium"),
    )
    llm._provider_kind = "openai"

    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    result = llm.chat_completion(messages=[{"role": "user", "content": "hello"}])
    assert result.error == ""
    assert result.content == "ok"
    assert mock_chat_server.requests[0]["payload"]["reasoning_effort"] == "medium"
    assert llm.capabilities.supports_reasoning_effort is True


def test_chat_completion_llama_cpp_passes_reasoning_controls_without_mapping(mock_chat_server):
    llm = _connect_remote(
        mock_chat_server.url,
        config=InferenceConfig(max_tokens=128, reasoning_effort="low"),
    )
    llm._provider_kind = "llama_cpp"

    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    result = llm.chat_completion(messages=[{"role": "user", "content": "hello"}])
    assert result.error == ""
    assert result.content == "ok"
    assert mock_chat_server.requests[0]["payload"]["reasoning_effort"] == "low"


def test_chat_completion_normalizes_reasoning_effort_extra_high(mock_chat_server):
    llm = _connect_remote(
        mock_chat_server.url,
        config=InferenceConfig(max_tokens=128, reasoning_effort="extra high"),
    )
    llm._provider_kind = "llama_cpp"

    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    result = llm.chat_completion(messages=[{"role": "user", "content": "hello"}])
    assert result.error == ""
    assert result.content == "ok"
    assert mock_chat_server.requests[0]["payload"]["reasoning_effort"] == "extra_high"


def test_chat_completion_openai_o_series_uses_max_completion_tokens(mock_chat_server):
    llm = _connect_remote(mock_chat_server.url, config=InferenceConfig(max_tokens=256))
    llm._provider_kind = "openai"
    llm._config.model_id = "o3-mini"

    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    result = llm.chat_completion(messages=[{"role": "user", "content": "hello"}])
    assert result.error == ""
    payload = mock_chat_server.requests[0]["payload"]
    assert payload["max_completion_tokens"] == 256
    assert "max_tokens" not in payload


def test_chat_completion_fallback_when_max_completion_tokens_is_rejected(mock_chat_server):
    llm = _connect_remote(mock_chat_server.url, config=InferenceConfig(max_tokens=64))
    llm._provider_kind = "openai"
    llm._config.model_id = "o3-mini"

    mock_chat_server.enqueue_error("Unsupported param: max_completion_tokens", status=400)
    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "token fallback ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    result = llm.chat_completion(messages=[{"role": "user", "content": "hello"}])
    assert result.error == ""
    assert result.content == "token fallback ok"
    assert len(mock_chat_server.requests) == 2
    assert "max_completion_tokens" in mock_chat_server.requests[0]["payload"]
    assert "max_tokens" not in mock_chat_server.requests[0]["payload"]
    assert mock_chat_server.requests[1]["payload"]["max_tokens"] == 64
    assert "max_completion_tokens" not in mock_chat_server.requests[1]["payload"]


def test_chat_completion_fallback_when_response_format_is_rejected(mock_chat_server):
    llm = _connect_remote(mock_chat_server.url)

    mock_chat_server.enqueue_error("Unsupported param: response_format", status=400)
    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "response format fallback ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    result = llm.chat_completion(
        messages=[{"role": "user", "content": "hello"}],
        response_format={"type": "json_object"},
    )
    assert result.error == ""
    assert result.content == "response format fallback ok"
    assert llm.capabilities.supports_response_format is False
    assert len(mock_chat_server.requests) == 2
    assert "response_format" in mock_chat_server.requests[0]["payload"]
    assert "response_format" not in mock_chat_server.requests[1]["payload"]


def test_chat_completion_fallback_when_parallel_tool_calls_is_rejected(mock_chat_server):
    llm = _connect_remote(mock_chat_server.url)
    llm.capabilities.supports_tools = True

    mock_chat_server.enqueue_error("Unsupported param: parallel_tool_calls", status=400)
    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "parallel fallback ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    result = llm.chat_completion(
        messages=[{"role": "user", "content": "hello"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "noop",
                    "description": "noop",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        parallel_tool_calls=True,
    )
    assert result.error == ""
    assert result.content == "parallel fallback ok"
    assert llm.capabilities.supports_parallel_tool_calls is False
    assert llm.capabilities.supports_tools is True
    assert len(mock_chat_server.requests) == 2
    assert mock_chat_server.requests[0]["payload"]["parallel_tool_calls"] is True
    assert "tools" in mock_chat_server.requests[0]["payload"]
    assert "parallel_tool_calls" not in mock_chat_server.requests[1]["payload"]
    assert "tools" in mock_chat_server.requests[1]["payload"]


def test_streaming_fallback_when_stream_is_rejected(mock_chat_server):
    llm = _connect_remote(mock_chat_server.url)

    mock_chat_server.enqueue_error("Unsupported param: stream", status=400)
    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "stream fallback ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    tokens = []
    result = llm.chat_completion(
        messages=[{"role": "user", "content": "hello"}],
        stream=True,
        on_token=tokens.append,
    )
    assert result.error == ""
    assert result.content == "stream fallback ok"
    assert llm.capabilities.supports_stream is False
    assert "".join(tokens) == "stream fallback ok"
    assert len(mock_chat_server.requests) == 2
    assert mock_chat_server.requests[0]["payload"]["stream"] is True
    assert "stream" not in mock_chat_server.requests[1]["payload"]


def test_llama_cpp_low_effort_surfaces_backend_reasoning_stream(mock_chat_server):
    llm = _connect_remote(
        mock_chat_server.url,
        config=InferenceConfig(max_tokens=64, reasoning_effort="low"),
    )
    llm._provider_kind = "llama_cpp"

    mock_chat_server.enqueue_stream(
        [
            {
                "choices": [
                    {"delta": {"reasoning_content": "very long hidden thinking"}, "finish_reason": None}
                ]
            },
            {"choices": [{"delta": {"content": "Visible"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": " answer"}, "finish_reason": "stop"}]},
        ]
    )

    tokens: list[str] = []
    reasoning: list[str] = []
    result = llm.chat_completion(
        messages=[{"role": "user", "content": "hello"}],
        stream=True,
        on_token=tokens.append,
        on_reasoning=reasoning.append,
    )

    assert result.error == ""
    assert result.content == "Visible answer"
    assert tokens == ["Visible", " answer"]
    assert reasoning == ["very long hidden thinking"]
    assert mock_chat_server.requests[0]["payload"]["reasoning_effort"] == "low"


def test_chat_completion_applies_transcript_policy_before_send(mock_chat_server):
    llm = _connect_remote(mock_chat_server.url)
    llm._provider_kind = "openai"

    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )
    result = llm.chat_completion(
        messages=[
            {"role": "tool", "content": "orphan", "tool_call_id": "bad-1"},
            {"role": "user", "content": "hello"},
        ]
    )

    assert result.error == ""
    payload_messages = mock_chat_server.requests[0]["payload"]["messages"]
    assert len(payload_messages) == 1
    assert payload_messages[0]["role"] == "user"


def test_chat_completion_normalizes_tools_for_provider(mock_chat_server):
    llm = _connect_remote(mock_chat_server.url)
    llm.capabilities.supports_tools = True
    llm._provider_kind = "gemini"

    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    result = llm.chat_completion(
        messages=[{"role": "user", "content": "hello"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "select_mode",
                    "description": "Pick mode",
                    "parameters": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "mode": {
                                "anyOf": [
                                    {"const": "safe", "type": "string"},
                                    {"const": "fast", "type": "string"},
                                ],
                                "pattern": "^[a-z]+$",
                            }
                        },
                    },
                },
            }
        ],
    )

    assert result.error == ""
    sent_schema = mock_chat_server.requests[0]["payload"]["tools"][0]["function"]["parameters"]
    assert "additionalProperties" not in sent_schema
    assert "anyOf" not in sent_schema["properties"]["mode"]
