# Architecture Decisions

## ADR-001: One application coordinator

**Decision:** `AssistantService` owns interaction orchestration.

**Reason:** parallel coordinators make cancellation, persistence, and lifecycle ordering non-deterministic.

## ADR-002: Protocol-based adapter boundaries

**Decision:** providers, persistence, cancellation, tokenization, and event sinks are expressed as Python protocols.

**Reason:** the core stays testable without vendor SDKs and alternate implementations do not leak into domain code.

## ADR-003: Generations instead of hard cancellation guarantees

**Decision:** treat cancellation as invalidation, not as a promise that every worker will stop immediately.

**Reason:** arbitrary providers and audio integrations may not be interruptible. Stale results can still be made harmless.

## ADR-004: SQLite for the local source of truth

**Decision:** use SQLite for session/message/event persistence.

**Reason:** it is local, transactional, dependency-light, inspectable, and resilient enough for a single-user desktop workload.

## ADR-005: Rust owns hard real-time audio

**Decision:** keep real-time audio outside Python orchestration.

**Reason:** callback code must have predictable latency and must not perform blocking or high-level application work.


### ADR-009: Fence final persistence by generation
- **Decision:** hold one short application lock across generation changes and final assistant-message persistence.
- **Why:** a provider can finish concurrently with cancel/new-request. A check performed before the write alone is racy.
- **Trade-off:** final commits serialize briefly, while network/provider streaming remains concurrent.

### ADR-010: Use SQLite backup API for live backups
- **Decision:** expose a store-level backup operation backed by `sqlite3.Connection.backup`.
- **Why:** copying an open WAL database at the filesystem level is easy to get wrong.
- **Trade-off:** backup is a little more explicit than a plain file copy, but correctness is worth the small API surface.

### ADR-011: Separate interactive OVOS messaging from durable Marina jobs
- **Decision:** keep OVOS MessageBus as the production interactive bus and introduce a `JobBroker` abstraction for durable/background work. Make NATS JetStream the only supported durable production backend; keep in-process as the default for tests/development.
- **Why:** voice/GUI traffic has latency and lifecycle semantics that differ from durable jobs, retries, long-running tools, and distributed workers.
- **Trade-off:** Marina has two messaging boundaries, but each has a narrow purpose and can be tested independently.
- **Non-goal:** do not route microphone, realtime audio, or normal GUI state through the job broker.
