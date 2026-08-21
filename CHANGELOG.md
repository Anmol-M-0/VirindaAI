
### Next - v0.26.4-next14

- Ignore late controller signals and service response events after `VoiceTurnRuntime.close()`.
- Prevent post-shutdown TTS completion from reopening the follow-up window.
- Add idempotent-close and late-event regression coverage.
## Unreleased — v0.26.4-next9

- Fenced Virinda TTS output by `AssistantService` generation so queued or in-flight audio from a cancelled response is discarded before playback.
- Added a public `AssistantService.is_generation_current()` boundary for realtime workers instead of reaching into application internals.
- Added regression coverage for stale TTS synthesis after cancellation and fixed queue accounting under stale-item discard.

## Unreleased — v0.26.4-next8

- Fixed OVOS voice-event correlation for wake-triggered barge-in: `record.started` now preserves the wake-correlated turn instead of creating a second turn.
- Ignored duplicate/late wake events while an active turn already exists.
- Added regression coverage for wake → record correlation during active TTS and duplicate wake events.

## Unreleased

### P0 voice acceptance
- Capture the OVOS `ovos.listener.wakeword` signal as `wake.detected` so wake-to-record latency can be measured from a real listener event.
- Preserve the wake-correlated turn when `record.started` follows wake detection, while creating a new turn for a barge-in recording that begins during active TTS output.
- Enforce the 150 ms wake-to-record acceptance target in `voice-benchmark.py`.


- Hardened OVOS voice-event correlation so an asynchronous `audio.output.ended` event remains attached to the playback turn that started it, even if a new recording begins after barge-in.
- Added regression coverage for interrupted-turn playback completion correlation.

## 0.26.4-next4

- Fixed in-process cancellation so cancelling a queued idempotent job releases its idempotency key for a valid replacement/retry.
- Added regression coverage for cancellation followed by republish with the same idempotency key.

## Unreleased

- Hardened JetStream delayed-job identity: every scheduled job now receives a unique schedule-definition subject derived from its job ID, preventing same-target schedule collisions.
- Added `JobBroker.cancel(job_id)` to cancel queued local jobs and purge native JetStream schedules before delivery.
- Added regression coverage for schedule identity, cancellation headers, and in-process cancellation.

## 0.26.4-next2

### Changed

- Aligned the Rust `audio-core` generation-fencing API with Virinda's Python cancellation contract using explicit `current`, `start`, and `invalidate` operations.
- Kept `next()` as a deprecated compatibility alias for existing Rust callers.

### Tests

- Added Rust unit coverage for initial state, stale-generation invalidation, and concurrent generation updates.
- Python regression suite remains green; native Rust compilation is pending an environment with the Rust toolchain installed.

## 0.26.4-next

### Fixed

- Fixed NATS JetStream delayed-job scheduling to publish schedule definitions on a dedicated control subject instead of the delivery subject, matching NATS ADR-51 requirements.
- Added regression coverage for scheduled publish subject isolation.

## 0.26.3

### JobBroker correctness hardening

- Reject NATS jobs outside Virinda's configured stream subject namespace before publishing.
- Validate an existing durable JetStream consumer's delivery policy before accepting it, preventing stale `ack_wait`, `max_deliver`, `max_ack_pending`, or filter settings from silently changing runtime semantics.

### P0 voice acceptance hardening

- Made repository voice benchmark scripts runnable directly from a source checkout without requiring an installed wheel.
- Kept barge-in turns correlated through `audio.output.ended` so interruption measurements are not orphaned from their turn.

## 0.26.2

### P0 voice measurement

- Added a timestamp-only OVOS voice event capture utility for real Linux acceptance runs.
- Added p50/p95 voice latency analysis for captured turns.
- Expanded `VoiceBenchmark` to preserve missing stages instead of fabricating measurements.
- Added explicit documentation for the hardware voice acceptance workflow and privacy guarantees.

## 0.25.9

- Added JetStream consumer observability to broker health/status.
- Added stable consumer-info projection and redelivery diagnostics to the durability acceptance probe.

