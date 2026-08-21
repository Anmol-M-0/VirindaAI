from __future__ import annotations

import asyncio
import inspect
import json
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class JobEnvelope:
    """Durable/background work item shared by all Marina JobBroker backends."""

    subject: str
    payload: dict[str, Any]
    id: str = field(default_factory=lambda: uuid4().hex)
    idempotency_key: str | None = None
    session_id: str | None = None
    created_at: float = field(default_factory=time.time)
    available_at: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class JobBrokerStatus:
    backend: str
    configured: bool
    connected: bool
    worker_subject: str | None
    processed: int
    failed: int
    last_job_id: str | None
    last_error: str | None
    last_activity_at: float | None
    backlog_hint: int | None = None
    worker_started_at: float | None = None
    last_heartbeat_at: float | None = None
    consumer: dict[str, Any] | None = None


JobHandler = Callable[[JobEnvelope], Any]


class JobBroker(Protocol):
    """Protocol for Marina's asynchronous durable-work boundary."""

    def publish(self, job: JobEnvelope) -> str: ...

    def cancel(self, job_id: str) -> bool: ...

    def start_worker(self, subject: str, handler: JobHandler) -> None: ...

    def close(self) -> None: ...

    def status(self) -> JobBrokerStatus: ...


class InProcessJobBroker:
    """Threaded local broker used by tests/development and single-process deployments.

    The implementation deliberately models at-least-once job semantics while retaining
    synchronous completion for callers that explicitly rely on the local backend.
    """

    synchronous = True

    def __init__(self, *, max_queue: int = 1000) -> None:
        self._max_queue = max_queue
        self._jobs: list[tuple[float, int, JobEnvelope]] = []
        self._sequence = 0
        self._completed_keys: set[str] = set()
        self._inflight_keys: set[str] = set()
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._subject: str | None = None
        self._handler: JobHandler | None = None
        self._processed = 0
        self._failed = 0
        self._last_job_id: str | None = None
        self._last_error: str | None = None
        self._last_activity_at: float | None = None
        self._worker_started_at: float | None = None

    def publish(self, job: JobEnvelope) -> str:
        if not job.subject.strip():
            raise ValueError("job subject is required")
        with self._condition:
            if self._worker_subject_conflicts(job.subject):
                raise ValueError(
                    f"job subject {job.subject!r} is not handled by worker {self._subject!r}"
                )
            if job.idempotency_key and (
                job.idempotency_key in self._completed_keys
                or job.idempotency_key in self._inflight_keys
            ):
                return job.id
            if len(self._jobs) >= self._max_queue:
                raise RuntimeError("in-process job queue is full")
            self._sequence += 1
            self._jobs.append((max(time.time(), job.available_at), self._sequence, job))
            if job.idempotency_key:
                self._inflight_keys.add(job.idempotency_key)
            self._condition.notify_all()
        return job.id

    def cancel(self, job_id: str) -> bool:
        """Cancel a queued job by id."""
        if not job_id.strip():
            raise ValueError("job id is required")
        with self._condition:
            before = len(self._jobs)
            cancelled = [item[2] for item in self._jobs if item[2].id == job_id]
            self._jobs = [item for item in self._jobs if item[2].id != job_id]
            changed = len(self._jobs) != before
            if changed:
                for job in cancelled:
                    if job.idempotency_key:
                        self._inflight_keys.discard(job.idempotency_key)
                self._condition.notify_all()
            return changed

    def _worker_subject_conflicts(self, subject: str) -> bool:
        return self._subject is not None and not _subject_matches(self._subject, subject)

    def start_worker(self, subject: str, handler: JobHandler) -> None:
        if not subject.strip():
            raise ValueError("worker subject is required")
        with self._condition:
            if self._worker and self._worker.is_alive():
                raise RuntimeError("in-process job worker already started")
            self._subject = subject
            self._handler = handler
            self._stop.clear()
            self._worker_started_at = time.time()
            self._worker = threading.Thread(target=self._run, name="marina-jobs", daemon=True)
            self._worker.start()
            self._condition.notify_all()

    def _next_job(self) -> JobEnvelope | None:
        with self._condition:
            while not self._stop.is_set():
                now = time.time()
                matching = [
                    item
                    for item in self._jobs
                    if self._subject is not None
                    and _subject_matches(self._subject, item[2].subject)
                ]
                if matching:
                    due = min(matching, key=lambda item: (item[0], item[1]))
                    if due[0] <= now:
                        self._jobs.remove(due)
                        return due[2]
                    self._condition.wait(timeout=max(0.01, due[0] - now))
                    continue
                self._condition.wait(timeout=0.1)
        return None

    def _run(self) -> None:
        while not self._stop.is_set():
            job = self._next_job()
            if job is None:
                continue
            try:
                if self._handler is None:
                    raise RuntimeError("in-process job worker has no handler")
                result = self._handler(job)
                if inspect.isawaitable(result):
                    asyncio.run(result)
                with self._lock:
                    self._processed += 1
                    self._last_job_id = job.id
                    self._last_error = None
                    self._last_activity_at = time.time()
                    if job.idempotency_key:
                        self._inflight_keys.discard(job.idempotency_key)
                        self._completed_keys.add(job.idempotency_key)
            except Exception as exc:
                with self._lock:
                    self._failed += 1
                    self._last_job_id = job.id
                    self._last_error = str(exc)
                    self._last_activity_at = time.time()
                    if job.idempotency_key:
                        self._inflight_keys.discard(job.idempotency_key)
                # A single failed job must never kill the local worker. The caller can
                # republish/retry it explicitly, while subsequent jobs remain healthy.
                continue

    def status(self) -> JobBrokerStatus:
        with self._lock:
            return JobBrokerStatus(
                backend="inprocess",
                configured=True,
                connected=self._worker is not None and self._worker.is_alive(),
                worker_subject=self._subject,
                processed=self._processed,
                failed=self._failed,
                last_job_id=self._last_job_id,
                last_error=self._last_error,
                last_activity_at=self._last_activity_at,
                backlog_hint=len(self._jobs),
                worker_started_at=self._worker_started_at,
                last_heartbeat_at=None,
                consumer=None,
            )

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            self._jobs.clear()
            self._inflight_keys.clear()
            self._condition.notify_all()
        worker = self._worker
        if worker:
            worker.join(timeout=1.0)
        with self._lock:
            self._worker = None
            self._handler = None
            self._subject = None
            self._completed_keys.clear()
            self._worker_started_at = None


