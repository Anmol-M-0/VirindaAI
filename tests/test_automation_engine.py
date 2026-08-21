import sqlite3
import time
import unittest
from datetime import UTC
from threading import RLock

from virinda.features import Routine, RoutineRunner, RoutineStore


class AutomationEngineTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.store = RoutineStore(self.conn, RLock())
        self.notifications = []
        self.tools = []
        self.approvals = []
        self.events = []
        self.runner = RoutineRunner(
            self.store,
            lambda title, body: self.notifications.append((title, body)),
            lambda name, **kwargs: self.tools.append((name, kwargs)),
            approval_requester=lambda name: {
                "token": "secret",
                "tool": name,
                "expires_at": time.time() + 30,
            },
            emit=lambda event, payload: self.events.append((event, payload)),
        )

    def test_multi_step_action_and_run_ledger(self):
        routine = self.store.save(
            Routine(
                "r1",
                "Morning",
                "event:morning",
                "notify:Hello|Good morning||notify:Agenda|Review calendar",
            )
        )
        self.assertEqual(self.runner.run_event("morning"), [routine.id])
        self.assertEqual(len(self.notifications), 2)
        runs = self.store.runs("r1")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].status, "succeeded")
        self.assertEqual(self.events[-1][0], "routine.completed")

    def test_event_payload_trigger_matches_application(self):
        routine = self.store.save(Routine("r2", "VSCode", "app:code", "notify:Focus|Coding mode"))
        self.assertEqual(
            self.runner.run_event("desktop.context", {"application": "Code - OSS"}), [routine.id]
        )
        self.assertEqual(self.notifications[0][0], "Focus")

    def test_retry_and_failure_are_recorded(self):
        attempts = []

        def failing_tool(name, **kwargs):
            attempts.append(name)
            raise RuntimeError("boom")

        runner = RoutineRunner(self.store, lambda *_: None, failing_tool)
        routine = self.store.save(
            Routine(
                "r3",
                "Failing",
                "event:test",
                "tool:desktop.launch|{}",
                retry_limit=2,
                retry_backoff_seconds=0,
            )
        )
        status = runner.execute(routine)
        self.assertEqual(status, "failed")
        self.assertEqual(len(attempts), 3)
        run = self.store.runs("r3")[0]
        self.assertEqual(run.attempt, 3)
        self.assertEqual(run.status, "failed")

    def test_approval_checkpoint_pauses_without_running_tool(self):
        routine = self.store.save(
            Routine(
                "r4",
                "Open",
                "event:open",
                'tool:browser.open|{"url":"https://example.com"}',
                require_approval=True,
            )
        )
        self.assertEqual(self.runner.run_event("open"), [routine.id])
        self.assertEqual(self.tools, [])
        run = self.store.runs("r4")[0]
        self.assertEqual(run.status, "pending_approval")
        self.assertTrue(run.approval_required)

    def test_approval_resume_executes_once(self):
        routine = self.store.save(
            Routine(
                "r5",
                "Open",
                "event:open",
                'approve:tool:browser.open|{"url":"https://example.com"}',
            )
        )
        self.runner.run_event("open")
        run = self.store.runs("r5")[0]
        self.assertEqual(run.status, "pending_approval")
        self.assertEqual(self.runner.resume_approved(run.id), "succeeded")
        self.assertEqual(len(self.tools), 1)

    def test_legacy_routine_schema_migrates(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE routines(id TEXT PRIMARY KEY,name TEXT,trigger TEXT,action TEXT,enabled INTEGER)"
        )
        conn.execute("INSERT INTO routines VALUES('legacy','Legacy','at:1','notify:Legacy|ok',1)")
        conn.commit()
        store = RoutineStore(conn, RLock())
        routine = store.list()[0]
        self.assertEqual(routine.name, "Legacy")
        self.assertEqual(routine.retry_limit, 0)
        self.assertFalse(routine.require_approval)


if __name__ == "__main__":
    unittest.main()


