from __future__ import annotations

from threading import Event, Thread

from virinda.application.service import AssistantService
from virinda.core.events import InMemoryEventBus
from virinda.domain.models import ProviderRequest
from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore
from virinda.infrastructure.providers.echo import EchoProvider
from virinda.infrastructure.providers.router import StaticProviderRouter


class BlockingProvider:
    name = "blocking"

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()

    def stream(self, request: ProviderRequest):
        self.started.set()
        self.release.wait(timeout=2)
        yield "late-result"


def make_service(tmp_path, provider):
    store = SQLiteConversationStore(tmp_path / "virinda.sqlite3")
    router = StaticProviderRouter(
        {"blocking": provider, "echo": EchoProvider()}, default="blocking"
    )
    return AssistantService(
        router=router,
        store=store,
        event_bus=InMemoryEventBus(),
        default_provider="blocking",
        default_model="test",
    )


def test_late_response_cannot_commit_after_new_generation(tmp_path):
    provider = BlockingProvider()
    service = make_service(tmp_path, provider)
    try:
        results: list[str] = []
        thread = Thread(target=lambda: results.append(service.ask("first")))
        thread.start()
        assert provider.started.wait(timeout=2)
        service.cancel("test")
        provider.release.set()
        thread.join(timeout=2)

        assert results == [""]
        messages = service.store.load_messages(service.snapshot().session_id)
        assert [m.content for m in messages] == ["first"]
    finally:
        service.close()
