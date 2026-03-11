from agentforge.agent_core import Agent, AgentConfig
from agentforge.contracts import ChatCompletionResult
from agentforge.tools import Tool, ToolRegistry


class _FallbackLLM:
    def __init__(self):
        self.capabilities = type("Caps", (), {"supports_tools": False})()
        self.round = 0

    def chat_completion(self, messages, **kwargs):
        self.round += 1
        if self.round == 1:
            return ChatCompletionResult(
                content='<tool_call>{"name":"echo_tool","arguments":{"text":"hello"}}</tool_call>',
            )
        return ChatCompletionResult(content="final")


def test_agent_uses_text_fallback_parser_when_provider_has_no_tools(minimal_workspace):
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="echo_tool",
            description="echo",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            execute_fn=lambda args: f"echo:{args['text']}",
        )
    )
    agent = Agent(
        config=AgentConfig(
            max_iterations=4,
            max_repeats=3,
            timeout=30.0,
            workspace_dir=str(minimal_workspace),
        ),
        llm=_FallbackLLM(),
        tools=registry,
    )

    answer = agent.run("start")
    assert answer == "final"