def _subject_matches(pattern: str, subject: str) -> bool:
    pattern_parts = pattern.split(".")
    subject_parts = subject.split(".")
    for index, part in enumerate(pattern_parts):
        if part == ">":
            return True
        if index >= len(subject_parts) or (part != "*" and part != subject_parts[index]):
            return False
    return len(pattern_parts) == len(subject_parts)


class NatsJetStreamJobBroker:
    """NATS JetStream-backed JobBroker.

    The adapter intentionally isolates the broker client behind this module. Marina's
    domain/application layers never import NATS directly. It uses a durable work-queue
    stream and explicit acknowledgements so failed jobs remain available for redelivery.

    `nats-py` is imported lazily, allowing the default in-process profile to remain
    dependency-free. The current NATS Python client exposes JetStream support directly.
    See https://github.com/nats-io/nats.py for the client/JetStream API.
    """

    synchronous = False

    def __init__(
        self,
        url: str,
        *,
        stream: str = "marina_jobs",
        subject_prefix: str = "virinda.jobs",
        durable: str = "marina-workers",
        credentials: str | None = None,
        ack_wait_seconds: float = 120.0,
        max_deliver: int = 5,
        max_ack_pending: int = 32,
    ) -> None:
        self.url = url
        self.stream = stream
        self.subject_prefix = subject_prefix.rstrip(".")
        self.durable = durable
        self.credentials = credentials
        self.ack_wait_seconds = float(ack_wait_seconds)
        self.max_deliver = int(max_deliver)
        self.max_ack_pending = int(max_ack_pending)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._nc: Any = None
        self._js: Any = None
        self._subscription: Any = None
        self._handler: JobHandler | None = None
        self._worker_subject: str | None = None
        self._startup_error: BaseException | None = None
        self._processed = 0
        self._failed = 0
        self._last_job_id: str | None = None
        self._last_error: str | None = None
        self._last_activity_at: float | None = None
        self._worker_started_at: float | None = None
        self._last_heartbeat_at: float | None = None
        self._start_lock = threading.RLock()
        self._subscription_lock = threading.RLock()

    def _ensure_started(self) -> None:
        with self._start_lock:
            if not (self._thread and self._thread.is_alive()):
                self._stop.clear()
                self._ready.clear()
                self._startup_error = None
                self._loop = None
                self._thread = threading.Thread(
                    target=self._thread_main, name="marina-nats", daemon=True
                )
                self._thread.start()
            if not self._ready.wait(timeout=10):
                raise TimeoutError("timed out starting NATS JobBroker")
            if self._startup_error:
                raise RuntimeError("NATS job broker failed to start") from self._startup_error

    def publish(self, job: JobEnvelope) -> str:
        if not job.subject.strip():
            raise ValueError("job subject is required")
        if not _subject_matches(f"{self.subject_prefix}.>", job.subject):
            raise ValueError(
                f"job subject {job.subject!r} is outside NATS stream prefix {self.subject_prefix!r}"
            )
        self._ensure_started()
        assert self._loop is not None
        if self._worker_subject and self._handler is not None and self._subscription is None:
            self._ensure_subscription()
        self._publish_now(job)
        return job.id

    def _publish_now(self, job: JobEnvelope) -> None:
        if self._loop is None:
            raise RuntimeError("NATS event loop is not ready")
        future = asyncio.run_coroutine_threadsafe(self._publish(job), self._loop)
        future.result(timeout=10)

    def _schedule_subject(self, job_id: str) -> str:
        # Each delayed job needs its own schedule-definition subject. Sharing a
        # single ``<target>.scheduled`` subject allows multiple jobs on the same
        # target to collide at the scheduler definition layer.
        return f"{self.subject_prefix}.schedules.{job_id}"

    def _schedule_control_subject(self) -> str:
        return f"{self.subject_prefix}.control.cancel"

    async def _publish(self, job: JobEnvelope) -> None:
        body = json.dumps(asdict(job), separators=(",", ":")).encode("utf-8")
        headers = {"Nats-Msg-Id": job.id}
        publish_subject = job.subject
        if job.available_at > time.time():
            when = (
                datetime.fromtimestamp(job.available_at, tz=UTC).isoformat().replace("+00:00", "Z")
            )
            headers["Nats-Schedule"] = f"@at {when}"
            headers["Nats-Schedule-Target"] = job.subject
            publish_subject = self._schedule_subject(job.id)
        await self._js.publish(publish_subject, body, headers=headers)

    def cancel(self, job_id: str) -> bool:
        """Cancel a server-side JetStream schedule by Marina job id.

        NATS implements schedule cancellation through a purge control publish: the
        ``Nats-Scheduler`` header names the schedule-definition subject and
        ``Nats-Schedule-Next: purge`` requests that schedule be removed.
        """
        if not job_id.strip():
            raise ValueError("job id is required")
        self._ensure_started()
        assert self._loop is not None
        future = asyncio.run_coroutine_threadsafe(self._cancel(job_id), self._loop)
        future.result(timeout=10)
        return True

    async def _cancel(self, job_id: str) -> None:
        headers = {
            "Nats-Scheduler": self._schedule_subject(job_id),
            "Nats-Schedule-Next": "purge",
            "Nats-Msg-Id": f"cancel:{job_id}",
        }
        await self._js.publish(self._schedule_control_subject(), b"", headers=headers)

    def start_worker(self, subject: str, handler: JobHandler) -> None:
        """Register a worker without requiring NATS to be reachable immediately."""
        if not subject.strip():
            raise ValueError("worker subject is required")
        with self._subscription_lock:
            if self._handler is not None:
                raise RuntimeError("NATS job worker already started")
            self._handler = handler
            self._worker_subject = subject
            self._worker_started_at = self._worker_started_at or time.time()
            if self._thread and self._thread.is_alive():
                self._ensure_subscription()

    def _ensure_subscription(self) -> None:
        with self._subscription_lock:
            self._ensure_started()
            assert self._loop is not None
            future = asyncio.run_coroutine_threadsafe(self._start_worker(), self._loop)
            future.result(timeout=10)

    async def _start_worker(self) -> None:
        if self._subscription is not None:
            raise RuntimeError("NATS job worker already started")
        try:
            from nats.js import api
        except ImportError as exc:
            raise RuntimeError("NATS backend requires a supported nats-py release") from exc
        config = api.ConsumerConfig(
            ack_wait=int(self.ack_wait_seconds),
            max_deliver=self.max_deliver,
            max_ack_pending=self.max_ack_pending,
        )
        self._subscription = await self._js.pull_subscribe(
            self._worker_subject,
            durable=self.durable,
            stream=self.stream,
            config=config,
        )
        try:
            await self._validate_consumer_config()
        except Exception:
            try:
                await self._subscription.unsubscribe()
            except Exception:
                pass
            self._subscription = None
            raise
        asyncio.create_task(self._consume())

    async def _validate_consumer_config(self) -> None:
        """Reject a pre-existing durable consumer with incompatible delivery policy."""
        info = await self._js.consumer_info(self.stream, self.durable)
        config = getattr(info, "config", None)
        if config is None:
            return

        ack_wait = getattr(config, "ack_wait", None)
        if hasattr(ack_wait, "total_seconds"):
            ack_wait = ack_wait.total_seconds()
        if ack_wait is not None and abs(float(ack_wait) - self.ack_wait_seconds) > 0.001:
            raise RuntimeError(
                f"existing JetStream consumer {self.durable!r} has ack_wait={ack_wait!r}; "
                f"expected {self.ack_wait_seconds!r}"
            )

        max_deliver = getattr(config, "max_deliver", None)
        if max_deliver is not None and int(max_deliver) != self.max_deliver:
            raise RuntimeError(
                f"existing JetStream consumer {self.durable!r} has max_deliver={max_deliver!r}; "
                f"expected {self.max_deliver!r}"
            )

        max_ack_pending = getattr(config, "max_ack_pending", None)
        if max_ack_pending is not None and int(max_ack_pending) != self.max_ack_pending:
            raise RuntimeError(
                f"existing JetStream consumer {self.durable!r} has "
                f"max_ack_pending={max_ack_pending!r}; expected {self.max_ack_pending!r}"
            )

        filter_subject = getattr(config, "filter_subject", None)
        if filter_subject and self._worker_subject and filter_subject != self._worker_subject:
            raise RuntimeError(
                f"existing JetStream consumer {self.durable!r} has filter_subject="
                f"{filter_subject!r}; expected {self._worker_subject!r}"
            )

    async def _consume(self) -> None:
        assert self._subscription is not None
        while not self._stop.is_set():
            try:
                message = await self._subscription.next_msg(timeout=0.5)
            except Exception:
                if self._stop.is_set():
                    return
                continue
            if message is None:
                continue
            try:
                raw = json.loads(message.data.decode("utf-8"))
                job = JobEnvelope(**raw)
                delay = job.available_at - time.time()
                if delay > 0:
                    nak_with_delay = getattr(message, "nak_with_delay", None)
                    if nak_with_delay is not None:
                        await nak_with_delay(delay)
                    else:
                        await message.nak(delay=delay)
                    continue
                if self._handler is None:
                    await message.nak()
                    continue

                heartbeat_stop = asyncio.Event()

                async def heartbeat() -> None:
                    interval = max(2.0, min(self.ack_wait_seconds / 3.0, 15.0))
                    while not heartbeat_stop.is_set():
                        try:
                            await asyncio.wait_for(heartbeat_stop.wait(), timeout=interval)
                        except TimeoutError:
                            try:
                                await message.in_progress()
                                self._last_heartbeat_at = time.time()
                            except Exception:
                                return

                heartbeat_task = asyncio.create_task(heartbeat())
                try:
                    if inspect.iscoroutinefunction(self._handler):
                        await self._handler(job)
                    else:
                        await asyncio.to_thread(self._handler, job)
                finally:
                    heartbeat_stop.set()
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except asyncio.CancelledError:
                        pass
                await message.ack()
                self._processed += 1
                self._last_job_id = job.id
                self._last_error = None
                self._last_activity_at = time.time()
            except Exception as exc:
                self._failed += 1
                try:
                    self._last_job_id = job.id
                except Exception:
                    self._last_job_id = None
                self._last_error = str(exc)
                self._last_activity_at = time.time()
                # Redelivery is intentional: the JetStream consumer owns retry/redelivery policy.
                try:
                    await message.nak()
                except Exception:
                    pass

    def _thread_main(self) -> None:
        try:
            import nats
        except ImportError as exc:
            self._startup_error = RuntimeError("NATS backend requires the 'nats-py' extra")
            self._startup_error.__cause__ = exc
            self._ready.set()
            return
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect(nats))
            self._ready.set()
            self._loop.run_until_complete(self._wait_stop())
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
        finally:
            try:
                self._loop.run_until_complete(self._shutdown_async())
            finally:
                self._loop.close()

    async def _connect(self, nats_module: Any) -> None:
        kwargs: dict[str, Any] = {}
        if self.credentials:
            kwargs["user_credentials"] = self.credentials
        self._nc = await nats_module.connect(self.url, **kwargs)
        self._js = self._nc.jetstream()
        desired_subject = f"{self.subject_prefix}.>"
        try:
            await self._js.add_stream(
                name=self.stream,
                subjects=[desired_subject],
                retention=nats_module.js.api.RetentionPolicy.WORK_QUEUE,
                max_msgs=-1,
                allow_msg_schedules=True,
            )
        except Exception as exc:
            if "stream name already in use" not in str(exc).lower():
                raise
            info = await self._js.stream_info(self.stream)
            config = getattr(info, "config", None)
            subjects = list(getattr(config, "subjects", []) or [])
            retention = getattr(config, "retention", None)
            retention_value = getattr(retention, "value", retention)
            schedules_enabled = bool(getattr(config, "allow_msg_schedules", False))
            if (
                desired_subject not in subjects
                or retention_value not in {"workqueue", "work_queue", "WORK_QUEUE"}
                or not schedules_enabled
            ):
                raise RuntimeError(
                    f"existing JetStream stream {self.stream!r} is incompatible: "
                    f"subjects={subjects!r}, retention={retention_value!r}, "
                    f"allow_msg_schedules={schedules_enabled!r}; expected {desired_subject!r}/workqueue/schedules-enabled"
                )

    async def _wait_stop(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(0.1)

    async def _shutdown_async(self) -> None:
        if self._nc is not None:
            try:
                await self._nc.drain()
            except Exception:
                await self._nc.close()

    async def _consumer_info(self) -> dict[str, Any] | None:
        if self._js is None or not self._worker_subject:
            return None
        try:
            info = await self._js.consumer_info(self.stream, self.durable)
        except Exception:
            return None
        data = getattr(info, "__dict__", {}) or {}
        # Keep only stable operational fields; nested config/state remain available
        # when the client exposes them as objects.
        result: dict[str, Any] = {}
        for key in (
            "name",
            "stream_name",
            "created",
            "num_ack_pending",
            "num_redelivered",
            "num_waiting",
            "num_pending",
        ):
            if hasattr(info, key):
                value = getattr(info, key)
                if not isinstance(value, (str, int, float, bool, type(None))):
                    value = str(value)
                result[key] = value
        state = getattr(info, "delivered", None)
        if state is not None:
            result["delivered"] = getattr(state, "consumer_seq", None)
            result["stream_seq"] = getattr(state, "stream_seq", None)
        return result or data

    def status(self) -> JobBrokerStatus:
        connected = bool(self._nc is not None and getattr(self._nc, "is_connected", False))
        consumer = None
        if connected and self._loop and self._loop.is_running() and self._worker_subject:
            try:
                consumer = asyncio.run_coroutine_threadsafe(
                    self._consumer_info(), self._loop
                ).result(timeout=2.0)
            except Exception:
                consumer = None
        backlog = None
        if consumer:
            backlog = consumer.get("num_pending")
        return JobBrokerStatus(
            backend="nats",
            configured=True,
            connected=connected,
            worker_subject=self._worker_subject,
            processed=self._processed,
            failed=self._failed,
            last_job_id=self._last_job_id,
            last_error=self._startup_error.__class__.__name__ + ": " + str(self._startup_error)
            if self._startup_error
            else self._last_error,
            last_activity_at=self._last_activity_at,
            backlog_hint=backlog,
            worker_started_at=self._worker_started_at,
            last_heartbeat_at=self._last_heartbeat_at,
            consumer=consumer,
        )

    def close(self) -> None:
        self._stop.set()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(lambda: None)
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._loop = None
        self._nc = None
        self._js = None
        self._subscription = None
        self._handler = None
        self._worker_subject = None
