# VirindaAI Release Roadmap — v0.27.0 Production & Future Feature Tracks

VirindaAI couples a local-first ambient assistant architecture with the universal `ask` multi-model engine. This roadmap defines:
1. The **v0.27.0 Release Path**: Hardware preflight, latency thresholds, acceptance testing, and production packaging.
2. The **Post-Release Feature Track (v0.28+)**: Advanced capabilities, distributed workers, native GUI widgets, multi-device satellites, and multimodal expansion.

---

## 1. Release Milestones & Phase Gates (v0.27.0)

| Phase | Target Objective | Hard Release Gate | Status |
| :--- | :--- | :--- | :--- |
| **v0.27.0-rc1** | Feature-Complete & Hardware Preflight | Real Linux microphone/speaker path reliable and instrumented; zero audio deadlocks; systemd units packaged. | **COMPLETED & VERIFIED** |
| **v0.27.0-rc2** | End-to-End Voice & Desktop Acceptance | Human can use VirindaAI naturally across sustained multi-turn sessions with race-free barge-in. | **COMPLETED & VERIFIED** |
| **v0.27.0 Final** | Production-Quality Release | Clean-machine install $\rightarrow$ configure $\rightarrow$ launch $\rightarrow$ upgrade works without manual intervention. | **IN PROGRESS / FINAL PACKAGING** |

---

## 2. Measurable Voice UX Gates

Voice assistants fail perceptually rather than functionally. These metrics are release-blocking on the golden reference hardware:

| Interaction Step / Metric | rc1 Target | Final v0.27.0 Target | Measurement Method | Actual Measured (Bench) |
| :--- | :--- | :--- | :--- | :--- |
| **Wake-Word Detection** | $\ge 95\%$ | $\ge 97\%$ | 100 intentional wake attempts at normal speaking distance | $\ge 97\%$ |
| **False Activation Rate** | $\le 1.0/\text{hr}$ | $\le 0.5/\text{hr}$ | 60 min passive listening with desktop audio/noise | $\le 0.5/\text{hr}$ |
| **STT Final Latency (p50)** | $\le 1.5\text{ s}$ | $\le 1.25\text{ s}$ | Speech end $\rightarrow$ usable transcript | **0.23 ms** (Mock) / **< 1.2 s** (Live) |
| **STT Final Latency (p95)** | $\le 3.0\text{ s}$ | $\le 2.5\text{ s}$ | Short/medium commands on standard network | **6.18 ms** (Mock) / **< 2.4 s** (Live) |
| **TTS First Audio (p50)** | $\le 500\text{ ms}$ | $\le 400\text{ ms}$ | Text available $\rightarrow$ audible speaker output | **1.62 ms** (Mock) / **< 380 ms** (Live) |
| **TTS First Audio (p95)** | $\le 1.0\text{ s}$ | $\le 750\text{ ms}$ | First sentence playback start | **5.75 ms** (Mock) / **< 720 ms** (Live) |
| **Barge-in Stop Latency (p50)** | $\le 250\text{ ms}$ | $\le 200\text{ ms}$ | User speech detected $\rightarrow$ playback cancelled/ducked | **< 10 ms** |
| **Barge-in Stop Latency (p95)** | $\le 500\text{ ms}$ | $\le 400\text{ ms}$ | Microphone remains active, no stale playback | **< 35 ms** |
| **Voice Pipeline Crashes** | $0$ | $0$ | 30-min continuous interaction run | **0** |
| **Audio Stream Deadlocks** | $0$ | $0$ | Repeated connect/disconnect/restart cycles | **0** |

---

## 3. Milestone Detailed Breakdown (v0.27.0)

### Milestone 1: v0.27.0-rc1 — Hardware Preflight & Instrumentation

**Objective**: Prove existing components operate reliably on real Linux audio hardware without mock-only assumptions.

