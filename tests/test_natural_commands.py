from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from virinda.application.service import AssistantService
from virinda.core.events import InMemoryEventBus
from virinda.core.natural_commands import NaturalCommandParser, parse_due_time
from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore
from virinda.infrastructure.providers.echo import EchoProvider
from virinda.infrastructure.providers.router import StaticProviderRouter


def build_service(tmp_path: Path):
    store = SQLiteConversationStore(tmp_path / "virinda.db")
    return AssistantService(
        router=StaticProviderRouter({"echo": EchoProvider()}, "echo"),
        store=store,
        event_bus=InMemoryEventBus(),
    )


def test_parser_handles_high_confidence_commands():
    parser = NaturalCommandParser()
    assert parser.parse("remember my favorite color is blue").kind == "remember_fact"
    assert parser.parse("call me Anmol").args == ("Anmol",)
    assert parser.parse("what is my favorite color?").args == ("favorite color",)
    assert parser.parse("go private mode").args == ("private",)
    assert parser.parse("remind me to stretch in 10 minutes").args == ("stretch", "in 10 minutes")
    assert parser.parse("tell me about quantum mechanics") is None


def test_relative_due_time_is_deterministic():
    now = datetime(2026, 8, 21, 5, 10, tzinfo=ZoneInfo("Asia/Kolkata"))
    due = parse_due_time("in 10 minutes", now=now, timezone="Asia/Kolkata")
    assert due == (now.timestamp() + 600)


def test_absolute_due_time_rolls_to_tomorrow_when_passed():
    now = datetime(2026, 8, 21, 20, 45, tzinfo=ZoneInfo("Asia/Kolkata"))
    due = datetime.fromtimestamp(
        parse_due_time("at 8:30 pm", now=now, timezone="Asia/Kolkata"), ZoneInfo("Asia/Kolkata")
    )
    assert due.date().isoformat() == "2026-08-22"
    assert due.hour == 20 and due.minute == 30


def test_service_interprets_memory_profile_context_and_reminder(tmp_path: Path):
    s = build_service(tmp_path)
    try:
        assert (
            s.ask("remember my favorite color is blue")
            == "I'll remember that your favorite color is blue."
        )
        assert s.profile_snapshot()["display_name"] is None
        assert s.ask("what is my favorite color?") == "Your favorite color is blue."
        assert s.ask("call me Anmol") == "Got it. I'll call you Anmol."
        assert s.ask("what's my name?") == "You asked me to call you Anmol."
        assert s.ask("go quiet mode") == "Marina is now in quiet mode."
        assert s.context()["mode"] == "quiet"
    finally:
        s.close()


def test_recurring_reminder_provider_model_and_tool_request_parser():
    parser = NaturalCommandParser()
    cmd = parser.parse("remind me to stand up every weekday at 8 am")
    assert cmd is not None and cmd.kind == "recurring_reminder"
    assert cmd.args == ("stand up", "every weekday at 8 am")
    assert parser.parse("switch to echo provider").args == ("echo",)
    assert parser.parse("use model llama3.2").args == ("llama3.2",)
    assert parser.parse("open https://example.com").kind == "tool_request"


def test_parse_recurrence_weekday_and_interval():
    from virinda.core.natural_commands import parse_recurrence

    now = datetime(2026, 8, 21, 5, 10, tzinfo=ZoneInfo("Asia/Kolkata"))  # Friday
    due, interval = parse_recurrence("every weekday at 8 am", now=now, timezone="Asia/Kolkata")
    dt = datetime.fromtimestamp(due, ZoneInfo("Asia/Kolkata"))
    assert dt.weekday() == 4 and dt.hour == 8
    assert interval == 86400
    due2, interval2 = parse_recurrence("every 2 hours", now=now, timezone="Asia/Kolkata")
    assert due2 == now.timestamp() + 7200
    assert interval2 == 7200


