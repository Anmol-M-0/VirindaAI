# Voice performance targets

The goal is a responsive ambient assistant, not merely a functional voice pipeline. Real hardware claims require the live OVOS event capture harness described in `docs/VOICE_ACCEPTANCE.md`.

## Target budget

These are engineering targets for a desktop-class machine, not guarantees:

| Stage | Target |
| --- | ---: |
| wake detection after model window | < 300 ms |
| wake → listening indicator | < 150 ms |
| end-of-speech → STT result | < 1.0 s for short utterances |
| STT → first LLM response token | < 1.5 s local |
| first response sentence → first TTS audio | < 1.0 s |
| barge-in → stopped audio | < 250 ms |

Measure each stage independently. Total conversational latency is the sum of several independent components and should not be diagnosed as a single number.

## What to instrument

Emit timestamps for:

- wake detected;
- recording started;
- speech start;
- speech end;
- STT started/completed;
- persona request started;
- first model delta;
- first TTS chunk;
- playback started;
- barge-in requested/completed;
- turn completed.

Never log raw microphone samples by default.

## Experiment protocol

Run at least 30 short turns for each hardware/configuration profile. Report p50/p95 rather than averages alone. Test with Marina speaking, background music, keyboard noise, and normal room conditions.

## Live OVOS benchmark harness

For real hardware, use `scripts/voice-event-capture.py` to capture normalized lifecycle timestamps from the local OVOS MessageBus and `scripts/voice-benchmark.py` to calculate p50/p95 values. The harness intentionally records timestamps rather than raw audio and does not invent wake-word or first-token timings that are not observable on the selected OVOS version.
