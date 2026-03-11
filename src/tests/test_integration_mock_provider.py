import json

from agentforge.agent_core import Agent, AgentConfig
from agentforge.llm_inference import InferenceConfig, LLMInference
from agentforge.tools import Tool, ToolRegistry


def _connect_remote(url: str) -> LLMInference:
    llm = LLMInference()
    ok = llm.connect_remote(
        base_url=url,
        model_id="mock-model",
        config=InferenceConfig(max_tokens=256),
    )
    assert ok
    llm.capabilities.supports_tools = True
    return llm


def test_structured_tool_call_single_step_from_mock_provider(mock_chat_server):
    llm = _connect_remote(mock_chat_server.url)
    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "read_file",
                                    "arguments": json.dumps({"path": "C:/tmp/a.txt"}),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )

    result = llm.chat_completion(
        messages=[{"role": "user", "content": "read file"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read file",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                },
            }
        ],
    )
    assert result.error == ""
    assert result.has_tool_calls
    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].arguments["path"] == "C:/tmp/a.txt"


def test_agent_multi_step_tool_loop_with_mock_provider(mock_chat_server, minimal_workspace):
    llm = _connect_remote(mock_chat_server.url)

    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Need tool",
                        "tool_calls": [
                            {
                                "id": "tc-1",
                                "type": "function",
                                "function": {
                                    "name": "echo_tool",
                                    "arguments": json.dumps({"text": "hello"}),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )
    mock_chat_server.enqueue_json(
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "done"},
                    "finish_reason": "stop",
                }
            ]
        }
    )

    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo_tool",
            description="Echo back text",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            execute_fn=lambda args: {"echo": args["text"]},
        )
    )

    agent = Agent(
        config=AgentConfig(
            max_iterations=4,
            max_repeats=3,
            timeout=30.0,
            workspace_dir=str(minimal_workspace),
        ),
        llm=llm,
        tools=registry,
    )
    answer = agent.run("start")

    assert answer == "done"
    assert len(mock_chat_server.requests) == 2
    second_payload = mock_chat_server.requests[1]["payload"]
    assert any(m.get("role") == "tool" and m.get("tool_call_id") == "tc1" for m in second_payload["messages"])


def test_parallel_tool_calls_flag_on_and_off(mock_chat_server):
    llm = _connect_remote(mock_chat_server.url)
    tool_defs = [
        {
            "type": "function",
            "function": {
                "name": "noop",
                "description": "noop",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    mock_chat_server.enqueue_json(
        {
            "choices": [
                {"message": {"role": "assistant", "content": "first"}, "finish_reason": "stop"}
            ]
        }
    )
    llm.chat_completion(
        messages=[{"role": "user", "content": "first"}],
        tools=tool_defs,
        parallel_tool_calls=False,
    )

    mock_chat_server.enqueue_json(
        {
            "choices": [
                {"message": {"role": "assistant", "content": "second"}, "finish_reason": "stop"}
            ]
        }
    )
    llm.chat_completion(
        messages=[{"role": "user", "content": "second"}],
        tools=tool_defs,
        parallel_tool_calls=True,
    )

    first_payload = mock_chat_server.requests[0]["payload"]
    second_payload = mock_chat_server.requests[1]["payload"]
    assert "parallel_tool_calls" not in first_payload
    assert second_payload["parallel_tool_calls"] is True
