import time
from pathlib import Path

from virinda.application.service import AssistantService
from virinda.core.events import InMemoryEventBus
from virinda.features import ContextSignals, VoiceProfile, WakeWordEvaluator, WakeWordResult
from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore
from virinda.infrastructure.providers.echo import EchoProvider
from virinda.infrastructure.providers.router import StaticProviderRouter


def service(tmp_path: Path) -> AssistantService:
    store = SQLiteConversationStore(tmp_path / "m.db")
    return AssistantService(
        router=StaticProviderRouter({"echo": EchoProvider()}, "echo"),
        store=store,
        event_bus=InMemoryEventBus(),
    )


def test_memory_private_mode_and_semantic_search(tmp_path):
    s = service(tmp_path)
    try:
        s.memory_fact("favorite_color", "blue")
        s.memory_add_note("I like blue bicycles")
        assert s.memory_search("blue")["facts"]
        assert s.memory_search("bicycle")["notes"]
        s.set_context_mode("private")
        try:
            s.memory_fact("secret", "hidden")
            raise AssertionError("private mode should reject persisted memory")
        except PermissionError:
            pass
    finally:
        s.close()


def test_alerts_notifications_and_routines(tmp_path):
    s = service(tmp_path)
    try:
        item = s.schedule_alert("reminder", "test", time.time() + 60)
        assert s.cancel_alert(item["id"])
        n = s.alerts.notify("Hello", "World")
        assert s.notification_summary() == "Hello: World"
        r = s.save_routine("greeting", "keyword:hello", "notify:Greeting|Hi")
        assert s.run_routines_for_text("hello virinda") == [r["id"]]
    finally:
        s.close()


def test_tool_audit_and_safe_filesystem(tmp_path):
    s = service(tmp_path)
    try:
        result = s.tool_execute("system.info")
        assert "platform" in result
        path = tmp_path / "note.txt"
        s.tool_execute("filesystem.write", approved=True, path=str(path), content="hello")
        assert s.tool_execute("filesystem.read", path=str(path)) == "hello"
        try:
            s.tool_execute("filesystem.read", path="/etc/passwd")
            raise AssertionError("path traversal should be rejected")
        except PermissionError:
            pass
        assert s.tool_audit_snapshot()
    finally:
        s.close()


def test_meeting_profile_and_audio_features(tmp_path):
    s = service(tmp_path)
    try:
        meeting = s.start_meeting()
        s.append_meeting_transcript("Opening discussion")
        ended = s.stop_meeting()
        assert meeting["id"] == ended["id"]
        s.save_voice_profile(VoiceProfile("default"))
        assert s.voice_profiles_snapshot()[0]["name"] == "default"
        assert "devices" in s.audio_devices()
    finally:
        s.close()


def test_proactive_context_respects_quiet_mode(tmp_path):
    s = service(tmp_path)
    try:
        signals = ContextSignals(meeting_active=True, headset_connected=False)
        assert s.proactive_evaluate(signals)
        s.set_context_mode("quiet")
        assert s.proactive_evaluate(signals) == []
    finally:
        s.close()


def test_wakeword_metrics():
    metrics = WakeWordEvaluator.evaluate(
        [
            WakeWordResult(True, True, 100),
            WakeWordResult(True, False, 0),
            WakeWordResult(False, True, 0),
            WakeWordResult(False, False, 0),
        ]
    )
    assert metrics["false_rejection_rate"] == 0.5
    assert metrics["false_accept_rate"] == 0.5


def test_feature_health_exposes_all_roadmap_planes(tmp_path):
    s = service(tmp_path)
    try:
        health = s.health()["features"]
        assert "live_context" in s.health()
        assert {
            "memory",
            "alerts",
            "notifications",
            "routines",
            "voice_profiles",
            "voice_benchmark",
            "meeting",
        } <= health.keys()
    finally:
        s.close()


def test_private_mode_does_not_persist_transcript(tmp_path):
    s = service(tmp_path)
    try:
        s.set_context_mode("private")
        assert s.ask("secret question")
        assert s.store.load_messages(s.snapshot().session_id) == []
    finally:
        s.close()


def test_provider_selection_and_briefing(tmp_path):
    s = service(tmp_path)
    try:
        assert s.select_provider("echo")["provider"] == "echo"
        s.schedule_alert("reminder", "demo", time.time() + 120)
        assert "upcoming alerts" in s.briefing().lower()
    finally:
        s.close()


def test_multimodal_and_satellite_validation(tmp_path):
    s = service(tmp_path)
    try:
        signals = s.desktop_signals()
        assert "active_application" in signals
        try:
            s.camera_capture(tmp_path / "camera.png", "/dev/null")
        except (RuntimeError, FileNotFoundError, OSError):
            pass
        envelope = s.satellite_send
        assert callable(envelope)
    finally:
        s.close()


def test_profile_and_schedule_are_exposed_over_ipc(tmp_path):
    from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore
    from virinda.infrastructure.providers.echo import EchoProvider
    from virinda.infrastructure.providers.router import StaticProviderRouter
    from virinda.interfaces.ipc import LocalRPCServer

    store = SQLiteConversationStore(tmp_path / "ipc-profile.sqlite3")
    service = AssistantService(
        router=StaticProviderRouter({"echo": EchoProvider()}, "echo"),
        store=store,
        event_bus=InMemoryEventBus(),
    )
    server = LocalRPCServer(service, tmp_path / "virinda.sock")
    try:
        profile = server.dispatch(
            {
                "id": 1,
                "method": "profile_update",
                "params": {"changes": {"display_name": "Virinda User"}},
            }
        )
        assert profile["result"]["display_name"] == "Virinda User"
        routine = server.dispatch(
            {
                "id": 2,
                "method": "routine_schedule",
                "params": {"name": "x", "due_at": 1, "action": "notify:T|B"},
            }
        )
        assert routine["ok"] is True
        assert routine["result"]["trigger"].startswith("at:")
    finally:
        service.close()
