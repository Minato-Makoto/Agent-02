from agentforge.cli_runtime import _build_callbacks, _render_agent_result


class _UIStub:
    def __init__(self):
        self.events = []

    def stream_start(self):
        self.events.append("stream_start")

    def stream_end(self):
        self.events.append("stream_end")

    def stream_token(self, token):
        self.events.append(("stream_token", token))

    def stream_reasoning(self, token):
        self.events.append(("stream_reasoning", token))

    def thinking_start(self):
        self.events.append("thinking_start")

    def thinking_stop(self):
        self.events.append("thinking_stop")

    def show_tool_call(self, name, arguments):
        self.events.append(("show_tool_call", name, arguments))

    def tool_call_stream_start(self, name):
        self.events.append(("tool_call_stream_start", name))

    def tool_call_stream_token(self, token):
        self.events.append(("tool_call_stream_token", token))

    def tool_call_stream_end(self):
        self.events.append("tool_call_stream_end")

    def show_tool_result(self, name, result):
        self.events.append(("show_tool_result", name, result))

    def status(self, message):
        self.events.append(("status", message))

    def error(self, message):
        self.events.append(("error", message))


def test_non_stream_result_closes_once_without_duplicate_processing_lane():
    ui = _UIStub()
    callbacks, stream_state = _build_callbacks(ui)

    callbacks.on_thinking_start()
    callbacks.on_reasoning("thinking")
    callbacks.on_stream_end()
    _render_agent_result(ui, "final answer", stream_state)

    stream_end_events = [event for event in ui.events if event == "stream_end"]
    assert len(stream_end_events) == 1


def test_streamed_tokens_still_close_on_stream_end():
    ui = _UIStub()
    callbacks, stream_state = _build_callbacks(ui)

    callbacks.on_thinking_start()
    callbacks.on_token("hello")
    callbacks.on_stream_end()
    _render_agent_result(ui, "hello", stream_state)

    stream_end_events = [event for event in ui.events if event == "stream_end"]
    assert len(stream_end_events) == 1
