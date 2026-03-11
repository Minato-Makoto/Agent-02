"""
TurnExecutor — run Agent turns in a worker thread with a global run lock.

Hooks into ``StreamCallbacks`` to emit WebSocket events in real time.
Only one model turn can be active at a time (MVP global lock).
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
from typing import Any, Callable, Dict, Optional

from ..agent_core import StreamCallbacks

logger = logging.getLogger(__name__)


class TurnExecutor:
    """Execute agent turns in a background thread, one at a time."""

    def __init__(self):
        self._lock = threading.Lock()
        self._busy = False

    @property
    def is_busy(self) -> bool:
        return self._busy

    async def execute_turn(
        self,
        *,
        agent: Any,
        user_input: str,
        emit_fn: Callable,
    ) -> str:
        """
        Run ``agent.run(user_input)`` in a worker thread.

        *emit_fn* is an ``async def emit(event_type, payload)`` coroutine
        that the executor calls (from the event loop) to push streaming
        events to WebSocket clients.

        Returns the final assistant text.
        """
        if not self._lock.acquire(blocking=False):
            await emit_fn("error", {"message": "Another turn is already in progress. Please wait."})
            return "[Busy]"

        self._busy = True
        loop = asyncio.get_event_loop()

        try:
            result = await loop.run_in_executor(
                None,
                self._run_sync,
                agent,
                user_input,
                emit_fn,
                loop,
            )
            return result
        finally:
            self._busy = False
            self._lock.release()

    def _run_sync(
        self,
        agent: Any,
        user_input: str,
        emit_fn: Callable,
        loop: asyncio.AbstractEventLoop,
    ) -> str:
        """Synchronous wrapper executed inside the thread pool."""

        emit_queue: "queue.SimpleQueue[Optional[tuple[str, Dict[str, Any]]]]" = queue.SimpleQueue()

        def _emit_worker() -> None:
            while True:
                item = emit_queue.get()
                if item is None:
                    return
                event_type, payload = item
                try:
                    asyncio.run_coroutine_threadsafe(
                        emit_fn(event_type, payload), loop
                    ).result(timeout=5)
                except Exception:
                    logger.debug("Failed to emit %s event.", event_type, exc_info=True)

        emitter_thread = threading.Thread(
            target=_emit_worker,
            name="agent-02-turn-emitter",
            daemon=True,
        )
        emitter_thread.start()

        def _emit_sync(event_type: str, payload: Dict[str, Any]) -> None:
            """Queue the async emit without blocking model generation."""
            try:
                emit_queue.put((event_type, payload))
            except Exception:
                logger.debug("Failed to emit %s event.", event_type, exc_info=True)

        callbacks = StreamCallbacks(
            on_token=lambda token: _emit_sync("assistant.delta", {"token": token}),
            on_reasoning=lambda token: _emit_sync("assistant.reasoning", {"token": token}),
            on_tool_call=lambda name, args: _emit_sync(
                "tool.call.start", {"name": name, "index": 0}
            ),
            on_tool_call_start=lambda name, idx: _emit_sync(
                "tool.call.start", {"name": name, "index": idx}
            ),
            on_tool_call_delta=lambda idx, token: _emit_sync(
                "tool.call.delta", {"index": idx, "token": token}
            ),
            on_tool_call_end=lambda idx: _emit_sync(
                "tool.call.end", {"index": idx}
            ),
            on_tool_result=lambda name, result: _emit_sync(
                "tool.result", {"name": name, "result": str(result)}
            ),
            on_stream_start=lambda: _emit_sync("status", {"text": "Generating..."}),
            on_stream_end=lambda: None,
            on_thinking_start=lambda: _emit_sync("status", {"text": "Thinking..."}),
            on_thinking_end=lambda: None,
            on_skill_activated=lambda name: _emit_sync(
                "status", {"text": f"Skill activated: {name}"}
            ),
            on_status=lambda text: _emit_sync("status", {"text": text}),
        )

        try:
            result = agent.run(user_input, callbacks=callbacks)
        except Exception as exc:
            logger.exception("Agent turn failed.")
            _emit_sync("error", {"message": str(exc)})
            result = f"[Error: {exc}]"

        _emit_sync("assistant.done", {"content": result})

        emit_queue.put(None)
        emitter_thread.join(timeout=5)
        if emitter_thread.is_alive():
            logger.debug("Turn emitter thread did not drain before timeout.")
        return result
