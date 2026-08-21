import time
from pathlib import Path

from marina.application.service import AssistantService
from marina.core.events import InMemoryEventBus
from marina.infrastructure.persistence.sqlite import SQLiteConversationStore
from marina.infrastructure.providers.echo import EchoProvider
from marina.infrastructure.providers.router import StaticProviderRouter


def build_service(tmp_path: Path):
    store = SQLiteConversationStore(tmp_path / "marina.db")
    bus = InMemoryEventBus()
    router = StaticProviderRouter({"echo": EchoProvider()}, "echo")
    return AssistantService(router=router, store=store, event_bus=bus)


def test_context_and_capabilities_are_exposed(tmp_path):
    service = build_service(tmp_path)
    try:
        assert service.context()["mode"] == "normal"
        service.set_context_mode("private")
        assert service.context()["persist_transcripts"] is False
        names = {item["name"] for item in service.capability_snapshot()}
        assert {"conversation", "voice", "browser_control"} <= names
        health = service.health()
        assert health["context"]["mode"] == "private"
    finally:
        service.close()


def test_profile_personalization_and_private_mode(tmp_path):
    s = build_service(tmp_path)
    try:
        updated = s.update_profile(display_name="Anmol", timezone="Asia/Kolkata", preferred_voice="default")
        assert updated["display_name"] == "Anmol"
        assert s.profile_snapshot()["timezone"] == "Asia/Kolkata"
        s.set_context_mode("private")
        try:
            s.update_profile(display_name="Hidden")
            raise AssertionError("private mode should reject profile persistence")
        except PermissionError:
            pass
        assert s.profile_snapshot()["display_name"] == "Anmol"
        s.clear_profile()
        assert s.profile_snapshot()["display_name"] is None
    finally:
        s.close()


def test_scheduled_routine_runs_once(tmp_path):
    s = build_service(tmp_path)
    try:
        routine = s.schedule_routine("remind", time.time() - 1, "notify:Reminder|Do it")
        assert routine["trigger"].startswith("at:")
        assert s.run_due_routines() == [routine["id"]]
        assert s.run_due_routines() == []
        assert s.notification_summary() == "Reminder: Do it"
    finally:
        s.close()


def test_service_health_exposes_job_broker_and_automation(tmp_path):
    service = build_service(tmp_path)
    try:
        health = service.health()
        assert health["job_broker"]["backend"] == "inprocess"
        assert "automation" in health
        assert health["automation"]["active_runs"] >= 0
    finally:
        service.close()
