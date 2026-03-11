from agentforge.tools import Tool
import asyncio


async def _async_tool_impl(args):
    return {"echo": args.get("value")}


def test_tool_execute_supports_async_return_in_sync_runtime():
    tool = Tool(
        name="async_echo",
        description="async echo",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
        execute_fn=_async_tool_impl,
    )

    result = tool.execute({"value": "ok"})
    assert result.success is True
    assert result.output == {"echo": "ok"}


def test_tool_execute_supports_async_return_when_event_loop_is_running():
    tool = Tool(
        name="async_echo",
        description="async echo",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
        execute_fn=_async_tool_impl,
    )

    async def _run():
        return tool.execute({"value": "loop"})

    result = asyncio.run(_run())
    assert result.success is True
    assert result.output == {"echo": "loop"}
