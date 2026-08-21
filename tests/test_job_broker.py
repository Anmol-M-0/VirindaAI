from __future__ import annotations

import threading
import time

import pytest

from virinda.config.settings import Settings
from virinda.infrastructure.jobs import (
    InProcessJobBroker,
    JobEnvelope,
    NatsJetStreamJobBroker,
    _subject_matches,
)


def test_subject_matches_supports_wildcards_and_tail() -> None:
    assert _subject_matches("virinda.jobs.>", "virinda.jobs.routines.execute")
    assert _subject_matches("virinda.*.execute", "virinda.routines.execute")
    assert not _subject_matches("virinda.*.execute", "virinda.routines.preview")
    assert not _subject_matches("virinda.jobs", "virinda.jobs.extra")


def test_inprocess_broker_runs_job() -> None:
    broker = InProcessJobBroker()
    seen = []
    event = threading.Event()
    broker.start_worker("virinda.jobs.>", lambda job: (seen.append(job), event.set()))
    job = JobEnvelope("virinda.jobs.routine", {"routine_id": "r1"})
    assert broker.publish(job) == job.id
    assert event.wait(1.0)
    assert seen[0].payload["routine_id"] == "r1"
    broker.close()


def test_inprocess_broker_deduplicates_idempotency_keys() -> None:
    broker = InProcessJobBroker()
    seen = []
    event = threading.Event()
    broker.start_worker("virinda.jobs.>", lambda job: (seen.append(job), event.set()))
    first = JobEnvelope("virinda.jobs.routine", {}, idempotency_key="same")
    second = JobEnvelope("virinda.jobs.routine", {}, idempotency_key="same")
    broker.publish(first)
    broker.publish(second)
    assert event.wait(1.0)
    time.sleep(0.1)
    assert len(seen) == 1
    broker.close()


def test_inprocess_broker_delayed_job() -> None:
    broker = InProcessJobBroker()
    seen = []
    event = threading.Event()
    broker.start_worker("virinda.jobs.>", lambda job: (seen.append(job), event.set()))
    job = JobEnvelope("virinda.jobs.routine", {}, available_at=time.time() + 0.05)
    broker.publish(job)
    assert event.wait(1.0)
    broker.close()


def test_nats_backend_fails_clearly_without_optional_dependency(monkeypatch) -> None:
    broker = NatsJetStreamJobBroker("nats://127.0.0.1:4222")
    monkeypatch.setattr(
        broker,
        "_ensure_started",
        lambda: (_ for _ in ()).throw(RuntimeError("NATS job broker failed to start")),
    )
    with pytest.raises(RuntimeError, match="NATS job broker failed"):
        broker.publish(JobEnvelope("virinda.jobs.test", {}))


def test_settings_expose_nats_delivery_policy() -> None:
    settings = Settings.from_env()
    assert settings.nats_ack_wait_seconds >= 5
    assert settings.nats_max_deliver >= 1
    assert settings.nats_max_ack_pending >= 1


def test_nats_broker_keeps_delivery_policy() -> None:
    broker = NatsJetStreamJobBroker(
        "nats://127.0.0.1:4222",
        ack_wait_seconds=45,
        max_deliver=7,
        max_ack_pending=12,
    )
    assert broker.ack_wait_seconds == 45
    assert broker.max_deliver == 7
    assert broker.max_ack_pending == 12
    broker.close()


def test_redelivered_succeeded_routine_is_idempotent(tmp_path):
    import sqlite3
    from threading import RLock

    from virinda.features import Routine, RoutineRunner, RoutineStore

    conn = sqlite3.connect(":memory:")
    store = RoutineStore(conn, RLock())
    routine = Routine("r1", "one-shot", "at:0", "notify:done|once", True)
    store.save(routine)
    calls = []
    runner = RoutineRunner(
        store, lambda title, body: calls.append((title, body)), lambda *a, **k: None
    )

    assert runner.dispatch(routine, trigger_context={"now": 1}, run_id="run-1") == "succeeded"
    assert calls == [("done", "once")]
    assert (
        runner.handle_job(
            type(
                "Job",
                (),
                {
                    "payload": {
                        "routine_id": "r1",
                        "trigger_context": {"now": 1},
                        "approved_run": False,
                        "run_id": "run-1",
                    }
                },
            )()
        )
        == "succeeded"
    )
    assert calls == [("done", "once")]


