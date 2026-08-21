from __future__ import annotations

import threading
from pathlib import Path

from virinda.application.service import AssistantService
from virinda.core.events import InMemoryEventBus
from virinda.domain.models import ProviderRequest
from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore
from virinda.infrastructure.providers.router import StaticProviderRouter
from virinda.interfaces.ipc import LocalRPCClient, LocalRPCServer


class StreamingProvider:
    name = "stream"

    def stream(self, request: ProviderRequest):
        yield "hello"
        yield " world"


def _service(tmp_path: Path) -> AssistantService:
    store = SQLiteConversationStore(tmp_path / "ipc.sqlite3")
    return AssistantService(
        router=StaticProviderRouter({"stream": StreamingProvider()}, "stream"),
        store=store,
        event_bus=InMemoryEventBus(),
        default_provider="stream",
        default_model="demo",
    )


def test_ipc_stream_delivers_deltas_and_completion(tmp_path: Path) -> None:
    service = _service(tmp_path)
    path = tmp_path / "virinda.sock"
    server = LocalRPCServer(service, path)
    server.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = LocalRPCClient(path)
        events = list(client.stream("hi"))
        assert any(event["type"] == "ResponseDelta" for event in events)
        assert any(event["type"] == "ResponseCompleted" for event in events)
    finally:
        server.shutdown()
        service.close()
        thread.join(timeout=2)
