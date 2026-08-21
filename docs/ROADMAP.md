# MarinaAI Roadmap — Feature-Complete Application Layer

The original roadmap is now implemented at the application/adapter level. Remaining work is primarily hardware/runtime acceptance, model evaluation, and UX refinement on a real Linux desktop.

## Completed

- [x] Capability registry, risk classes, permission boundary
- [x] Context modes: normal, focus, private, quiet
- [x] Local Unix IPC discovery and streaming
- [x] Custom-venv OVOS deployment + systemd lifecycle
- [x] OVOS compatibility matrix and staged runtime smoke tests
- [x] Production OVOS GUI message-bus integration
- [x] Messaging boundary decision: OVOS MessageBus for interaction, JobBroker for durable work
- [x] Desktop loopback diagnostics overlay (non-production)
- [x] Voice profiles
- [x] Wake-word evaluation metrics
- [x] Voice latency benchmark storage
- [x] Audio device discovery/selection
- [x] Speaker-identification adapter (local centroid baseline)
- [x] Explicit memory facts and notes
- [x] Optional deterministic local semantic ranking
- [x] Memory inspection/edit/delete
- [x] Private-mode persistence policy
- [x] Alerts, timers/reminders scheduler, notifications inbox
- [x] OVOS Alerts notification adapter
- [x] Read-only system tools
- [x] Safe filesystem tools restricted to approved roots
- [x] Browser open/fetch/search tools with approval boundary
- [x] Desktop application launcher
- [x] Clipboard tools
- [x] Screenshot capture
- [x] Optional camera capture
- [x] Tool execution audit log
- [x] User-defined safe routines/automations
- [x] Confirmation policy by risk class
- [x] Desktop context signals
- [x] Proactive rules and briefing
- [x] Meeting/transcription mode
- [x] OVOS GUI adapter
- [x] OVOS PHAL-compatible adapter boundary
- [x] Multimodal image input and OpenAI-compatible vision adapter
- [x] Satellite envelope + OVOS bus adapter
- [x] HMAC-authenticated transport primitive for remote/satellite integration
- [x] Marina-specific OVOS voice control intents

## Live validation still required

- [ ] Real `Hey Marina` model false-positive/false-negative benchmark on representative audio
- [ ] End-to-end microphone → wake → VAD → STT → LLM → TTS acceptance run on target Linux hardware
- [ ] PipeWire/ALSA automatic-device selection tuning
- [ ] Barge-in latency measurement on target hardware
- [ ] Speaker-identification accuracy/security evaluation
- [ ] Real OVOS GUI client acceptance test
- [ ] Real `ovos-skill-alerts` integration acceptance test
- [ ] Real PHAL/hardware action acceptance test
- [ ] Real multi-device/HiveMind transport acceptance test

## Product direction after hardware validation

The next iterations should focus on:

1. latency optimization;
2. wake-word model quality;
3. desktop interaction polish;
4. memory quality and user trust controls;
5. safe tool confirmations;
6. hardware and multi-device reliability.

## Async execution milestone

The async-work architecture is implemented. Remaining work is live infrastructure acceptance only.

- [x] Define JobBroker / JobEnvelope / retry / idempotency contracts.
- [x] Implement in-process JobBroker as the test/development backend.
- [x] Move automation and long-running execution behind JobBroker.
- [x] Add NATS JetStream backend.
- [x] Add broker health/recovery diagnostics and stale-run reconciliation.
- [x] Add crash/redelivery idempotency handling.
- [x] Use native NATS 2.14+ message scheduling for durable delayed jobs.
- [ ] Run distributed worker acceptance tests against a provisioned NATS environment.
- [ ] Run NATS JetStream 2.14.x crash/restart acceptance checks on a provisioned host.
- [ ] Validate production worker deployment, TLS, credentials, permissions, and recovery runbooks.

## Product-first reset (0.26+)

The roadmap is now explicitly ordered by user-visible value:

### P0 — Voice experience

- [ ] Provision a target Linux desktop with the supported OVOS stack.
- [ ] Validate a real `Hey Marina` model with representative noise.
- [x] Add hardware-independent OVOS event capture + p50/p95 benchmark harness.
- [x] Add Linux/OVOS/PipeWire preflight and enforceable P0 benchmark thresholds.
- [ ] Measure wake → STT → first token → first audio → barge-in p50/p95 on target hardware.
- [ ] Tune PipeWire/ALSA device selection.
- [ ] Validate continuous follow-up conversation on target hardware.
- [ ] Validate private-mode behavior end-to-end on real hardware.

### P1 — Personal assistant quality

- [x] Persistent profile and memory primitives.
- [x] Natural reminder/routine commands.
- [x] Personalized briefing primitives.
- [ ] Improve semantic memory relevance evaluation.
- [ ] User-facing memory management UI.
- [ ] Routine conflict/execution UX refinement.

### P2 — Desktop assistant quality

- [x] OVOS GUI message-bus bridge.
- [x] Local routine editor prototype.
- [ ] Native OVOS GUI client acceptance test.
- [ ] Approval dialogs and live tool progress in the native GUI.
- [ ] Desktop context quality evaluation.

### P3 — Async work platform

- [x] JobBroker abstraction.
- [x] In-process backend.
- [x] NATS JetStream backend.
- [x] Automation execution migration to JobBroker.
- [x] Idempotent redelivery/recovery primitives.
- [x] Broker health/recovery diagnostics.
- [ ] Live NATS 2.14.x crash/restart acceptance run.
- [ ] Durable worker deployment/operations validation.

### P4 — Distributed and multimodal

- [x] Multimodal input boundaries.
- [x] Satellite transport primitive.
- [ ] Real HiveMind/multi-device acceptance.
- [ ] Screen/camera quality evaluation on real hardware.
- [ ] Optional distributed workers after P0/P1 reliability targets are met.

## Current priority gate

After the JobBroker correctness work is complete, new infrastructure feature work is paused. The next implementation work should advance the unmet P0 voice gate: real Linux OVOS deployment, wake-word evaluation, end-to-end audio latency, barge-in, and native OVOS GUI acceptance. The repository now provides the timestamp-only capture/benchmark harness, Linux/OVOS/PipeWire preflight, and an enforceable acceptance report; live hardware remains the acceptance boundary. P3/P4 changes should only resume when they directly unblock those acceptance goals or are required for production reliability.

## Product rule

Do not advance P3/P4 infrastructure work at the expense of an unmet P0 voice acceptance gate unless the infrastructure change is itself required to unblock P0.