def test_pending_approval_persists_for_resume(tmp_path):
    import sqlite3
    from threading import RLock

    from virinda.features import Routine, RoutineRunner, RoutineStore

    conn = sqlite3.connect(":memory:")
    store = RoutineStore(conn, RLock())
    routine = Routine(
        "r2", "approve", "at:0", 'approve:tool:open_url|{"url":"https://example.com"}', True
    )
    store.save(routine)
    approvals = []
    runner = RoutineRunner(
        store,
        lambda *a: None,
        lambda *a, **k: approvals.append(k),
        approval_requester=lambda tool: {"tool": tool, "token": "hidden"},
    )

    assert runner.dispatch(routine, run_id="run-2") == "pending_approval"
    assert runner.resume_approved("run-2") == "succeeded"
    assert approvals == [{"approved": True, "url": "https://example.com"}]


def test_nats_consumer_uses_single_message_next_msg_and_acks(monkeypatch):
    import asyncio
    import json

    broker = NatsJetStreamJobBroker("nats://127.0.0.1:4222")
    seen = []

    class FakeMessage:
        data = json.dumps({"subject": "virinda.jobs.test", "payload": {"ok": True}}).encode()

        async def ack(self):
            broker._stop.set()

        async def nak(self):
            broker._stop.set()
            raise AssertionError("test job must not be negatively acknowledged")

        async def in_progress(self):
            return None

    class FakeSubscription:
        def __init__(self):
            self.called = False

        async def next_msg(self, timeout):
            assert timeout == 0.5
            if self.called:
                return None
            self.called = True
            return FakeMessage()

    async def handler(job):
        seen.append(job.payload)

    broker._subscription = FakeSubscription()
    broker._handler = handler
    asyncio.run(broker._consume())
    assert seen == [{"ok": True}]
    broker.close()


def test_nats_consumer_info_projection_is_stable(monkeypatch):
    import asyncio

    broker = NatsJetStreamJobBroker("nats://127.0.0.1:4222", stream="marina_jobs", durable="worker")

    class Info:
        name = "worker"
        stream_name = "marina_jobs"
        created = "2026-08-21T10:00:00Z"
        num_ack_pending = 2
        num_redelivered = 3
        num_waiting = 1
        num_pending = 7
        delivered = type("Delivered", (), {"consumer_seq": 42, "stream_seq": 99})()

    class JS:
        async def consumer_info(self, stream, durable):
            assert stream == "marina_jobs"
            assert durable == "worker"
            return Info()

    broker._js = JS()
    broker._worker_subject = "virinda.jobs.>"
    result = asyncio.run(broker._consumer_info())
    assert result["name"] == "worker"
    assert result["num_pending"] == 7
    assert result["num_redelivered"] == 3
    assert result["num_ack_pending"] == 2
    assert result["delivered"] == 42
    assert result["stream_seq"] == 99
    broker.close()


def test_inprocess_broker_status_exposes_runtime_metrics() -> None:
    broker = InProcessJobBroker()
    status = broker.status()
    assert status.backend == "inprocess"
    assert status.configured is True
    assert status.connected is False
    broker.close()


def test_inprocess_broker_status_counts_processed_jobs() -> None:
    broker = InProcessJobBroker()
    event = threading.Event()
    broker.start_worker("virinda.jobs.>", lambda job: event.set())
    job = JobEnvelope("virinda.jobs.test", {})
    broker.publish(job)
    assert event.wait(1.0)
    deadline = time.time() + 1.0
    while broker.status().processed < 1 and time.time() < deadline:
        time.sleep(0.01)
    status = broker.status()
    assert status.processed == 1
    assert status.last_job_id == job.id
    broker.close()


def test_routine_store_reports_stale_active_runs() -> None:
    import sqlite3
    from threading import RLock

    from virinda.features import RoutineRun, RoutineStore

    store = RoutineStore(sqlite3.connect(":memory:"), RLock())
    store.record_run(RoutineRun("old", "routine", "running", 1, 10.0))
    stale = store.stale_runs(older_than_seconds=5.0, now=20.0)
    assert [run.id for run in stale] == ["old"]


def test_inprocess_worker_survives_failed_handler() -> None:
    broker = InProcessJobBroker()
    done = threading.Event()
    calls: list[str] = []

    def handler(job):
        calls.append(job.id)
        if len(calls) == 1:
            raise RuntimeError("boom")
        done.set()

    broker.start_worker("virinda.jobs.>", handler)
    first = JobEnvelope("virinda.jobs.test", {})
    second = JobEnvelope("virinda.jobs.test", {})
    broker.publish(first)
    broker.publish(second)
    assert done.wait(1.0)
    assert broker.status().failed == 1
    assert broker.status().processed == 1
    assert len(calls) == 2
    broker.close()


