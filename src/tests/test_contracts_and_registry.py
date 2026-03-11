import json

from agentforge.contracts import ToolCall
from agentforge.prompting import PromptBuilder
from agentforge.tool_id import remap_tool_call_ids, sanitize_tool_call_id
from agentforge.tools import Tool, ToolRegistry


def test_tool_registry_to_openai_tools_contract():
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="sum_numbers",
            description="Sum two integers",
            input_schema={
                "type": "object",
                "properties": {
                    "a": {"type": "int"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
            execute_fn=lambda args: {"result": args["a"] + args["b"]},
        )
    )

    tools = registry.to_openai_tools()
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    fn = tools[0]["function"]
    assert fn["name"] == "sum_numbers"
    assert fn["description"] == "Sum two integers"
    assert fn["parameters"]["type"] == "object"
    assert fn["parameters"]["properties"]["a"]["type"] == "integer"


def test_prompt_builder_serializes_tool_call_and_tool_result_messages():
    pb = PromptBuilder()
    pb.set_system("sys")
    pb.add_user("hello")
    pb.add_assistant_tool_calls(
        [
            ToolCall(
                id="call_1",
                name="sum_numbers",
                arguments={"a": 1, "b": 2},
            )
        ],
        content="Calling tool",
    )
    pb.add_tool_result("call_1", "sum_numbers", {"result": 3})

    messages = pb.build_messages()
    assert messages[0] == {"role": "system", "content": "sys"}
    assert messages[1] == {"role": "user", "content": "hello"}
    assert messages[2]["role"] == "assistant"
    assert messages[2]["tool_calls"][0]["function"]["name"] == "sum_numbers"
    assert json.loads(messages[2]["tool_calls"][0]["function"]["arguments"]) == {"a": 1, "b": 2}
    assert messages[3]["role"] == "tool"
    assert messages[3]["tool_call_id"] == "call_1"


def test_tool_call_id_sanitization_and_collision_remap():
    assert sanitize_tool_call_id("call-1:abc", mode="strict") == "call1abc"
    strict9 = sanitize_tool_call_id("tool-id", mode="strict9")
    assert strict9.isalnum()
    assert len(strict9) == 9

    remapped = remap_tool_call_ids({"a:b": "", "a|b": ""}, mode="strict")
    assert remapped["a:b"] != remapped["a|b"]
