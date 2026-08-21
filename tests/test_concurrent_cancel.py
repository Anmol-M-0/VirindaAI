import threading
from pathlib import Path

from marina.application.service import AssistantService
from marina.core.events import InMemoryEventBus
from marina.domain.models import ProviderRequest
from marina.infrastructure.persistence.sqlite import SQLiteConversationStore
from marina.infrastructure.providers.router import StaticProviderRouter


class BlockingProvider:
    name = "blocking"

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def stream(self, request: ProviderRequest):
        self.started.set()
        self.release.wait(2)
        yield "stale result"


def test_cancel_invalidates_late_provider_result(tmp_path: Path) -> None:
    provider = BlockingProvider()
    store = SQLiteConversationStore(tmp_path / "marina.sqlite3")
    service = AssistantService(
        router=StaticProviderRouter({"blocking": provider}, "blocking"),
        store=store,
        event_bus=InMemoryEventBus(),
        default_provider="blocking",
    )
    result: list[str] = []
    worker = threading.Thread(target=lambda: result.append(service.ask("hello")))
    worker.start()
    assert provider.started.wait(1)
    service.cancel()
    provider.release.set()
    worker.join(2)
    assert result == [""]
    assert [m.role for m in store.load_messages(service.snapshot().session_id)] == ["user"]
    service.close()
