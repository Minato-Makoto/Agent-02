import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest


@dataclass
class _QueuedReply:
    kind: str
    status: int
    body: Any


class MockChatServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._lock = threading.Lock()
        self._queue: List[_QueuedReply] = []
        self.requests: List[Dict[str, Any]] = []
        self._get_routes: Dict[str, _QueuedReply] = {}

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def enqueue_json(self, body: Dict[str, Any], status: int = 200) -> None:
        with self._lock:
            self._queue.append(_QueuedReply(kind="json", status=status, body=body))

    def enqueue_error(self, message: str, status: int = 400) -> None:
        payload = {"error": {"message": message}}
        with self._lock:
            self._queue.append(_QueuedReply(kind="json", status=status, body=payload))

    def enqueue_stream(self, chunks: List[Dict[str, Any]], status: int = 200) -> None:
        with self._lock:
            self._queue.append(_QueuedReply(kind="stream", status=status, body=chunks))

    def set_get_json(self, path: str, body: Dict[str, Any], status: int = 200) -> None:
        with self._lock:
            self._get_routes[path] = _QueuedReply(kind="json", status=status, body=body)

    def pop_reply(self) -> Optional[_QueuedReply]:
        with self._lock:
            if not self._queue:
                return None
            return self._queue.pop(0)

    def push_request(self, path: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            self.requests.append({"path": path, "payload": payload})


def _handler_factory(state: MockChatServer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def do_GET(self):  # noqa: N802
            if self.path == "/health":
                body = json.dumps({"status": "ok"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            route = state._get_routes.get(self.path)
            if route is not None:
                response_bytes = json.dumps(route.body).encode("utf-8")
                self.send_response(route.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response_bytes)))
                self.end_headers()
                self.wfile.write(response_bytes)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            state.push_request(self.path, payload)

            reply = state.pop_reply()
            if reply is None:
                reply = _QueuedReply(
                    kind="json",
                    status=200,
                    body={
                        "choices": [
                            {
                                "message": {"role": "assistant", "content": "ok"},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                )

            if reply.kind == "stream":
                self.send_response(reply.status)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                for chunk in reply.body:
                    line = f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
                    self.wfile.write(line)
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                return

            response_bytes = json.dumps(reply.body).encode("utf-8")
            self.send_response(reply.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_bytes)))
            self.end_headers()
            self.wfile.write(response_bytes)

    return Handler


@pytest.fixture
def mock_chat_server():
    state = MockChatServer("127.0.0.1", 0)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_factory(state))
    state.host = server.server_address[0]
    state.port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.fixture
def minimal_workspace(tmp_path: Path) -> Path:
    for name in ("IDENTITY.md", "SOUL.md", "AGENT.md", "USER.md"):
        (tmp_path / name).write_text(f"# {name}\n", encoding="utf-8")
    (tmp_path / "skills").mkdir(exist_ok=True)
    return tmp_path
