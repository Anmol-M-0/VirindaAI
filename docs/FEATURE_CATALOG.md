# VirindaAI Feature Catalog

Virinda's application layer is now feature-complete against the current roadmap. The implementation is deliberately split into three classes:

- **Native/local**: implemented without remote dependencies.
- **OVOS-backed**: Virinda owns policy/state while OVOS owns the runtime/service boundary.
- **Optional adapters**: available when the host provides the corresponding Linux/OVOS capability.

## Memory and personalization

Native local memory supports explicit facts, conversation notes, provenance, confidence, sensitivity, inspection, search, and deletion. A deterministic hash embedding fallback enables semantic-ish local note ranking without a model dependency; a proper embedding provider can be substituted later.

Private mode rejects new persisted memory and disables persisted conversation turns.

## Alerts and notifications

Virinda has a durable local alert scheduler and notification inbox. An OVOS bus adapter can publish Virinda notifications into an OVOS installation, while `ovos-skill-alerts` remains the authoritative production scheduler/UI when installed. The OVOS Alerts skill supports alarms, timers, reminders, events and todos. See the upstream project: https://github.com/OpenVoiceOS/ovos-skill-alerts

## Tools and automation

The permissioned `ToolBroker` now exposes safe system information, approved filesystem read/write, browser fetch/open/search, clipboard read/write, and application launch. Every tool execution is written to a local audit log.

Routines use a constrained DSL with keyword triggers and `notify:*` or `tool:*` actions. Arbitrary shell execution is intentionally not a routine action.

## Desktop experience

The production desktop surface is integrated through OVOS `ovos-gui`/MessageBus using Virinda-owned state and command messages. A loopback browser overlay remains available only as a developer/diagnostics client over the standalone service API.

OVOS GUI integration is exposed through an adapter so the production desktop can use `ovos-gui`, which owns the GUI message-bus service and client protocol. See https://github.com/OpenVoiceOS/ovos-gui

## Voice

The OVOS runtime owns microphone, wake word, VAD, STT, TTS and audio playback. Virinda adds voice profiles, wake-word benchmark metrics, latency sampling, barge-in/follow-up policy, and audio-device inspection/selection helpers.

The packaged OVOS skill now supports Virinda-specific voice controls: normal, focus, private, quiet, briefing, and meeting start/stop.

## Multimodal

Virinda can capture desktop screenshots and optional V4L2 camera frames. Clipboard input is available as a multimodal text source. An OpenAI-compatible vision adapter accepts image bytes using the standard chat-completions vision content shape.

All capture operations are disabled by policy in private mode where appropriate.

## Proactive and meeting mode

A context collector reads active-application and headset signals when supported by the host. Proactive policies can generate local notifications while respecting quiet/focus policies.

Meeting mode persists a dedicated transcript stream independently of ordinary conversation state, with start/append/stop lifecycle operations.

## Distributed / satellite boundary

Virinda includes a versioned `SatelliteEnvelope`, an OVOS message-bus adapter, and an HMAC-authenticated JSON-line TCP client for a future cross-device/satellite transport. The transport layer is isolated so a production deployment can use HiveMind/OVOS transport without changing feature code.

## Security hardening

Consequential tools now require explicit approval. The IPC layer supports short-lived, single-use approval tokens so a desktop UI or voice confirmation can approve one action without globally disabling the safety boundary. Browser/network tools reject private, loopback, link-local, reserved, multicast and credential-bearing URLs and validate redirect targets. Filesystem tools default to the Virinda data directory plus explicitly configured `VIRINDA_TOOL_ROOTS`; the full home directory is no longer implicitly writable. Satellite envelopes include timestamps/nonces and reject stale messages.

## OVOS-backed production components

The stable profile now includes the current constrained GUI, PHAL, message bus, Alerts, diagnostics, screenshot, camera, volume and application-launcher components used by Virinda's feature plane. OVOS recommends installing against the stable constraints file so these independently released repositories remain mutually compatible. https://github.com/OpenVoiceOS/OpenVoiceOS/blob/main/constraints-stable.txt

## Explicit non-goals

- raw microphone recording by default;
- arbitrary shell execution from natural language;
- direct GUI ownership of state;
- bypassing the OVOS stable constraints file;
- assuming optional hardware/services exist on every host.

## Runtime validation status

All native/application features are covered by the local test suite. Live OVOS, microphone, wake-word, speaker, PipeWire, V4L2 and cross-device transport still require validation on a provisioned Linux host with the corresponding hardware/services.


## Async job backbone

| Feature | Implementation status | Production boundary | Notes |
|---|---|---|---|
| In-process jobs | Implemented | Virinda application | Default for tests/development |
| NATS JetStream | Implemented adapter | JobBroker | Supported durable production backend |
| Fluvio/Redpanda | Future evaluation | JobBroker/event stream | Only if high-volume streaming becomes material |
