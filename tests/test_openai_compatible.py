import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from virinda.domain.models import Message, ProviderRequest
from virinda.infrastructure.providers.openai_compatible import OpenAICompatibleProvider


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        payload = json.loads(self.rfile.read(length))
        if payload["stream"]:
            chunks = ["hello", " world", "!"]
            body = (
                b"".join(
                    f"data: {json.dumps({'choices': [{'delta': {'content': chunk}}]})}\n\n".encode()
                    for chunk in chunks
                )
                + b"data: [DONE]\n\n"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = json.dumps({"choices": [{"message": {"content": "hello!"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def test_openai_compatible_provider_streams_sse() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        provider = OpenAICompatibleProvider(
            name="test",
            base_url=f"http://127.0.0.1:{server.server_port}",
            api_key="x",
            default_model="demo",
        )
        request = ProviderRequest(1, "demo", (Message("user", "hello"),))
        assert list(provider.stream(request)) == ["hello", " world", "!"]
    finally:
        server.shutdown()
        server.server_close()
