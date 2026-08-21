# VirindaAI 0.26.2 Release

## Highlights

### Voice benchmark harness

- Added `scripts/voice-event-capture.py` to passively capture normalized OVOS voice lifecycle timestamps.
- Added `scripts/voice-benchmark.py` to report p50/p95 stage latency.
- No PCM audio or transcripts are persisted by the capture utility.


This release is a correctness hardening pass over the JobBroker implementation derived from v0.26.0.

- In-process workers survive individual handler failures.
- Failed jobs can be retried with the same idempotency key.
- Delayed local jobs are cancelled cleanly on shutdown.
- Subject mismatches fail fast instead of starving the worker queue.
- NATS startup/subscription initialization is synchronized.
- Existing JetStream streams are validated before Virinda accepts them.
- `available_at` uses native NATS 2.14+ message scheduling, so delayed jobs survive Virinda process restarts.
- Delivery is explicitly documented as at-least-once with application-level idempotency, not exactly-once.
- The roadmap now has one authoritative async milestone and explicitly returns priority to the P0 voice experience after JobBroker correctness work.

## Validation

- Full test suite: passing
- Documentation validation: passing
- OVOS compatibility validation: passing
- Product-direction guard: passing
- Release metadata validation: passing
- Python compilation: passing
- Wheel build: passing
- Source archive hygiene: passing

## Live validation still required

A real NATS Server 2.14.x + JetStream environment is still required to validate broker connectivity, crash/restart redelivery, and TLS/credential deployment. The target Linux OVOS voice acceptance path remains the next product milestone.

## 0.26.3

This release strengthens the P0 voice acceptance workflow. Run `scripts/voice-preflight.py` before a hardware benchmark, then use `scripts/voice-benchmark.py --fail-on-targets --min-turns 30 --markdown` to produce a release-oriented pass/fail report. No raw microphone audio is persisted by these tools.

## 0.26.4-next4

- Fix in-process `JobBroker.cancel(job_id)` to release an idempotency key belonging to a cancelled queued job.
- Add regression coverage for cancel-then-republish semantics.

## 0.26.4-next3

- Give every native JetStream delayed job a unique schedule-definition subject derived from its job ID.
- Add `JobBroker.cancel(job_id)` for queued local cancellation and native JetStream schedule purge.
- Add regression coverage for schedule identity and cancellation semantics.
- Full repository checks remain green; live NATS validation and Rust compilation remain environment-dependent.