def test_inprocess_idempotency_key_can_retry_after_failure() -> None:
    broker = InProcessJobBroker()
    done = threading.Event()
    attempts = 0

    def handler(job):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("retry me")
        done.set()

    broker.start_worker("virinda.jobs.>", handler)
    job = JobEnvelope("virinda.jobs.test", {}, idempotency_key="retryable")
    broker.publish(job)
    deadline = time.time() + 1.0
    while broker.status().failed < 1 and time.time() < deadline:
        time.sleep(0.01)
    broker.publish(job)
    assert done.wait(1.0)
    assert attempts == 2
    broker.close()


def test_inprocess_cancel_releases_idempotency_key_for_republish() -> None:
    broker = InProcessJobBroker()
    first = JobEnvelope(
        "virinda.jobs.test",
        {"x": 1},
        idempotency_key="cancel-republish",
        available_at=time.time() + 60,
    )
    replacement = JobEnvelope(
        "virinda.jobs.test",
        {"x": 2},
        idempotency_key="cancel-republish",
        available_at=time.time() + 60,
    )
    assert broker.publish(first) == first.id
    assert broker.cancel(first.id) is True
    assert broker.publish(replacement) == replacement.id
    assert len(broker._jobs) == 1
    assert broker._jobs[0][2].id == replacement.id
    broker.close()


def test_inprocess_cancel_removes_only_matching_queued_job() -> None:
    broker = InProcessJobBroker()
    first = JobEnvelope("virinda.jobs.test", {"x": 1}, available_at=time.time() + 60)
    second = JobEnvelope("virinda.jobs.test", {"x": 2}, available_at=time.time() + 60)
    broker.publish(first)
    broker.publish(second)
    assert broker.cancel(first.id) is True
    assert broker.cancel(first.id) is False
    assert len(broker._jobs) == 1
    assert broker._jobs[0][2].id == second.id
    broker.close()


def test_inprocess_delayed_job_is_cancelled_on_close() -> None:
    broker = InProcessJobBroker()
    seen = []
    broker.start_worker("virinda.jobs.>", lambda job: seen.append(job))
    broker.publish(JobEnvelope("virinda.jobs.test", {}, available_at=time.time() + 0.25))
    broker.close()
    time.sleep(0.35)
    assert seen == []


def test_inprocess_rejects_unhandled_subject_when_worker_started() -> None:
    broker = InProcessJobBroker()
    broker.start_worker("virinda.jobs.automation.>", lambda job: None)
    with pytest.raises(ValueError, match="not handled by worker"):
        broker.publish(JobEnvelope("virinda.jobs.other.test", {}))
    broker.close()


def test_nats_startup_waits_for_ready_event(monkeypatch) -> None:
    broker = NatsJetStreamJobBroker("nats://127.0.0.1:4222")
    broker._thread = threading.Thread(target=lambda: None)
    broker._ready.clear()
    monkeypatch.setattr(broker, "_thread_main", lambda: (time.sleep(0.05), broker._ready.set()))
    broker._thread = None
    broker._ensure_started()
    assert broker._ready.is_set()
    broker.close()


def test_nats_existing_incompatible_stream_is_rejected() -> None:
    import asyncio

    broker = NatsJetStreamJobBroker("nats://127.0.0.1:4222", stream="marina_jobs")

    class Config:
        subjects = ["other.>"]
        retention = "limits"

    class Info:
        config = Config()

    class JS:
        async def add_stream(self, **kwargs):
            raise RuntimeError("stream name already in use")

        async def stream_info(self, name):
            return Info()

    class NC:
        def jetstream(self):
            return JS()

    async def connect_stub(*args, **kwargs):
        return NC()

    class NatsModule:
        class js:
            class api:
                class RetentionPolicy:
                    WORK_QUEUE = "workqueue"

        connect = staticmethod(connect_stub)

    with pytest.raises(RuntimeError, match="incompatible"):
        asyncio.run(broker._connect(NatsModule))


def test_nats_publish_uses_server_side_schedule_for_future_jobs() -> None:
    import asyncio

    broker = NatsJetStreamJobBroker("nats://127.0.0.1:4222")
    captured = {}

    class JS:
        async def publish(self, subject, body, headers=None):
            captured.update(subject=subject, body=body, headers=headers)

    broker._js = JS()
    future = time.time() + 60
    job = JobEnvelope("virinda.jobs.test", {"x": 1}, available_at=future)
    asyncio.run(broker._publish(job))
    assert captured["subject"].startswith("virinda.jobs.schedules.")
    assert captured["subject"].endswith(job.id)
    assert captured["headers"]["Nats-Msg-Id"] == job.id
    assert captured["headers"]["Nats-Schedule"].startswith("@at ")
    assert captured["headers"]["Nats-Schedule-Target"] == job.subject
    broker.close()


