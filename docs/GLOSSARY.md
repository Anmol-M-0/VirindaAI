# Glossary

**AssistantService** — Virinda's authoritative application coordinator in the standalone control plane.

**Barge-in** — a user's new speech interrupting Virinda's current spoken response.

**Capability** — a user-visible or tool-visible ability exposed through Virinda's feature registry.

**Context mode** — a policy state such as normal, focus, private, or quiet that changes feature behavior.

**Dinkum Listener** — the OVOS service responsible for the production microphone → wake word → VAD → STT lifecycle.

**Generation** — a monotonic cancellation identifier used by Virinda to make late asynchronous work harmless.

**Local-first** — local execution/storage is the default; networked dependencies are optional and explicit.

**Virinda feature plane** — the product-specific layer for memory, alerts, tools, automations, desktop integration, and policy.

**Message bus** — OVOS's local inter-service event transport.

**Persona** — the OVOS conversational layer that selects/uses a solver/provider for general conversation.

**PHAL** — OVOS platform/hardware abstraction layer.

**Private mode** — a policy mode that suppresses durable conversation/memory persistence and optional capture/proactive behavior.

**Provider** — an LLM/backend implementation exposed through Virinda's provider protocol.

**Skill** — an OVOS plugin package containing intents/handlers that integrates with the OVOS core runtime.

**Satellite** — a remote microphone/voice endpoint that forwards interactions to a central assistant runtime.

**Stable constraints** — an OVOS version lock intended to keep independently released repositories compatible.

**ToolBroker** — Virinda's permissioned action boundary for filesystem, browser, clipboard, application, and future system tools.

**Wake word** — the locally detected activation phrase such as “Hey Virinda”.

**Voice plane** — the production OVOS runtime that owns microphone, wake word, VAD, STT, TTS, and audio.


### JobBroker
Virinda's application-level abstraction for durable/background work. The default implementation is in-process; NATS JetStream is the recommended production backend.

### Interactive bus
The OVOS MessageBus used for immediate assistant interaction, voice, GUI, intents, and service lifecycle events.

### Durable job
A background work item that must survive process boundaries/restarts and may require retries, acknowledgement, approval, or dead-letter handling.
