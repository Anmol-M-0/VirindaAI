# VirindaAI Release Roadmap — v0.27.0 Production Path

With the core application layer, universal `ask` LLM engine, and 174/174 automated tests complete, VirindaAI transitions from a feature-development phase to a **hardware validation, latency hardening, and acceptance-driven release process** for **v0.27.0**.

---

## 1. Release Milestones & Phase Gates

| Phase | Target Objective | Hard Release Gate |
| :--- | :--- | :--- |
| **v0.27.0-rc1** | Feature-Complete & Hardware Preflight | Real Linux microphone/speaker path reliable and instrumented; zero audio deadlocks; systemd units packaged. |
| **v0.27.0-rc2** | End-to-End Voice & Desktop Acceptance | Human can use VirindaAI naturally across sustained multi-turn sessions with race-free barge-in. |
| **v0.27.0 Final** | Production-Quality Release | Clean-machine install $\rightarrow$ configure $\rightarrow$ launch $\rightarrow$ upgrade works without manual intervention. |

---

## 2. Measurable Voice UX Gates

Voice assistants fail perceptually rather than functionally. These metrics are release-blocking on the golden reference hardware:

| Interaction Step / Metric | rc1 Target | Final v0.27.0 Target | Measurement Method |
| :--- | :--- | :--- | :--- |
| **Wake-Word Detection** | $\ge 95\%$ | $\ge 97\%$ | 100 intentional wake attempts at normal speaking distance |
| **False Activation Rate** | $\le 1.0/\text{hr}$ | $\le 0.5/\text{hr}$ | 60 min passive listening with desktop audio/noise |
| **STT Final Latency (p50)** | $\le 1.5\text{ s}$ | $\le 1.25\text{ s}$ | Speech end $\rightarrow$ usable transcript |
| **STT Final Latency (p95)** | $\le 3.0\text{ s}$ | $\le 2.5\text{ s}$ | Short/medium commands on standard network |
| **TTS First Audio (p50)** | $\le 500\text{ ms}$ | $\le 400\text{ ms}$ | Text available $\rightarrow$ audible speaker output |
| **TTS First Audio (p95)** | $\le 1.0\text{ s}$ | $\le 750\text{ ms}$ | First sentence playback start |
| **Barge-in Stop Latency (p50)** | $\le 250\text{ ms}$ | $\le 200\text{ ms}$ | User speech detected $\rightarrow$ playback cancelled/ducked |
| **Barge-in Stop Latency (p95)** | $\le 500\text{ ms}$ | $\le 400\text{ ms}$ | Microphone remains active, no stale playback |
| **Voice Pipeline Crashes** | $0$ | $0$ | 30-min continuous interaction run |
| **Audio Stream Deadlocks** | $0$ | $0$ | Repeated connect/disconnect/restart cycles |

---

## 3. Milestone Detailed Breakdown

### Milestone 1: v0.27.0-rc1 — Hardware Preflight & Instrumentation

**Objective**: Prove existing components operate reliably on real Linux audio hardware without mock-only assumptions.

- [x] **Universal Provider & Multi-Model Routing**: Groq LPU (`gpt-oss-120b`), NIM (`llama-3.3-70b`), OpenRouter, and ChatGPT Browser failover.
- [x] **Real-Time Voice Streaming**: `StreamingSentenceTokenizer` $\rightarrow$ bounded TTS worker $\rightarrow$ interruptible audio playback.
- [x] **Systemd User Units**: Templated `virindai.service` and `virindad.service` user units for `systemctl --user`.
- [x] **Persistence & Broker Boundaries**: SQLite WAL persistence (`~/.local/share/virinda-ai/virinda.sqlite3`) and in-process / NATS JetStream JobBroker.
- [ ] **End-to-End Correlation Timestamps**: Instrument `interaction_id` across `wake_detected`, `record_started`, `speech_ended`, `stt_final`, `llm_first_token`, `tts_first_audio`, `barge_in_detected`, and `playback_cancelled`.
- [ ] **Golden Hardware Audio Acquisition**: Verify 16-kHz mono capture and speaker output on PipeWire / ALSA across laptop mics, USB headsets, and Bluetooth devices.
- [ ] **Wake-Word Test Set**: Benchmark the `Hey Virinda` OpenWakeWord model against 100 intentional activations and background speech.

### Milestone 2: v0.27.0-rc2 — End-to-End Acceptance Scenarios