def test_nats_delayed_jobs_get_unique_schedule_subjects() -> None:
    import asyncio

    broker = NatsJetStreamJobBroker("nats://127.0.0.1:4222")
    captured = []

    class JS:
        async def publish(self, subject, body, headers=None):
            captured.append((subject, headers))

    broker._js = JS()
    when = time.time() + 60
    first = JobEnvelope("virinda.jobs.test", {"x": 1}, available_at=when)
    second = JobEnvelope("virinda.jobs.test", {"x": 2}, available_at=when)
    asyncio.run(broker._publish(first))
    asyncio.run(broker._publish(second))
    assert captured[0][0] != captured[1][0]
    assert captured[0][1]["Nats-Schedule-Target"] == first.subject
    assert captured[1][1]["Nats-Schedule-Target"] == second.subject
    broker.close()


def test_nats_cancel_purges_schedule_by_job_id() -> None:
    import asyncio

    broker = NatsJetStreamJobBroker("nats://127.0.0.1:4222")
    captured = {}

    class JS:
        async def publish(self, subject, body, headers=None):
            captured.update(subject=subject, body=body, headers=headers)

    broker._js = JS()
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(broker._cancel("abc123"))
    finally:
        loop.close()
    assert captured["subject"] == "virinda.jobs.control.cancel"
    assert captured["headers"]["Nats-Scheduler"] == "virinda.jobs.schedules.abc123"
    assert captured["headers"]["Nats-Schedule-Next"] == "purge"
    broker.close()


def test_nats_publish_keeps_immediate_jobs_unscheduled() -> None:
    import asyncio

    broker = NatsJetStreamJobBroker("nats://127.0.0.1:4222")
    captured = {}

    class JS:
        async def publish(self, subject, body, headers=None):
            captured.update(subject=subject, headers=headers)

    broker._js = JS()
    job = JobEnvelope("virinda.jobs.test", {}, available_at=time.time() - 1)
    asyncio.run(broker._publish(job))
    assert captured["subject"] == job.subject
    assert "Nats-Schedule" not in captured["headers"]
    broker.close()


def test_nats_existing_stream_must_enable_message_schedules() -> None:
    import asyncio

    broker = NatsJetStreamJobBroker("nats://127.0.0.1:4222", stream="marina_jobs")

    class Config:
        subjects = ["virinda.jobs.>"]
        retention = "workqueue"
        allow_msg_schedules = False

    class Info:
        config = Config()

    class JS:
        async def add_stream(self, **kwargs):
            raise RuntimeError("stream name already in use")

        async def stream_info(self, name):
            return Info()

    class NC:
        def jetstream(self):
            return JS()

    async def connect_stub(*args, **kwargs):
        return NC()

    class NatsModule:
        class js:
            class api:
                class RetentionPolicy:
                    WORK_QUEUE = "workqueue"

        connect = staticmethod(connect_stub)

    with pytest.raises(RuntimeError, match="allow_msg_schedules"):
        asyncio.run(broker._connect(NatsModule))


def test_nats_publish_rejects_subject_outside_stream_prefix() -> None:
    broker = NatsJetStreamJobBroker("nats://127.0.0.1:4222", subject_prefix="virinda.jobs")
    with pytest.raises(ValueError, match="outside NATS stream prefix"):
        broker.publish(JobEnvelope("other.jobs.test", {}))
    broker.close()


def test_nats_existing_consumer_delivery_policy_is_validated() -> None:
    import asyncio

    broker = NatsJetStreamJobBroker(
        "nats://127.0.0.1:4222",
        ack_wait_seconds=120,
        max_deliver=5,
        max_ack_pending=32,
        durable="worker",
    )

    class Config:
        ack_wait = 60.0
        max_deliver = 5
        max_ack_pending = 32
        filter_subject = "virinda.jobs.>"

    class Info:
        config = Config()

    class JS:
        async def consumer_info(self, stream, durable):
            assert stream == "marina_jobs"
            assert durable == "worker"
            return Info()

    broker._js = JS()
    with pytest.raises(RuntimeError, match="ack_wait"):
        asyncio.run(broker._validate_consumer_config())
    broker.close()


def test_nats_existing_consumer_filter_is_validated() -> None:
    import asyncio

    broker = NatsJetStreamJobBroker("nats://127.0.0.1:4222", durable="worker")

    class Config:
        ack_wait = 120.0
        max_deliver = 5
        max_ack_pending = 32
        filter_subject = "virinda.jobs.automation.>"

    class Info:
        config = Config()

    class JS:
        async def consumer_info(self, stream, durable):
            return Info()

    broker._js = JS()
    broker._worker_subject = "virinda.jobs.>"
    with pytest.raises(RuntimeError, match="filter_subject"):
        asyncio.run(broker._validate_consumer_config())
    broker.close()
