# Product Gates

These gates keep Virinda aligned with the product north star.

## P0 voice gate

A production voice profile is not considered complete until a target Linux machine demonstrates:

- wake detection under representative noise;
- false-positive/false-negative measurements;
- end-of-speech detection;
- STT completion latency;
- time to first model token;
- time to first TTS audio;
- barge-in latency;
- no durable mic-audio persistence by default;
- clean fallback when STT/TTS/LLM is unavailable.

## P1 assistant gate

Memory, profiles, reminders, routines, and briefings must:

- share one session/context boundary;
- expose inspection/deletion controls;
- honor Private mode;
- have deterministic offline tests;
- avoid hidden side effects.

## P2 tool gate

Any tool that changes external/local state must:

- declare its risk class;
- pass the capability/permission boundary;
- generate an audit record;
- support explicit approval where required;
- fail closed when policy state is unavailable.

## P3 async gate

Background jobs must:

- run through `JobBroker`;
- remain independent of realtime voice;
- be idempotent on redelivery;
- survive process restart where durability is promised;
- expose health/recovery information;
- degrade to the in-process implementation for development/tests.

## Architecture guardrails

Production interaction must use OVOS MessageBus. Production desktop GUI integration must use `ovos-gui`.
HTTP is diagnostics-only. NATS JetStream is the only planned durable broker. No RabbitMQ/Fluvio/Redpanda
runtime integration is permitted unless a new ADR changes the architecture decision.