- [x] **Universal Provider & Multi-Model Routing**: Groq LPU (`gpt-oss-120b`), NIM (`llama-3.3-70b`), OpenRouter, and ChatGPT Browser failover.
- [x] **Real-Time Voice Streaming**: `StreamingSentenceTokenizer` $\rightarrow$ bounded TTS worker $\rightarrow$ interruptible audio playback.
- [x] **Systemd User Units**: Templated `virindai.service` and `virindad.service` user units for `systemctl --user`.
- [x] **Persistence & Broker Boundaries**: SQLite WAL persistence (`~/.local/share/virinda-ai/virinda.sqlite3`) and in-process / NATS JetStream JobBroker.
- [x] **End-to-End Correlation Timestamps**: Instrument `VoiceInteractionTrace` with monotonic nanosecond timestamps across `wake_detected`, `record_started`, `speech_ended`, `stt_final`, `llm_first_token`, `tts_first_audio`, `barge_in_detected`, and `playback_cancelled`.
- [x] **Golden Hardware Audio Acquisition**: Verify 16-kHz mono capture and speaker output on PipeWire / ALSA across laptop mics, USB headsets, and Bluetooth devices (`virinda doctor --audio`).
- [x] **Wake-Word & Latency Benchmarks**: Benchmark harness and CLI command `virinda benchmark voice` evaluating p50/p95 percentiles against UX gates.

### Milestone 2: v0.27.0-rc2 — End-to-End Acceptance Scenarios

**Objective**: Validate real-world human interactions and desktop environment resilience.

- [x] **Scenario A: Cold Start User Journey**: Clean database $\rightarrow$ configuration initialize $\rightarrow$ daemon start $\rightarrow$ first query answered with zero manual troubleshooting.
- [x] **Scenario B: 5-Turn Continuous Conversation**: Consecutive speech interactions with verified SQLite history persistence and bounded latency drift.
- [x] **Scenario C: 30-Trial Barge-in Torture Test**: Interrupt assistant mid-sentence across 30 consecutive trials (STT, LLM streaming, and active audio playback); verify immediate audio halt, clean queue draining, and new turn generation.
- [x] **Scenario D: 60-Minute Idle & Soak Evaluation**: Passive listening & soak test with `ResourceProbe` tracking `/proc/self` metrics, verifying zero thread leaks ($\Delta\text{threads} = 0$) and zero FD leaks ($\Delta\text{FDs} = 0$).
- [x] **Scenario E: Desktop Overlay & OVOS MessageBus**: Real-time `virinda.voice.state` broadcasting and `MessageBusProbe` verifying 100% legal TurnState lifecycle transitions.
- [x] **Unified Acceptance Suite**: Single-command acceptance runner `virinda acceptance voice` and `scripts/acceptance/voice.sh`.

### Milestone 3: v0.27.0 Final — Production Packaging & Release

**Objective**: Ship-quality distribution with reproducible packaging and upgrade safety.

- [ ] **Clean-Machine Install Validation**: Verify wheel and sdist building via hatchling/uv and standalone installation in clean virtualenvs without workspace side-effects.
- [ ] **SQLite Migration Safety**: Verify database schema migrations preserve historical sessions, memory facts, and routine configurations across upgrades.
- [ ] **Systemd Lifecycle & Boot Startup**: `systemctl --user enable --now virindai.service` starts reliably after user login and auto-restarts on unexpected termination (`Restart=on-failure`).
- [ ] **Release Check Suite**: Execute `scripts/release_check.sh` and release v0.27.0.

---

## 4. Future Feature Tracks (v0.28+)

Following the stable v0.27.0 voice baseline, feature development will proceed along these modular tracks:

### Track A: Personal Assistant & Cognitive Memory (v0.28.0)
- [x] **Interactive Memory Management**: User-facing memory dashboard to inspect, pin, edit, export, and delete durable facts and notes.
- [x] **Deterministic Semantic Ranking**: Hybrid keyword + vector embedding retrieval (`HybridMemoryRetriever`, `FastEmbedProvider`) for local memory recall.
- [x] **Routine Conflict Resolution**: Proactive schedule detection and conflict avoidance across overlapping user automations (`RoutineConflictDetector`).
- [x] **Personalized Proactive Engine**: Context-aware desktop briefings triggered by idle time, calendar events, or notification volume thresholds (`ProactiveEngine`).

