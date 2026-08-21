from pathlib import Path

from virinda.application.service import AssistantService
from virinda.core.events import InMemoryEventBus
from virinda.domain.events import ResponseCompleted
from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore
from virinda.infrastructure.providers.echo import EchoProvider
from virinda.infrastructure.providers.router import StaticProviderRouter


def test_events_are_persisted_and_reloaded(tmp_path: Path) -> None:
    store = SQLiteConversationStore(tmp_path / "virinda.sqlite3")
    service = AssistantService(
        router=StaticProviderRouter({"echo": EchoProvider()}, "echo"),
        store=store,
        event_bus=InMemoryEventBus(),
    )
    assert service.ask("hello") == "Marina received: hello"
    events = store.load_events(service.snapshot().session_id)
    assert any(isinstance(event, ResponseCompleted) for event in events)
    service.close()