### NATS durability acceptance
- Switched the NATS JetStream worker from `pull_subscribe().fetch()` to single-message `next_msg()` consumption to avoid the known `nats-py 2.15.x` fetch-stall path.
- Added `scripts/nats-durability-acceptance.py` to verify durable redelivery after a simulated worker crash.
- Added regression coverage for the production consumer using `next_msg()`.
- Documented the supported NATS Server 2.14.x / `nats-py` 2.15.x compatibility target and live acceptance flow.

## 0.25.6

### Async job backbone
- Formalized `JobBroker` / `JobEnvelope` contracts.
- Added `InProcessJobBroker` for dependency-free local execution.
- Added `NatsJetStreamJobBroker` behind the optional `job-backbone` extra.
- Removed RabbitMQ as an architectural option; NATS JetStream is the only supported durable broker backend.
- Added NATS configuration and documentation.

## 0.25.1

- Made OVOS MessageBus + `ovos-gui` the production desktop/UI transport.
- Added `OVOSGuiBridge` for Virinda state publication and GUI command/response messages.
- Kept the HTTP overlay as a loopback-only developer/diagnostics surface.
- Added GUI bridge regression tests and documented the UI transport/security model.

## 0.25.0

- Added the local-first desktop routine editor and routine lifecycle API.
- Added routine list/preview/edit/disable/delete/run controls and recent-run inspection to the loopback overlay.
- Added regression coverage for the overlay HTTP/API contract.
- Kept automation execution behind the existing service, conflict, preview, and approval boundaries.

## 0.24.9

### Added
- Durable user profile/personalization store with explicit private-mode protection.
- Time-based routine scheduling plus event- and application-triggered automation.
- Multi-step routine actions, bounded retries, durable run history, and approval checkpoints.
- CLI/IPC controls for routine runs, events, and approval/resume flows.
- Regression tests for automation migration, retries, approval pauses, and event triggers.

### Changed
- User profile context is injected into provider requests only when explicitly configured.
- Default locale is no longer treated as personalized data, preventing hidden prompt noise.
- OVOS voice events are normalized into Virinda automation events instead of binding routines directly to bus topic names.

## 0.24.1

- Added a canonical documentation hub and abundant operator/developer documentation.
- Added configuration, CLI, installation, testing, troubleshooting, security-model, observability, glossary, contributor, and feature-matrix references.
- Added `scripts/check_docs.py` to validate Markdown headings, local links, environment-variable coverage, release-version consistency, and documentation hygiene.
- Added documentation validation to the standard development checks and CI.
- Added public-module/class docstrings for configuration, application coordination, features, and OVOS skill integration.
- Corrected README release metadata and removed generated packaging metadata from the source checkout.

## 0.24.0

- Improve natural-language memory search so token matches surface relevant facts and notes.
- Inject bounded durable memory context into normal-mode provider requests.
- Prevent memory context from entering private-mode provider requests.
- Make approval token storage thread-safe and ensure audit logs record effective approval.
- Add regression coverage for privacy and approval semantics.

## 0.22.0

- Hardened URL/network tools against SSRF and unsafe redirects.
- Added one-time, expiring approval tokens for consequential tools.
- Added replay/staleness validation to satellite envelopes.
- Restricted filesystem tool roots to Virinda data plus explicit `VIRINDA_TOOL_ROOTS`.
- Aligned the stable OVOS extra with GUI, PHAL, message bus, Alerts, diagnostics, camera, screenshot, volume and application-launcher components in the current stable constraints.

## 0.21.0

Feature-complete application layer for the roadmap. Adds durable memory and semantic ranking, alerts/notifications, routines, safe tools and audit logs, desktop overlay, voice profiles and benchmarking, proactive context, meeting mode, multimodal screen/camera hooks, OVOS GUI/Alerts/PHAL adapter boundaries, satellite transport primitives, provider management, and Virinda-specific OVOS intents.

## [0.19.0]

- Installer now provisions Virinda systemd units transactionally.
- Added safe uninstall script and first-boot provisioning wrapper.
- Preserved the Virinda virtualenv/database during uninstall by default.

# Changelog

## 0.18.0 — 2026-08-20

