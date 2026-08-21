from pathlib import Path

from marina.application.service import AssistantService
from marina.core.events import InMemoryEventBus
from marina.infrastructure.persistence.sqlite import SQLiteConversationStore
from marina.infrastructure.providers.echo import EchoProvider
from marina.infrastructure.providers.router import StaticProviderRouter


def build_service(tmp_path: Path):
    store = SQLiteConversationStore(tmp_path / "marina.db")
    return AssistantService(
        router=StaticProviderRouter({"echo": EchoProvider()}, "echo"),
        store=store,
        event_bus=InMemoryEventBus(),
    )

def test_service_persists_turn(tmp_path: Path) -> None:
    store = SQLiteConversationStore(tmp_path / "marina.sqlite3")
    service = AssistantService(
        router=StaticProviderRouter({"echo": EchoProvider()}, "echo"),
        store=store,
        event_bus=InMemoryEventBus(),
    )
    result = service.ask("hello")
    assert result == "Marina received: hello"
    messages = store.load_messages(service.snapshot().session_id)
    assert [m.role for m in messages] == ["user", "assistant"]


class RecordingProvider:
    name = "recording"
    def __init__(self):
        self.last = None
    def stream(self, request):
        self.last = request
        yield "ok"


def test_memory_is_injected_as_bounded_context(tmp_path: Path) -> None:
    store = SQLiteConversationStore(tmp_path / "marina.sqlite3")
    provider = RecordingProvider()
    service = AssistantService(
        router=StaticProviderRouter({"recording": provider}, "recording"),
        store=store,
        event_bus=InMemoryEventBus(),
    )
    try:
        service.memory_fact("favorite color", "blue")
        service.ask("Can you tell me my favorite color?", provider="recording")
        assert provider.last is not None
        assert any(m.role == "system" and "favorite color: blue" in m.content for m in provider.last.messages)
        assert provider.last.metadata["context_mode"] == "normal"
    finally:
        service.close()


def test_private_mode_does_not_inject_memory_context(tmp_path: Path) -> None:
    store = SQLiteConversationStore(tmp_path / "marina.sqlite3")
    provider = RecordingProvider()
    service = AssistantService(
        router=StaticProviderRouter({"recording": provider}, "recording"),
        store=store,
        event_bus=InMemoryEventBus(),
    )
    try:
        service.memory_fact("secret", "do not send")
        service.set_context_mode("private")
        service.ask("hello", provider="recording")
        assert provider.last is not None
        assert not any("do not send" in m.content for m in provider.last.messages)
        assert provider.last.metadata["context_mode"] == "private"
    finally:
        service.close()


def test_service_selects_inprocess_job_broker(monkeypatch, tmp_path):
    monkeypatch.setenv("MARINA_JOB_BROKER", "inprocess")
    service = build_service(tmp_path)
    try:
        from marina.infrastructure.jobs import InProcessJobBroker
        assert isinstance(service.job_broker, InProcessJobBroker)
    finally:
        service.close()


def test_service_selects_nats_job_broker(monkeypatch, tmp_path):
    monkeypatch.setenv("MARINA_JOB_BROKER", "nats")
    monkeypatch.setenv("MARINA_NATS_URL", "nats://127.0.0.1:4222")
    service = build_service(tmp_path)
    try:
        from marina.infrastructure.jobs import NatsJetStreamJobBroker
        assert isinstance(service.job_broker, NatsJetStreamJobBroker)
    finally:
        service.close()
