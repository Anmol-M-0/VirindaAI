# MarinaAI Architecture

## Purpose

MarinaAI is a Linux desktop assistant built **on OpenVoiceOS (OVOS)**. OVOS is the production voice framework; Marina owns the product-specific persona, custom skills, local state, policy, diagnostics, and optional desktop clients.

The standalone Marina control plane remains valuable for deterministic tests, automation, and environments where OVOS is not installed. It is explicitly not the owner of the production microphone/audio lifecycle.

## Production architecture

```text
                 +---------------------------+
                 |        Linux desktop      |
                 | PipeWire / ALSA / desktop |
                 +-------------+-------------+
                               |
                               v
                    +----------------------+
                    | ovos-dinkum-listener |
                    | wake / VAD / STT     |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    |   ovos-messagebus    |
                    +----------+-----------+
                               |
                   +-----------+-----------+
                   |                       |
                   v                       v
            +--------------+       +---------------+
            |   OVOS Core  |       |  ovos-audio   |
            | skills/pipeline|     | TTS / output  |
            +------+-------+       +---------------+
                   |
          +--------+---------+
          |                  |
          v                  v
   +--------------+   +----------------+
   | Marina Skill |   | Marina Persona  |
   | actions      |   | conversation    |
   +--------------+   +--------+-------+
                               |
                               v
                     ovos-openai-plugin
                               |
              +----------------+----------------+
              |                                 |
              v                                 v
          local LLM                       compatible API
       Ollama / llama.cpp                 / vLLM / etc.
```

OVOS provides the message bus, skill lifecycle, intent pipeline, listener, plugin system, and audio output services. Marina should consume those contracts rather than duplicate them.

## Ownership rules

| Responsibility | Owner |
|---|---|
| microphone capture | OVOS microphone/plugin layer |
| wake-word detection | OVOS wake-word plugin |
| VAD | OVOS VAD plugin |
| STT | OVOS STT plugin |
| message routing | OVOS message bus/core |
| intent matching | OVOS pipeline |
| conversation fallback | OVOS Persona |
| TTS synthesis/playback | OVOS audio + TTS plugin |
| Marina-specific commands | Marina skill |
| persona/instructions | Marina Persona configuration |
| durable Marina metadata | Marina SQLite layer / optional event bridge |
| desktop IPC | Marina compatibility daemon |
| UI | OVOS GUI client consuming Marina state/command bus messages; localhost HTTP overlay is diagnostics-only |

## Why the boundary matters

The original prototype had several independent components that implicitly competed for the same interaction lifecycle. The new rule is stronger:

> There must be exactly one production owner for each realtime voice concern.

This means Marina must not add a second microphone loop, a second wake-word engine, a second TTS scheduler, or a second general-purpose conversation bus.

## Marina skill vs Marina persona

These are deliberately separate:

### Marina skill

Owns explicit deterministic actions, product diagnostics, settings, and future desktop integrations. It is an OVOS `OVOSSkill` loaded by `ovos-core`.

### Marina persona

Owns open-ended conversational behavior. It is configured through `ovos-persona` and uses `ovos-openai-plugin` as its conversational backend, with the stable profile using its legacy solver entry point; the newer agent API is an explicit experimental track. The persona should sit at the appropriate fallback stage of the OVOS pipeline so high-confidence action skills still win.

## Standalone compatibility runtime

The existing `AssistantService` remains useful for:

- unit and integration testing;
- offline development without OVOS;
- CLI/API automation;
- embedded applications that need a small deterministic assistant facade;
- migration from the original prototype.

It must be treated as a compatibility/runtime boundary, not as a replacement for OVOS voice services.

## Persistence

SQLite remains Marina's local durable store for application-specific history and diagnostics. OVOS owns runtime conversational session state. Where both need durable records, Marina should consume message-bus events asynchronously rather than synchronously modifying OVOS state.

## Concurrency

The standalone service continues to use monotonic generations to make cancelled provider work harmless. OVOS provides the production voice/message lifecycle; Marina-specific background work must use the same cancellation principle and must never block the message bus or realtime audio path.

Realtime voice workers also fence TTS output by the service generation: queued or synthesized audio is checked immediately before playback, so cancellation can invalidate late audio without exposing application internals to OVOS adapters.
The standalone audio boundary additionally supports an optional `play_interruptible(..., cancel_event=...)` contract. Production realtime adapters that implement it must abort an in-progress playback when that worker-local event is set; this is required for deterministic barge-in latency. Each TTS worker owns a distinct cancellation event, queue, and completion state, so a later turn cannot accidentally re-enable an older playback worker or let a stopping worker consume the newer turn's audio.

## Failure policy

| Failure | Behavior |
|---|---|
| wake-word plugin unavailable | fall back to push-to-talk/text; surface diagnostic |
| VAD/STT unavailable | typed IPC/GUI interaction remains available |
| TTS unavailable | text response remains available |
| LLM/persona unavailable | deterministic skills still work |
| Marina skill crashes | OVOS core remains alive; skill can be reloaded |
| Marina GUI crashes | OVOS voice runtime remains independent |
| Marina SQLite unavailable | voice interaction remains available unless a feature explicitly requires local history |
| provider result arrives after standalone cancellation | result is ignored |

## Real-time boundary

Realtime audio callbacks must never call Python application code, SQLite, HTTP, GUI code, or unbounded logging. OVOS's listener/audio services own this boundary in production. If Marina adds DSP/native extensions later, they must remain behind OVOS plugin interfaces or a dedicated realtime worker boundary.

## External clients

Local desktop clients should prefer the OVOS message bus for voice lifecycle and assistant events. Marina's Unix-socket IPC remains for applications that want a compact request/response API without depending on OVOS internals.

## Messaging boundary

Marina deliberately has two messaging concerns:

- **OVOS MessageBus:** interactive assistant traffic: voice lifecycle, intents, GUI, TTS/audio coordination, and immediate skill events.
- **JobBroker:** durable/background work such as automation jobs, integrations, retries, notifications, and distributed workers.

The supported durable JobBroker backend is NATS JetStream, while development/test deployments use the in-process implementation. Application code depends only on the broker protocol. See [Async Job Backbone](JOB_BACKBONE.md).

## References

See `docs/OVOS.md` and `docs/REFERENCES.md` for upstream framework documentation and the exact components selected for Marina.


## UI transport rule

Production desktop interaction uses OVOS `ovos-gui` and the OVOS MessageBus. Marina HTTP is strictly a localhost diagnostics adapter. See [OVOS GUI Integration](OVOS_GUI.md).

## Product-first priority

Marina's architectural complexity is justified only when it protects or improves the assistant experience.
The priority order is P0 voice experience, P1 personal assistant, P2 desktop tools/UI, P3 durable background work,
and P4 distributed/multimodal expansion. A lower-priority infrastructure milestone must not become a prerequisite
for realtime voice operation unless an ADR explicitly records why.

See [Product North Star](PRODUCT_NORTH_STAR.md) and [Product Gates](PRODUCT_GATES.md).
