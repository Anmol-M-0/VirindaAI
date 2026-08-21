# Virinda Voice Acceptance

This document defines the P0 hardware-validation workflow for Virinda's voice experience.

Virinda does **not** replace the OVOS listener. Dinkum Listener already owns microphone input, wake word, VAD and STT, and publishes the resulting lifecycle through the OVOS MessageBus. urlDinkum Listenerhttps://github.com/OpenVoiceOS/ovos-dinkum-listener

## 1. Capture real OVOS events

On a provisioned Linux desktop running the Virinda OVOS profile:

```bash
python scripts/voice-event-capture.py --duration 180 --output voice-events.jsonl
```

The collector connects to the local OVOS MessageBus using `ovos-bus-client`. That client intentionally requires a local/private bus and exposes `run_in_thread()` plus `connected_event` for synchronization. urlovos-bus-clienthttps://github.com/OpenVoiceOS/ovos-bus-client

The collector records timestamps only. It does **not** save PCM audio or transcripts.

## 2. Compute latency statistics

```bash
python scripts/voice-benchmark.py voice-events.jsonl
python scripts/voice-benchmark.py voice-events.jsonl --json
```

The report contains p50/p95 for the stages that are observable from the captured events.

Current normalized events:

```text
record.started
record.ended
stt.completed
audio.output.started
audio.output.ended
barge_in.requested
```

An event such as `wake.detected` or `llm.first_token` may be supplied by a future deeper integration, but Virinda deliberately does not fabricate those measurements when the underlying OVOS service does not expose them.

## 3. P0 acceptance targets

Targets are engineering goals, not guarantees:

| Stage | Target |
|---|---:|
| wake → recording | < 150 ms |
| record end → STT | < 1.0 s for short utterances |
| STT → first model token | < 1.5 s for a local model |
| first sentence → first TTS audio | < 1.0 s |
| barge-in → playback stopped | < 250 ms |
| total turn | measure p50 and p95; optimize regressions, not only the mean |

A release cannot claim the P0 voice gate is complete from synthetic tests alone.

## 4. Wake-word quality

A separate test set must measure:

- false accepts per hour of representative background audio;
- false rejects across multiple speakers;
- performance while Virinda is speaking;
- performance with keyboard/music/room noise;
- performance after device sleep/wake;
- cold-start and warm-start behavior.

The dedicated `hey_virinda` model is required for production. Do not silently substitute another wake phrase.

## 5. Barge-in

During TTS playback:

1. user speaks or presses the configured interruption control;
2. OVOS/Virinda stops playback;
3. the current assistant generation is cancelled;
4. the listener returns to capture;
5. no stale response may resume playback.

The capture utility records the playback-start turn separately from the current
recording turn, so an asynchronous `audio.output.ended` remains attached to the
interrupted response even when a new recording begins immediately after barge-in.
This is a playback-stop proxy;
a target-hardware run should additionally verify the physical stop point if the
installed audio backend exposes a more precise event.

This must be measured on the target hardware.

## 6. Privacy acceptance

A production pass requires confirmation that:

- pre-wake audio is only held in bounded memory buffers;
- diagnostic recordings are disabled by default;
- private mode does not persist transcripts or durable memory;
- network STT/LLM providers are explicitly configured;
- local microphone state is visible to the user.

## 7. Recommended test matrix

Run at least 30 turns per hardware profile and report p50/p95. Repeat with:

- quiet room;
- normal conversation/background noise;
- music playing;
- keyboard/desk noise;
- Virinda speaking while the user interrupts;
- follow-up conversation without repeating the wake word.

The authoritative voice gate remains the P0 product gate; this harness only supplies the measurements required to make that gate objective.

## 8. Preflight and release decision

Run the read-only Linux host preflight before collecting voice events:

```bash
python scripts/voice-preflight.py
python scripts/voice-preflight.py --json > voice-preflight.json
```

The preflight verifies that Linux, OVOS bus/core/listener modules, PipeWire/WirePlumber inspection, and ALSA capture/playback inspection are available. It never changes routing and never records microphone data.

For a release-quality hardware run, collect at least 30 turns and enforce the P0 latency targets:

```bash
python scripts/voice-benchmark.py voice-events.jsonl \
  --fail-on-targets \
  --min-turns 30 \
  --markdown > voice-acceptance.md
```

A P0 latency acceptance run fails when the required sample count is not met or when an observed p95 latency exceeds the target. Missing observability stages are also treated as a failure unless `--allow-incomplete` is explicitly used for exploratory diagnostics.

This benchmark is intentionally stricter than the ordinary diagnostic report: a diagnostic run may be partial, while a release acceptance run must be complete enough to make a pass/fail decision.
