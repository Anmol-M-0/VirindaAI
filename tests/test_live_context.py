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
    return AssistantService(
        router=StaticProviderRouter({"echo": EchoProvider()}, "echo"),
        store=SQLiteConversationStore(tmp_path / "live.sqlite3"),
        event_bus=InMemoryEventBus(),
    )


def test_ovos_live_context_does_not_duplicate_persistence_by_default(tmp_path):
    service = _service(tmp_path)
    try:
        state = service.observe_ovos_utterance("hello from voice", speaker="alice")
        assert state["last_user_utterance"] == "hello from voice"
        assert state["speaker"] == "alice"
        assert service.store.load_messages(service.snapshot().session_id) == []
        state = service.observe_ovos_speak("hello back")
        assert state["last_assistant_text"] == "hello back"
        service.observe_ovos_speech_complete()
        assert service.live_session_context()["speaking"] is False
    finally:
        service.close()


def test_meeting_utterances_enter_meeting_transcript_only(tmp_path):
    service = _service(tmp_path)
    try:
        service.start_meeting()
        service.observe_ovos_utterance("action item one")
        meeting = service.meetings_snapshot()[0]
        assert "action item one" in meeting["transcript"]
        assert service.store.load_messages(service.snapshot().session_id) == []
    finally:
        service.close()


def test_live_context_available_over_ipc(tmp_path):
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
        client.call("ovos_utterance", text="hello", speaker="alice")
        context = client.call("live_context")
        assert context["last_user_utterance"] == "hello"
        assert context["speaker"] == "alice"
    finally:
        server.shutdown()
        service.close()
        thread.join(timeout=2)
