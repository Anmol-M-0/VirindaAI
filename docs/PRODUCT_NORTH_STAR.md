# Virinda Product North Star

## Purpose

VirindaAI is a **local-first personal desktop voice assistant for Linux**.
The product goal is not to maximize infrastructure. The goal is to make Virinda feel fast,
private, useful, predictable, and pleasant to talk to.

## Product hierarchy

### P0 — Core assistant experience

This is the product-critical path.

- "Hey Virinda" passive listening.
- Fast wake → listening feedback.
- Natural multi-turn conversation.
- Low-latency streaming responses and speech.
- Barge-in while Virinda is speaking.
- Private / Focus / Quiet modes.
- Robust offline/typed fallback when voice services fail.
- Clear visible listening/speaking/privacy state.

### P1 — Personal assistant

- Memory that users can inspect and delete.
- Profiles and preferences.
- Reminders and alerts.
- Personalized briefings.
- Natural-language routines.
- Notifications and follow-up conversations.

### P2 — Safe computer assistant

- Browser assistance.
- Desktop/application control.
- Clipboard, screenshot, and filesystem tools.
- Tool approval and auditability.
- Visual routine editing.

### P3 — Durable background work

- NATS JetStream-backed jobs.
- Long-running integrations.
- Retry/recovery/idempotency.
- Background workers.
- Operational health and repair tooling.

P3 must never make the P0 realtime voice path depend on NATS availability.

### P4 — Advanced/distributed capabilities

- Multimodal camera/screen awareness.
- Satellites and multi-device operation.
- Distributed workers.
- Optional remote integrations.

P4 is an extension of Virinda, not the definition of Virinda.

## Hard product rules

1. **Voice experience beats infrastructure expansion.**
2. **OVOS owns realtime voice/audio lifecycle in production.**
3. **OVOS MessageBus owns interactive assistant traffic.**
4. **NATS JetStream owns durable asynchronous work only.**
5. **SQLite owns Virinda-local durable product state.**
6. **There is one authoritative application coordinator.**
7. **Consequential tools require explicit policy/approval.**
8. **Private mode must not persist or inject durable personal context.**
9. **Every feature must degrade cleanly when its optional integration is unavailable.**
10. **No new infrastructure dependency is added unless it materially improves a user-visible capability.**

## Definition of product progress

A release is product-progress when it improves at least one of:

- wake reliability;
- perceived response latency;
- conversational continuity;
- memory quality/trust;
- automation usefulness;
- desktop interaction quality;
- privacy/control clarity;
- real-world hardware reliability.

Infrastructure-only work is maintenance unless it directly enables one of these outcomes.

## Current priority

The next major product milestone is **real voice acceptance on Linux hardware**:

```text
microphone
  → wake word
  → VAD
  → STT
  → Virinda context/persona
  → streaming response
  → TTS
  → playback
  → barge-in
```

Measure this path before expanding the distributed/platform surface further.