**Objective**: Validate real-world human interactions and desktop environment resilience.

- [ ] **Scenario A: Cold Start User Journey**: Clean installation $\rightarrow$ `.env` configuration $\rightarrow$ `virindad` launch $\rightarrow$ first query answered with zero terminal troubleshooting.
- [ ] **Scenario B: 5-Turn Continuous Conversation**: Consecutive speech interactions without accumulated latency, state drift, or duplicate job dispatch.
- [ ] **Scenario C: 30-Trial Barge-in Torture Test**: Interrupt assistant mid-sentence 30 consecutive times; verify immediate audio halt, clean generator exit, and new response generation.
- [ ] **Scenario D: 60-Minute Idle & Endurance Test**: Continuous passive listening without memory leaks, zombie worker threads, or stale socket descriptors.
- [ ] **Scenario E: Desktop Overlay & OVOS GUI**: Verify status visualization on `:8765` and OVOS MessageBus bridge without focus stealing.
- [ ] **Scenario F: Provider Failover & Network Resilience**: Verify graceful fallback from primary provider to secondary on network glitches without wedging the audio loop.

### Milestone 3: v0.27.0 Final — Production Packaging & Release

**Objective**: Ship-quality distribution with reproducible packaging and upgrade safety.

- [ ] **Clean-Machine Install Validation**: Verify installation via `uv sync` / wheel without local repository side-effects.
- [ ] **SQLite Migration Safety**: Verify database schema migrations preserve historical sessions, memory facts, and routine configurations across upgrades.
- [ ] **Systemd Lifecycle & Boot Startup**: `systemctl --user enable --now virindai.service` starts reliably after user login and auto-restarts on unexpected termination (`Restart=on-failure`).
- [ ] **Zero Known P0 Regressions**: Zero audio lockups, zero stuck playback, zero duplicate responses.

---

## 4. Product-First Scope Rules

To prevent scope creep and guarantee a timely, high-quality release:

1. **Rule 1 — User-Visible Value First**: If a change does not improve *Hear $\rightarrow$ Understand $\rightarrow$ Act $\rightarrow$ Respond*, it is deferred past v0.27.0.
2. **Rule 2 — Reliability Over Feature Count**: 10 capabilities that work every time beat 30 that occasionally fail.
3. **Rule 3 — Preserve Stable Architectural Boundaries**: Keep the clear separation between universal `ask`, Virinda runtime, JobBroker, SQLite persistence, and the OVOS MessageBus.
4. **Rule 4 — Streaming Is a Core UX Requirement**: The user must hear the response begin while tokens are still generating.
5. **Rule 5 — Cancellation Is Correctness**: Barge-in is not an optional enhancement; the assistant must stop immediately when interrupted.
6. **Rule 6 — Optimize p95, Not Demos**: Tail latency determines user trust.
7. **Rule 7 — One Golden Path**: Prioritize Linux + systemd + PipeWire + Groq/NIM + OVOS before expanding to exotic platforms.

---

## 5. Explicitly Deferred Capabilities (Post-v0.27.0)

The following items are intentionally deferred to post-v0.27.0 milestones:
- Complex multi-agent persona negotiation frameworks.
- Distributed multi-node worker clustering (NATS JetStream local single-node broker is standard for v0.27.0).
- Remote satellite hardware relays (HiveMind cross-device transport).
- Exotic OS and proprietary audio interface support.
- Speculative architectural refactors of stable components.

---

## 6. Completed Foundation Summary

- [x] Capability registry, risk classes, and local permission boundary.
- [x] Context modes: `normal`, `focus`, `private`, `quiet`.
- [x] Local Unix IPC discovery (`virinda.sock`) and JSON streaming.
- [x] Universal `ask` LLM engine integration (Groq LPU, NIM, OpenRouter, Browser ChatGPT).
- [x] SQLite WAL persistence (`~/.local/share/virinda-ai/virinda.sqlite3`).
- [x] In-process and NATS JetStream JobBroker implementations.
- [x] StreamingSentenceTokenizer and interruptible voice runtime.
- [x] Systemd user service configuration (`virindai.service`).
- [x] OVOS skill, GUI bridge, and doctor diagnostics (`skill-virinda-ai.openvoiceos`).
- [x] Diagnostic Web Overlay (`http://127.0.0.1:8765/`).
- [x] 174/174 unit and integration test suite passing.
