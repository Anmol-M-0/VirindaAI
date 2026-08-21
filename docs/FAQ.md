# FAQ

## Why OVOS instead of building our own microphone/wake/STT/TTS loop?

Because OVOS already provides the lifecycle and compatibility boundaries for those services. Marina then stays focused on product behavior, policy, memory, tools, and desktop experience.

## Can Marina run without OVOS?

Yes. The standalone application/control plane supports deterministic/offline operation and is heavily tested without OVOS. Production voice interaction should use OVOS.

## Is every OVOS repository supported?

No. Marina follows the checked-in stable constraints plus a small set of separately validated add-ons. See `OVOS_SUPPORTED_STACK.md` and `OVOS_COMPATIBILITY.md`.

## Does “private mode” mean audio never touches memory?

Private mode prevents Marina's durable transcript/context persistence and disables relevant capture/proactive behaviors. OS/OVOS runtime services may still handle ephemeral audio required to complete the current turn.

## Can Marina run arbitrary shell commands?

No. Arbitrary shell execution is deliberately excluded from the tool DSL. Explicit system actions should be modeled as narrow, audited capabilities.

## How do I test the assistant without a microphone?

Use the deterministic CLI/provider path or the live OVOS bus smoke test. These validate application behavior without pretending to validate hardware.

## How do I debug “voice works but Marina does not answer”?

Run the staged diagnostics in `TROUBLESHOOTING.md`: first verify MessageBus/Core, then verify the Marina skill, then inspect listener/STT, and only then debug provider/TTS.


## Why doesn't Marina use NATS JetStream for everything?

Because voice/GUI interaction and durable background work have different requirements. OVOS MessageBus remains the low-latency interactive bus. Marina's JobBroker abstraction is reserved for durable automation, integrations, retries, and distributed workers. NATS JetStream is the recommended production backend when a persistent broker becomes necessary.

## Why NATS before NATS JetStream?

Marina benefits from a small durable messaging system that can start as a single-node local service and grow into distributed workers without making the core application depend on broker-specific APIs. NATS JetStream remains a valid adapter for deployments whose dominant need is queue-centric task processing.
