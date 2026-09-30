"""Shared test fixtures. Everything here is local and offline: no real GPU,
no real Ollama, no network beyond loopback sockets the test itself starts.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


def make_openai_stream_transport(chunks_per_request: int = 5, delay_s: float = 0.0):
    """An httpx.MockTransport that answers /v1/chat/completions and /api/ps
    like a small OpenAI-compatible local server, without any real socket."""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "mock-model"}]})
        if request.url.path == "/v1/chat/completions":
            body = json.loads(request.content or b"{}")
            if body.get("stream", True):

                def body_iter():
                    for _ in range(chunks_per_request):
                        if delay_s:
                            time.sleep(delay_s)
                        chunk = {"choices": [{"delta": {"content": "hi "}}]}
                        yield f"data: {json.dumps(chunk)}\n\n".encode()
                    yield b"data: [DONE]\n\n"

                return httpx.Response(200, content=body_iter())
            return httpx.Response(200, json={"choices": [{"message": {"content": "hi hi hi"}}]})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def mock_client_factory():
    """Returns a factory of the same shape as httpx.AsyncClient, backed by a mock transport."""
    import httpx

    def _make(chunks_per_request: int = 5, delay_s: float = 0.0):
        transport = make_openai_stream_transport(chunks_per_request, delay_s)

        def factory(**kwargs):
            kwargs.pop("timeout", None)
            return httpx.AsyncClient(transport=transport, base_url="http://mock")

        return factory

    return _make


class _StubHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path == "/api/ps":
            body = json.dumps({"models": [{"name": "stub-model"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(200)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        stream = payload.get("stream", True)
        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for _ in range(3):
                chunk = {"choices": [{"delta": {"content": "hi "}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        else:
            body = json.dumps({"choices": [{"message": {"content": "hi hi hi"}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


@pytest.fixture
def stub_server() -> Iterator[str]:
    """A tiny local HTTP server standing in for an OpenAI-compatible backend."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