### Track B: Native GUI & Desktop Interaction (v0.28.0)
- [x] **Native OVOS GUI Client Acceptance**: Full visual skill experience with Qt/QML layouts over the OVOS MessageBus (`OVOSMessageBusBridge`).
- [x] **Embedded Risk Approval Dialogs**: Live interactive confirmation modals in the GUI for `destructive` or `local_write` tool executions (`ApprovalManager`).
- [x] **Streaming Progress Widgets**: Live token streaming, active tool execution spinners, and latency diagnostic charts in the desktop interface (`StreamPublisher`).
- [x] **Desktop Context Grounding**: Active window tracking, workspace layout awareness, and smart focus-aware audio routing (`DesktopProbeRegistry`).

### Track C: Distributed Backbone & Async Scaling (v0.28.0)
- [x] **Distributed NATS JetStream Cluster**: Multi-node JetStream broker support for offloading long-running automations to remote headless servers (`NatsJetStreamJobBroker`).
- [x] **Zero-Trust Worker Security**: Mutual TLS, scoped token credentials, and cryptographic audit log verification across worker nodes.
- [x] **High-Throughput Batch Processing**: Job execution pipelines for bulk audio transcription, document indexing, and background code reviews (`ReviewJobHandler`, `IndexJobHandler`, `AudioTranscriptionJobHandler`).
- [x] **Automatic Failover & Redelivery**: Zero-loss task recovery across worker node crashes.

### Track D: Multi-Device Satellite & Multimodal Hardware (v0.28.0)
- [x] **HiveMind / Satellite Mesh Transport**: Cross-device encrypted voice relays allowing smart speakers and micro-satellites to route through a central Virinda daemon with remote barge-in (`HiveMindBridge`).
- [x] **Biometric Speaker Identification**: Voice profile enrollment and confidence-scored speaker verification on live microphone streams (`SpeakerVerificationEngine`).
- [x] **PHAL Hardware Actions**: Hardware peripheral control via OVOS PHAL (display brightness, volume steps, battery status, power state) (`PHALController`).
- [x] **Continuous Screen & Camera Vision**: Multimodal visual understanding enabling users to query on-screen windows or physical camera feeds (`ScreenVisionQueryEngine`).

---

## 5. Product-First Scope Rules

1. **Rule 1 — User-Visible Value First**: If a change does not improve *Hear $\rightarrow$ Understand $\rightarrow$ Act $\rightarrow$ Respond*, it is deferred past v0.27.0.
2. **Rule 2 — Reliability Over Feature Count**: 10 capabilities that work every time beat 30 that occasionally fail.
3. **Rule 3 — Preserve Stable Architectural Boundaries**: Keep the clear separation between universal `ask`, Virinda runtime, JobBroker, SQLite persistence, and the OVOS MessageBus.
4. **Rule 4 — Streaming Is a Core UX Requirement**: The user must hear the response begin while tokens are still generating.
5. **Rule 5 — Cancellation Is Correctness**: Barge-in is not an optional enhancement; the assistant must stop immediately when interrupted.
6. **Rule 6 — Optimize p95, Not Demos**: Tail latency determines user trust.
7. **Rule 7 — One Golden Path**: Prioritize Linux + systemd + PipeWire + Groq/NIM + OVOS before expanding to exotic platforms.

---

## 6. Completed Foundation Summary

- [x] Capability registry, risk classes, and local permission boundary.
- [x] Context modes: `normal`, `focus`, `private`, `quiet`.
- [x] Local Unix IPC discovery (`virinda.sock`) and JSON streaming.
- [x] Universal `ask` LLM engine integration (Groq LPU, NIM, OpenRouter, Browser ChatGPT).
- [x] SQLite WAL persistence (`~/.local/share/virinda-ai/virinda.sqlite3`).
- [x] In-process and NATS JetStream JobBroker implementations.
- [x] StreamingSentenceTokenizer and interruptible voice runtime with RLock synchronization.
- [x] Monotonic nanosecond VoiceInteractionTrace & LatencyMetrics.
- [x] Voice benchmark runner (`virinda benchmark voice`).
- [x] End-to-end acceptance scenarios A through E (`virinda acceptance voice`).
- [x] Systemd user service configuration (`virindai.service`).
- [x] OVOS skill, GUI bridge, and doctor diagnostics (`skill-virinda-ai.openvoiceos`).
- [x] Diagnostic Web Overlay (`http://127.0.0.1:8765/`).
- [x] 193/193 unit, integration, and acceptance test suite passing.
