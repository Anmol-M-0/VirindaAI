from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

from marina.application.service import AssistantService
from marina.core.events import InMemoryEventBus
from marina.infrastructure.persistence.sqlite import SQLiteConversationStore
from marina.infrastructure.providers.echo import EchoProvider
from marina.infrastructure.providers.router import StaticProviderRouter
from marina.interfaces.ipc import LocalRPCServer


def test_cli_can_target_daemon_socket(tmp_path: Path):
    store = SQLiteConversationStore(tmp_path / "cli.sqlite3")
    service = AssistantService(
        router=StaticProviderRouter({"echo": EchoProvider()}, default="echo"),
        store=store,
        event_bus=InMemoryEventBus(),
    )
    path = tmp_path / "marina.sock"
    server = LocalRPCServer(service, path)
    server.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "marina", "--socket", str(path), "ask", "hello daemon"],
            cwd=Path(__file__).parents[1],
            env={"PYTHONPATH": str(Path(__file__).parents[1] / "src")},
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "Marina received: hello daemon"
    finally:
        server.shutdown()
        service.close()
        thread.join(timeout=2)


def test_ipc_capabilities_and_context(tmp_path: Path):
    store = SQLiteConversationStore(tmp_path / "cap.sqlite3")
    service = AssistantService(
        router=StaticProviderRouter({"echo": EchoProvider()}, default="echo"),
        store=store,
        event_bus=InMemoryEventBus(),
    )
    socket_path = tmp_path / "cap.sock"
    server = LocalRPCServer(service, socket_path)
    server.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        from marina.interfaces.ipc import LocalRPCClient
        client = LocalRPCClient(socket_path)
        caps = client.call("capabilities")
        assert any(item["name"] == "browser_control" for item in caps)
        context = client.call("set_context", mode="private")
        assert context["mode"] == "private"
        assert context["persist_transcripts"] is False
    finally:
        server.shutdown()
        service.close()
        thread.join(timeout=2)