- Split OVOS smoke validation into bus/core/skill and optional service-gated stages.
- Added safe optional installation of OVOS user configuration without overwriting an existing config.
- Hardened user systemd units with deterministic Python environment settings.
- Added regression tests for service-gated smoke probing and config installation.

## 0.18.0

### Added

- Added a live `scripts/ovos-runtime-smoke.py` probe for the OVOS message-bus/core path without microphone hardware.
- Added explicit stable/local-voice installer profiles.
- Installer now installs Virinda’s OVOS skill into the user XDG skill directory.
- Fixed the skill dependency to the exact Virinda release instead of an impossible range.

### Fixed

- Removed the mismatch where the OVOS installer could provision the runtime but never install the Virinda skill.
- Kept the optional Whisper.cpp/phoonnx overlay out of the stable OVOS base install.

## 0.15.0

- Added an explicit OVOS reliability matrix: stable core, stable local fallback, separately validated Virinda add-ons, and experimental/legacy exclusions.
- Split the Python package extras so `ovos` means the stable stack while `ovos-local-voice` contains separately validated Whisper.cpp/phooNNX add-ons.
- Added `docs/OVOS_SUPPORTED_STACK.md` and machine-readable reliability policy.

# Changelog

## 0.13.0

- Added a checked-in snapshot of the current OVOS stable constraints.
- Split Virinda-selected voice add-ons from the OVOS stable dependency lock.
- Pinned stable Virinda audio add-ons: openWakeWord 0.4.1, Silero VAD 0.0.5, Whisper.cpp STT 0.0.1, and phoonnx 1.3.3.
- Added a machine-readable OVOS compatibility profile.
- Added `scripts/verify-ovos-compatibility.py` to prevent incompatible OVOS generations from being combined.
- Updated the installer to use the checked-in compatibility snapshot and add-on pins.

## 0.12.0

### OVOS compatibility hardening

- Added an explicit OVOS compatibility matrix based on the upstream stable constraints channel.
- Switched the production Persona profile back to the legacy `ovos-solver-openai-plugin` API because it is the compatible combination with the current stable Persona/OPM versions.
- Isolated the newer `ovos-chat-openai-plugin` agent configuration under `config/ovos/experimental-agent/`.
- Added compatibility tests preventing accidental mixing of legacy and agent-generation dependencies.
- Updated the installer/package extras to match the stable compatibility contract.
- Documented the rule: one OVOS release channel per environment; never assemble a production runtime from arbitrary latest repositories.


## 0.9.0 - 2026-08-20

- Align package and OVOS skill metadata to 0.9.0.
- Use the current OVOS Persona `solvers` configuration with `ovos-chat-openai-plugin`.
- Add a concrete local STT profile using `ovos-stt-plugin-whispercpp` and `base.en`.
- Add local voice profile, performance targets, and wake-model acceptance documentation.
- Add explicit OVOS user service templates for message bus, core, listener, and audio.
- Extend the OVOS doctor to validate the local STT plugin dependency.
- Add configuration tests for local STT and hybrid listening.


## 0.8.0

- Made OpenVoiceOS the recommended production voice runtime.
- Added `virinda.ovos` integration layer.
- Added deployable `skill-virinda-ai.openvoiceos` package with status/stop intents.
- Added OVOS Persona configuration using `ovos-openai-plugin`.
- Added Dinkum Listener / OpenWakeWord / Silero VAD configuration template.
- Added explicit custom `hey_virinda` model path instead of pretending a bundled model exists.
- Migrated TTS configuration guidance toward `ovos-tts-plugin-phoonnx` after the legacy Piper plugin was archived.
- Added `docs/OVOS.md` and `docs/REFERENCES.md`.
- Added validation tests for OVOS skill assets and config files.
- Corrected Virinda Persona configuration to the current handler/agent shape.
- Added `virinda doctor` for OVOS environment, persona, and wake-model diagnostics.
- Added additive SQLite migrations for pre-0.8 session schemas.
- Kept the standalone Virinda service as a compatibility runtime for non-OVOS environments.

## 0.6.0

- Added voice interaction state machine and runtime adapters.
- Added passive wake-word policy, VAD turn detection, follow-up listening, and barge-in semantics.

## 0.5.0

- Added streamed Unix-socket IPC.
- Added event-streaming daemon protocol.