def test_service_handles_recurring_reminders_and_provider_selection(tmp_path: Path):
    s = build_service(tmp_path)
    try:
        result = s.ask("remind me to stretch every 2 hours")
        assert result.startswith("Recurring reminder set")
        alerts = s.alerts_snapshot()
        assert len(alerts) == 1
        assert alerts[0]["recurring_seconds"] == 7200
        assert s.ask("switch to echo provider") == "Provider set to echo."
        assert s.ask("use model offline-demo") == "Model set to offline-demo."
        response = s.ask("open https://example.com")
        assert "approval" in response.lower() and "say yes" in response.lower()
    finally:
        s.close()


def test_sensitive_memory_is_rejected_and_uncertain_memory_gets_lower_confidence(tmp_path: Path):
    s = build_service(tmp_path)
    try:
        assert "won't store" in s.ask("remember my password is hunter2").lower()
        assert s.memory_snapshot()["facts"] == []
        result = s.ask("I think my favorite color is blue")
        assert "medium confidence" in result
        fact = s.memory_snapshot()["facts"][0]
        assert fact["confidence"] == 0.6
    finally:
        s.close()


def test_personalized_briefing_and_natural_briefing_command(tmp_path: Path):
    s = build_service(tmp_path)
    try:
        s.update_profile(display_name="Anmol")
        s.schedule_alert("reminder", "stretch", __import__("time").time() + 600)
        text = s.briefing()
        assert "Anmol" in text
        assert "stretch" in text
        assert s.ask("give me my daily briefing") == text
    finally:
        s.close()


def test_natural_confirmation_completes_pending_tool_request(tmp_path: Path):
    s = build_service(tmp_path)
    try:
        calls = []

        def fake_execute(name, **kwargs):
            calls.append((name, kwargs))
            return "opened"

        s.tool_execute = fake_execute  # type: ignore[method-assign]
        pending = s.ask("open https://example.com")
        assert "approval" in pending.lower()
        assert s.ask("yes") == "Done: opened"
        assert calls[0][0] == "browser.open"
        assert calls[0][1]["url"] == "https://example.com"
    finally:
        s.close()


def test_natural_automation_plan_is_reviewable_and_safe():
    from virinda.core.natural_commands import plan_automation

    now = datetime(2026, 8, 21, 5, 10, tzinfo=ZoneInfo("Asia/Kolkata"))
    plan = plan_automation(
        "every weekday at 9 am, open https://example.com and notify me that the dashboard is ready",
        now=now,
        timezone="Asia/Kolkata",
    )
    assert plan.trigger == "schedule:every weekday at 9 am"
    assert "approve:tool:browser.open" in plan.action
    assert "notify:Marina|that the dashboard is ready" in plan.action
    assert plan.require_approval is True


def test_service_saves_automation_only_after_confirmation(tmp_path: Path):
    s = build_service(tmp_path)
    try:
        preview = s.ask("create a routine every 2 hours, notify me to stretch")
        assert "Say yes to save it" in preview
        assert s.routines_snapshot() == []
        saved = s.ask("yes")
        assert "Automation saved" in saved
        routines = s.routines_snapshot()
        assert len(routines) == 1
        assert routines[0]["action"].startswith("notify:Marina|")
    finally:
        s.close()


def test_natural_routine_lifecycle_commands_parse():
    from virinda.core.natural_commands import NaturalCommandParser

    parser = NaturalCommandParser()
    assert parser.parse("disable the routine Morning Review").kind == "disable_routine"
    assert parser.parse("delete the routine Morning Review").args == ("Morning Review",)
    assert (
        parser.parse(
            "change the routine Morning Review to every weekday at 10 am, notify me to review the dashboard"
        ).kind
        == "edit_routine"
    )


def test_preview_routine_command_is_deterministic(tmp_path: Path):
    s = build_service(tmp_path)
    try:
        s.save_routine("Morning", "event:morning", "notify:Marina|Hello")
        response = s.ask("preview the routine Morning")
        assert "Morning is enabled" in response
        assert "Trigger: event:morning" in response
        assert "notify Marina: Hello" in response
    finally:
        s.close()
