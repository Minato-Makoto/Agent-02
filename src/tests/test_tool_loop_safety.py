from agentforge.tool_loop import ToolLoop
from agentforge.tools import Tool, ToolRegistry


def _registry_with_tool(name: str, output: str) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name=name,
            description="test tool",
            input_schema={"type": "object", "properties": {}},
            execute_fn=lambda args: output,
        )
    )
    return registry


def test_generic_repeat_detection_blocks_identical_calls():
    registry = _registry_with_tool("noop", "ok")
    loop = ToolLoop(registry=registry, max_iterations=10, max_repeats=3, timeout=60.0)

    r1 = loop.execute_tool("noop", {"a": 1})
    r2 = loop.execute_tool("noop", {"a": 1})
    r3 = loop.execute_tool("noop", {"a": 1})

    assert r1.success is True
    assert r2.success is True
    assert r3.success is False
    assert "Loop detected" in r3.error


def test_no_progress_polling_hits_global_circuit_breaker():
    registry = _registry_with_tool("process", "still running")
    loop = ToolLoop(
        registry=registry,
        max_iterations=20,
        max_repeats=50,
        timeout=60.0,
        warning_threshold=3,
        critical_threshold=4,
        global_threshold=4,
    )

    args = {"action": "poll", "job_id": "abc"}
    # First five calls build a no-progress streak with identical outcomes.
    # global_threshold is clamped to critical_threshold + 1 in ToolLoop.__init__.
    for _ in range(5):
        res = loop.execute_tool("process", args)
        assert res.success is True

    blocked = loop.execute_tool("process", args)
    assert blocked.success is False
    assert "Global circuit breaker" in blocked.error


def test_ping_pong_detection_blocks_alternating_patterns():
    registry = _registry_with_tool("process", "same result")
    loop = ToolLoop(
        registry=registry,
        max_iterations=20,
        max_repeats=50,
        timeout=60.0,
        warning_threshold=4,
        critical_threshold=5,
        global_threshold=20,
    )

    assert loop.execute_tool("process", {"action": "poll", "id": "A"}).success
    assert loop.execute_tool("process", {"action": "poll", "id": "B"}).success
    assert loop.execute_tool("process", {"action": "poll", "id": "A"}).success
    blocked = loop.execute_tool("process", {"action": "poll", "id": "B"})

    assert blocked.success is False
    assert "Ping-pong" in blocked.error
