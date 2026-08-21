from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

from virinda.application.service import AssistantService
from virinda.core.events import InMemoryEventBus
from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore
from virinda.infrastructure.providers.echo import EchoProvider
from virinda.infrastructure.providers.router import StaticProviderRouter
from virinda.interfaces.ipc import LocalRPCClient, LocalRPCServer


def _service(tmp_path: Path) -> AssistantService:
    store = SQLiteConversationStore(tmp_path / "ipc.sqlite3")
    bus = InMemoryEventBus()
    router = StaticProviderRouter({"echo": EchoProvider()}, default="echo")
    return AssistantService(router=router, store=store, event_bus=bus)


def test_local_rpc_roundtrip_and_cleanup(tmp_path: Path):
    service = _service(tmp_path)
    path = tmp_path / "virinda.sock"
    server = LocalRPCServer(service, path)
    server.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if path.exists():
                break
            time.sleep(0.01)
        client = LocalRPCClient(path)
        assert "echo" in client.call("providers")
        result = client.call("ask", text="hello")
        assert result == "Virinda received: hello"
        history = client.call("history")
        assert [item["role"] for item in history][-2:] == ["user", "assistant"]
        status = client.call("status")
        assert status["status"] == "ok"
    finally:
        server.shutdown()
        service.close()
        thread.join(timeout=2)
    assert not path.exists()


def test_local_rpc_rejects_bad_requests(tmp_path: Path):
    service = _service(tmp_path)
    path = tmp_path / "virinda.sock"
    server = LocalRPCServer(service, path)
    server.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(str(path))
            client.sendall(b'{"id":2,"method":"unknown"}\n')
            response = client.makefile("rb").readline()
        assert b'"ok": false' in response.lower()
        assert b"unknown method" in response
    finally:
        server.shutdown()
        service.close()
        thread.join(timeout=2)
