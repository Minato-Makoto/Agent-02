from agentforge.agent_core import Agent, AgentConfig, StreamCallbacks
from agentforge.contracts import ChatCompletionResult, ToolCall
from agentforge.llm_inference import InferenceConfig, LLMInference
from agentforge.tools import Tool, ToolRegistry


def test_streaming_tokens_and_reasoning_are_preserved(mock_chat_server):
    llm = LLMInference()
    assert llm.connect_remote(
        base_url=mock_chat_server.url,
        model_id="mock",
        config=InferenceConfig(max_tokens=64),
    )

    mock_chat_server.enqueue_stream(
        [
            {
                "choices": [
                    {"delta": {"reasoning_content": "thinking..."}, "finish_reason": None}
                ]
            },
            {"choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": " world"}, "finish_reason": "stop"}]},
        ]
    )

    tokens = []
    reasoning = []
    result = llm.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
        on_token=tokens.append,
        on_reasoning=reasoning.append,
    )

    assert result.error == ""
    assert result.content == "Hello world"
    assert "".join(tokens) == "Hello world"
    assert "".join(reasoning) == "thinking..."


def test_streaming_tool_call_arguments_callbacks_are_emitted(mock_chat_server):
    llm = LLMInference()
    assert llm.connect_remote(
        base_url=mock_chat_server.url,
        model_id="mock",
        config=InferenceConfig(max_tokens=64),
    )

    mock_chat_server.enqueue_stream(
        [
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "function": {"name": "read_file", "arguments": "{\"path\":\""},
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {"arguments": "workspace/AGENT.md\"}"},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        ]
    )

    starts = []
    deltas = []
    ends = []
    result = llm.chat_completion(
        messages=[{"role": "user", "content": "read file"}],
        stream=True,
        on_tool_call_start=lambda name, index: starts.append((name, index)),
        on_tool_call_delta=lambda index, token: deltas.append((index, token)),
        on_tool_call_end=ends.append,
    )

    assert result.error == ""
    assert result.has_tool_calls
    assert result.tool_calls_streamed is True
    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].arguments["path"] == "workspace/AGENT.md"
    assert starts == [("read_file", 0)]
    assert "".join(token for _, token in deltas) == "{\"path\":\"workspace/AGENT.md\"}"
    assert ends == [0]


class _FakeLLM:
    def __init__(self):
        self.capabilities = type("Caps", (), {"supports_tools": True})()
        self._round = 0

    def chat_completion(self, messages, **kwargs):
        self._round += 1
        if self._round == 1:
            return ChatCompletionResult(
                content="",
                tool_calls=[ToolCall(id="call-1", name="noop_tool", arguments={"x": 1})],
                finish_reason="tool_calls",
            )
        on_token = kwargs.get("on_token")
        on_reasoning = kwargs.get("on_reasoning")
        if on_reasoning:
            on_reasoning("r")
        if on_token:
            on_token("done")
        return ChatCompletionResult(content="done", finish_reason="stop")


class _FakeLLMToolCallStream:
    def __init__(self):
        self.capabilities = type("Caps", (), {"supports_tools": True})()
        self._round = 0

    def chat_completion(self, messages, **kwargs):
        self._round += 1
        if self._round == 1:
            on_tool_call_start = kwargs.get("on_tool_call_start")
            on_tool_call_delta = kwargs.get("on_tool_call_delta")
            on_tool_call_end = kwargs.get("on_tool_call_end")
            if on_tool_call_start:
                on_tool_call_start("noop_tool", 0)
            if on_tool_call_delta:
                on_tool_call_delta(0, '{"x":')
                on_tool_call_delta(0, " 1}")
            if on_tool_call_end:
                on_tool_call_end(0)
            return ChatCompletionResult(
                content="",
                tool_calls=[ToolCall(id="call-1", name="noop_tool", arguments={"x": 1})],
                finish_reason="tool_calls",
                tool_calls_streamed=True,
            )
        on_token = kwargs.get("on_token")
        if on_token:
            on_token("done")
        return ChatCompletionResult(content="done", finish_reason="stop")


def test_agent_ui_callbacks_regression(minimal_workspace):
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="noop_tool",
            description="returns ok",
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            execute_fn=lambda args: {"ok": args["x"]},
        )
    )
    agent = Agent(
        config=AgentConfig(
            max_iterations=4,
            max_repeats=3,
            timeout=30.0,
            workspace_dir=str(minimal_workspace),
        ),
        llm=_FakeLLM(),
        tools=registry,
    )

    events = {
        "start": 0,
        "end": 0,
        "tool_calls": [],
        "tool_results": [],
        "tokens": [],
        "reasoning": [],
    }
    callbacks = StreamCallbacks(
        on_stream_start=lambda: events.__setitem__("start", events["start"] + 1),
        on_stream_end=lambda: events.__setitem__("end", events["end"] + 1),
        on_tool_call=lambda name, args: events["tool_calls"].append((name, args)),
        on_tool_result=lambda name, out: events["tool_results"].append((name, out)),
        on_token=events["tokens"].append,
        on_reasoning=events["reasoning"].append,
    )

    answer = agent.run("go", callbacks=callbacks)
    assert answer == "done"
    # on_stream_start is now a UI concern (triggered lazily by stream_token),
    # so the agent loop does not call it directly.
    assert events["end"] == 2
    assert len(events["tool_calls"]) == 1
    assert events["tool_calls"][0][0] == "noop_tool"
    assert len(events["tool_results"]) == 1
    assert "".join(events["tokens"]) == "done"
    assert "".join(events["reasoning"]) == "r"


def test_agent_skips_duplicate_tool_call_callback_when_streamed(minimal_workspace):
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="noop_tool",
            description="returns ok",
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            execute_fn=lambda args: {"ok": args["x"]},
        )
    )
    agent = Agent(
        config=AgentConfig(
            max_iterations=4,
            max_repeats=3,
            timeout=30.0,
            workspace_dir=str(minimal_workspace),
        ),
        llm=_FakeLLMToolCallStream(),
        tools=registry,
    )

    events = {
        "tool_calls": [],
        "tool_call_stream_start": [],
        "tool_call_stream_delta": [],
        "tool_call_stream_end": [],
    }
    callbacks = StreamCallbacks(
        on_tool_call=lambda name, args: events["tool_calls"].append((name, args)),
        on_tool_call_start=lambda name, index: events["tool_call_stream_start"].append(
            (name, index)
        ),
        on_tool_call_delta=lambda index, token: events["tool_call_stream_delta"].append(
            (index, token)
        ),
        on_tool_call_end=events["tool_call_stream_end"].append,
    )

    answer = agent.run("go", callbacks=callbacks)
    assert answer == "done"
    assert events["tool_calls"] == []
    assert events["tool_call_stream_start"] == [("noop_tool", 0)]
    assert "".join(token for _, token in events["tool_call_stream_delta"]) == '{"x": 1}'
    assert events["tool_call_stream_end"] == [0]
