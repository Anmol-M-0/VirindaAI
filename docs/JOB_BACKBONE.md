# Virinda Async Job Backbone

Virinda uses **OVOS MessageBus for interactive assistant communication** and a separate **JobBroker for durable/background work**.

The only planned durable broker backend is **NATS JetStream**. The default development/test backend is an in-process broker so Virinda remains usable without infrastructure.

NATS JetStream is appropriate for background work because the Python NATS client supports JetStream persistence, pull consumers, explicit acknowledgements, and durable consumers. The official NATS documentation describes JetStream as the persistence layer over NATS, while the Python client exposes JetStream APIs. [NATS documentation](https://docs.nats.io/) · [nats.py](https://github.com/nats-io/nats.py)

## Boundary

```text
                  Virinda
                     │
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
   OVOS MessageBus        JobBroker
          │                     │
   voice / GUI / core     async durable work
                                │
                         NATS JetStream
```

OVOS remains responsible for low-latency interaction: listener, intent handling, GUI, TTS, audio, skills, and session-carried messages. Virinda uses JobBroker for automation execution, long-running tools, integrations, notifications, retries, and distributed workers.

## Job contract

The application layer depends on the `JobBroker` protocol in `virinda.infrastructure.jobs`, never on a broker client directly. The protocol is intentionally small; delivery semantics live in the job envelope, persisted run state, and backend implementation.

```python
@dataclass(frozen=True, slots=True)
class JobEnvelope:
    subject: str
    payload: dict[str, Any]
    id: str
    idempotency_key: str | None
    session_id: str | None
    created_at: float
    available_at: float
```

The protocol exposes four operations:

- `publish(job)`
- `cancel(job_id)`
- `start_worker(subject, handler)`
- `close()`

`cancel(job_id)` is a backend-level cancellation primitive. For the in-process backend it removes a queued job and releases its idempotency key so a deliberate replacement can be published. For JetStream it removes the server-side schedule before delivery. For JetStream it removes the server-side schedule before delivery. Interactive features should use this primitive for user-requested cancellation rather than maintaining a second local timer registry.

### Delivery contract

Virinda promises **at-least-once delivery**, not exactly-once execution. A job may be delivered more than once after a worker crash or lost acknowledgement. Correctness therefore comes from persisted application-level idempotency (for example, the routine run ID) rather than a broker-level exactly-once claim. Ordering across independent subjects/workers is not guaranteed.

A terminal application state (`succeeded`, `failed`, `cancelled`, or equivalent) is authoritative. Redelivery of a run already recorded as `succeeded` is a no-op.

## Implementations

### InProcessJobBroker

The in-process implementation is the default for development, tests, and installations that do not require durable background workers. It provides bounded queueing, subject matching, delayed dispatch, retry-safe idempotency bookkeeping, and a worker that survives individual handler failures. Closing the broker cancels delayed local work. The in-process backend is intentionally non-durable across process restarts.

### NatsJetStreamJobBroker

The NATS implementation is the production path. It uses a durable JetStream work-queue stream and pull consumer with explicit acknowledgement. Failed handlers negatively acknowledge the message so JetStream can redeliver it according to the server-side consumer policy. Synchronous handlers run in a worker thread so they do not block the NATS event loop, and long-running jobs periodically send `in_progress` acknowledgements inside the configured acknowledgement window.

The stream must have message scheduling enabled. For `JobEnvelope.available_at` in the future, Virinda publishes using NATS native message scheduling (`Nats-Schedule` + `Nats-Schedule-Target`) rather than a client-side timer. This makes delayed jobs survive Virinda process restarts. Each delayed job gets a unique schedule-definition subject (`<prefix>.schedules.<job_id>`); schedule definitions are never shared by target subject, preventing collisions between multiple delayed jobs. NATS also supports schedule cancellation with `Nats-Scheduler` plus `Nats-Schedule-Next: purge`, which Virinda exposes through `JobBroker.cancel(job_id)`. citeturn230585search4turn230585search0

The cancellation control subject (`<prefix>.control.cancel`) is reserved for the JobBroker backend and is not a normal worker subject. Worker subscriptions should remain narrowly scoped to executable job subjects rather than `<prefix>.>`.

The configured subject prefix is enforced at publish time, so an application cannot accidentally publish a job outside the JetStream stream namespace. When a durable consumer already exists, Virinda also validates its acknowledgement window, maximum delivery count, maximum acknowledgement backlog, and filter subject against the configured worker policy. A stale consumer configuration is rejected rather than silently reused.

NATS is optional at install time through the `job-backbone` extra:

```bash
pip install -e '.[job-backbone]'
```

The client dependency is intentionally isolated from the core package. `nats-py` 2.15.x is imported lazily, so the base Virinda runtime remains dependency-free.

## Subjects

The default subject namespace is:

```text
virinda.jobs.>
```

Recommended subjects include:

```text
virinda.jobs.automation.execute
virinda.jobs.tool.execute
virinda.jobs.integration.execute
virinda.jobs.notification.send
```

## Idempotency

Every consequential background job should carry a stable application-level idempotency key, and the payload should carry the durable application run ID when the job represents a routine execution. A retry must not duplicate a destructive action merely because the broker redelivered a message. JetStream's publisher-side message ID is intentionally the unique job ID; application idempotency is stronger and persists beyond the broker duplicate window.

## NATS compatibility target

Virinda targets **NATS Server 2.14.x with JetStream enabled** and the **`nats-py` 2.15.x** Python client line. The server and client are separate version domains: JetStream is a capability of the NATS Server, while `nats-py` is Virinda's client library. The supported target should be treated as a tested compatibility pair rather than a generic “latest NATS” claim.

The repository acceptance probe deliberately avoids `fetch()` because the current `nats-py` 2.15.0 issue tracker documents an intermittent low-traffic pull-consumer stall in that API path. Virinda uses the pull consumer's single-message `next_msg()` acceptance path instead, while the production worker remains covered by explicit acknowledgement, in-progress heartbeat, and redelivery tests.

At release time, verify the live server version with `nats-server -v` and run both `python scripts/nats-acceptance.py` and `python scripts/nats-durability-acceptance.py` against the provisioned JetStream instance.

## Security

A NATS server crossing a host boundary must use TLS and scoped credentials. Worker permissions should be limited to the subjects required by that worker. Job payloads must contain references/arguments, not secrets that could otherwise be copied into logs or dead-letter stores.

The OVOS MessageBus and NATS JetStream are separate trust domains. The OVOS bus remains a local interaction boundary; NATS is the durable worker boundary.

## Operational policy

For a normal desktop installation:

```text
OVOS MessageBus + in-process JobBroker
```

For a production/distributed Virinda installation:

```text
OVOS MessageBus + NATS JetStream
```

Virinda does not support or document a second message broker backend. Keeping one durable broker path prevents competing delivery/ack/retry semantics and keeps operational documentation focused.

## Migration sequence

1. Keep `InProcessJobBroker` as the test/default implementation.
2. Automation, scheduled routines, event-triggered routines, and long-running execution publish through `JobBroker`.
3. Use `NatsJetStreamJobBroker` for production durable execution; the in-process backend remains the default local/test path.
4. Run `python scripts/nats-acceptance.py` against the provisioned broker before enabling durable automation.
5. Add broker health/readiness to `virinda doctor`.
6. Run the live connectivity and crash/recovery acceptance scripts against a real NATS JetStream server.

## References

- https://docs.nats.io/
- https://github.com/nats-io/nats.py


### Automation execution flow

Routine triggers do not execute tool actions directly inside the assistant request path. They publish a `virinda.jobs.automation.execute` job containing the routine ID, trigger context, session ID, and execution ID. The selected `JobBroker` worker invokes the existing `RoutineRunner`, which owns retries, approval checkpoints, execution logging, and side effects.

This keeps OVOS interaction latency separate from background automation work while preserving deterministic in-process behavior for local development and tests.

## Restart and redelivery guarantees

Routine execution is idempotent at the persisted run boundary. If a worker performs the side effect, persists `succeeded`, and dies before acknowledging the NATS message, JetStream redelivery reuses the same run ID and the terminal `succeeded` state is treated as a no-op. Pending approvals are persisted and can be resumed after Virinda restarts using the original run ID. A queued/running job remains owned by JetStream until acknowledged; the local in-process broker is intentionally non-durable.

## Broker observability

When the NATS backend is connected, Virinda reports a bounded JetStream consumer snapshot in `virinda status`: pending messages, acknowledgement-pending messages, redelivery count, waiting consumers, and delivered sequence numbers. The snapshot is advisory and may be temporarily unavailable during reconnects; job correctness never depends on it.

`virinda status` should be used for dashboards and diagnosis, while `scripts/nats-durability-acceptance.py` remains the authoritative live acceptance check.