def test_schedule_trigger_preserves_weekday_semantics():
    from datetime import datetime

    routine = self = None
    conn = sqlite3.connect(":memory:")
    store = RoutineStore(conn, RLock())
    notices = []
    runner = RoutineRunner(
        store, lambda title, body: notices.append((title, body)), lambda name, **kwargs: None
    )
    routine = store.save(
        Routine("weekday", "Weekday", "schedule:every weekday at 9 am", "notify:Marina|stand up")
    )
    friday = datetime(2026, 8, 21, 10, 0, tzinfo=UTC).timestamp()
    # The runner's local timezone is the host timezone; this assertion only checks that
    # a Friday occurrence is eligible and a Saturday occurrence is not re-fired.
    assert runner._due_match(routine, friday) is True
    runner.execute(routine, trigger_context={"now": friday})
    saturday = datetime(2026, 8, 22, 10, 0, tzinfo=UTC).timestamp()
    assert runner._due_match(routine, saturday) is False


def test_routine_edit_delete_disable_and_conflict_detection():
    conn = sqlite3.connect(":memory:")
    store = RoutineStore(conn, RLock())
    first = store.save(
        Routine("r1", "Morning", "schedule:every weekday at 9 am", "notify:Marina|hello")
    )
    conflicts = store.conflicts(
        Routine("r2", "Duplicate", "schedule:every weekday at 9 am", "notify:Marina|bye")
    )
    assert [item.id for item in conflicts] == ["r1"]
    updated = store.update("r1", name="Morning Updated", action="notify:Marina|updated")
    assert updated is not None and updated.name == "Morning Updated"
    assert store.disable("r1") is True
    assert store.get("r1").enabled is False
    assert store.delete("r1") is True
    assert store.get("r1") is None


def test_routine_interpolates_profile_and_context_values():
    conn = sqlite3.connect(":memory:")
    store = RoutineStore(conn, RLock())
    notifications = []
    runner = RoutineRunner(
        store,
        lambda title, body: notifications.append((title, body)),
        lambda name, **kwargs: None,
        context_provider=lambda: {
            "profile": {"display_name": "Anmol"},
            "context": {"mode": "focus"},
        },
    )
    routine = store.save(
        Routine(
            "r3",
            "Personal",
            "event:test",
            "notify:Marina|Hello {{profile.display_name}} ({{context.mode}} mode)",
        )
    )
    assert runner.run_event("test") == [routine.id]
    assert notifications == [("Marina", "Hello Anmol (focus mode)")]


def test_routine_context_interpolation_unknown_values_become_empty():
    conn = sqlite3.connect(":memory:")
    store = RoutineStore(conn, RLock())
    notices = []
    runner = RoutineRunner(
        store, lambda title, body: notices.append((title, body)), lambda name, **kwargs: None
    )
    routine = store.save(
        Routine("r4", "Context", "event:test", "notify:Marina|Hello {{missing.value}}")
    )
    runner.run_event("test")
    assert notices == [("Marina", "Hello")]


def test_routine_preview_is_side_effect_free_and_explains_approval():
    conn = sqlite3.connect(":memory:")
    store = RoutineStore(conn, RLock())
    notifications = []
    tool_calls = []
    runner = RoutineRunner(
        store,
        lambda title, body: notifications.append((title, body)),
        lambda name, **kwargs: tool_calls.append((name, kwargs)),
        approval_requester=lambda name: {"token": "secret", "tool": name, "expires_at": 123.0},
        context_provider=lambda: {"profile": {"display_name": "Anmol"}},
    )
    routine = store.save(
        Routine(
            "preview",
            "Dashboard",
            "schedule:every weekday at 9 am",
            'notify:Marina|Hello {{profile.display_name}}||approve:tool:browser.open|{"url":"https://example.com"}',
        )
    )
    preview = runner.dry_run(routine)
    assert preview["routine"]["name"] == "Dashboard"
    assert preview["requires_approval"] is True
    assert preview["steps"][0]["body"] == "Hello Anmol"
    assert preview["steps"][1]["tool"] == "browser.open"
    assert preview["steps"][1]["approval_required"] is True
    assert notifications == []
    assert tool_calls == []
    assert store.runs() == []


def test_routine_preview_reports_conflicts():
    conn = sqlite3.connect(":memory:")
    store = RoutineStore(conn, RLock())
    runner = RoutineRunner(store, lambda *args: None, lambda *args, **kwargs: None)
    store.save(Routine("one", "One", "event:test", "notify:Marina|one"))
    second = store.save(Routine("two", "Two", "event:test", "notify:Marina|two"))
    preview = runner.explain(second)
    assert [item["name"] for item in preview["conflicts"]] == ["One"]
    assert preview["will_execute"] is False