## 0.4.0

- Added durable SQLite health checks and live backup.
- Added generation-fenced concurrent cancellation.

## 0.11.0 - 2026-08-20

- Added read-only Linux PipeWire/WirePlumber and ALSA audio diagnostics.
- Added `virinda doctor --audio` and JSON diagnostics for desktop provisioning.
- Aligned OVOS core/audio/listener/ALSA compatibility with the current stable 1.3.x/0.4.x channel targets.
- Enabled `instant_listen` in the example voice profile for lower wake-to-command latency.
- Made release tests derive skill version from the package version instead of hard-coding it.

## 0.15.0

- Split OVOS smoke verification into `stable` and `local-voice` profiles.
- Made `virinda doctor` determine selected STT/TTS plugin requirements from OVOS configuration.
- Removed duplicate OVOS dependency declarations from the packaging metadata.
- Kept Whisper.cpp and phoonnx explicitly classified as Virinda local-voice add-ons rather than upstream-stable requirements.
- Added release checks for the new compatibility profile behavior.

## 0.20.0

- Added `ContextMode` policies for normal, focus, private, and quiet operation.
- Added a typed capability registry with explicit risk classes.
- Added a permissioned tool broker for future browser, system, filesystem, and automation tools.
- Added IPC and CLI capability discovery plus context mode control.
- Added `docs/ROADMAP.md` covering voice, memory, tools, desktop UI, multimodal, proactive, and distributed features.
- Fixed OVOS systemd units to render the configured custom Virinda virtualenv path.

## 0.24.0

- Unified live session context across OVOS voice events, daemon IPC, and desktop overlay.
- Added canonical OVOS listener/audio lifecycle bridging for record start/end and audio output start/end.
- Added live context IPC endpoints for UI/runtime consumers.
- Meeting mode now consumes finalized OVOS utterances without duplicating ordinary conversation history.
- Stop events from the Virinda OVOS skill now flow through Virinda generation cancellation.
- Added regression coverage for the live session context bridge and canonical OVOS lifecycle topics.

## 0.26.1

### Fixed

- Keep the in-process job worker alive after individual handler failures.
- Allow failed jobs to be retried with the same idempotency key.
- Cancel delayed in-process jobs cleanly on broker close.
- Reject unhandled subjects instead of recycling them indefinitely.
- Synchronize NATS broker startup and worker subscription initialization.
- Validate pre-existing JetStream stream configuration before use.
- Use NATS 2.14+ server-side message scheduling for `JobEnvelope.available_at`.
- Preserve at-least-once delivery semantics with application-level idempotency.

### Documentation

- Consolidated the JobBroker roadmap milestone into one authoritative status.
- Documented at-least-once delivery and exactly-once non-goals.
- Documented native JetStream scheduling and restart semantics.
- Re-centered the roadmap on the unmet P0 voice acceptance gate.

## 0.26.3

- Added read-only Linux/OVOS/PipeWire voice preflight.
- Added enforceable p50/p95 P0 voice acceptance thresholds and minimum-turn checks.
- Added Markdown acceptance report generation from timestamp-only voice event logs.
- Updated voice acceptance documentation and roadmap.

## Unreleased – voice turn fencing

- Added generation fencing to the Python `VoiceTurnRuntime` so in-flight STT work from a cancelled or barge-in turn cannot submit stale text to `AssistantService`.
- Added regression coverage for cancellation while STT is blocked.
- Kept the generation lock non-blocking around the recognizer call so barge-in/cancel can invalidate an active STT worker immediately.

## Unreleased – voice timing hardening

- Aligned `VoiceInteractionController` listening-duration accounting with the audio timestamp supplied to `on_audio()`.
- Added deterministic max-utterance and follow-up timing regression coverage.
- Preserved monotonic-clock defaults for production callers that do not supply timestamps.


## Unreleased – TTS worker lifecycle isolation

- Made each TTS worker own its queue and response-completion state so a stopping worker cannot consume a later turn's queued audio.
- Preserved worker-local cancellation events across turns and kept stale-generation audio fenced before playback.
- Added regression coverage for starting a replacement TTS worker while the previous worker is still shutting down.
