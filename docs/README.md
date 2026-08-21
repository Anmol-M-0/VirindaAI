# VirindaAI Documentation

This directory is the canonical engineering and operations documentation set for VirindaAI.
The project is intentionally documented as two cooperating systems:

1. **Virinda application plane** — product behavior, memory, policy, tools, automation, local state, desktop clients, and diagnostics.
2. **OVOS runtime plane** — microphone, wake word, VAD, STT, TTS, audio, message bus, GUI, PHAL, and skill execution.

The guiding rule is that Virinda owns product policy and durable application state; OVOS owns the production voice runtime. OVOS MessageBus is the production interactive bus; Virinda background work uses the JobBroker abstraction when durable asynchronous execution is required.

## Start here

| Need | Read |
|---|---|
| Understand the whole system | [Architecture](ARCHITECTURE.md) |
| Install on Linux | [Installation & First Boot](INSTALLATION.md) |
| Configure Virinda | [Configuration Reference](CONFIGURATION.md) |
| Operate/debug a running system | [Operations](OPERATIONS.md) and [Troubleshooting](TROUBLESHOOTING.md) |
| Use the CLI/daemon | [CLI](CLI.md) and [IPC](reference/IPC.md) |
| Understand feature status | [Feature Catalog](FEATURE_CATALOG.md) |
| Understand async jobs/events | [Async Job Backbone](JOB_BACKBONE.md) |
| Add/extend a feature | [Extending Virinda](EXTENDING.md) |
| Integrate with OVOS | [OVOS Integration](OVOS.md) |
| Verify OVOS compatibility | [OVOS Compatibility](OVOS_COMPATIBILITY.md) |
| Understand privacy/security | [Security](SECURITY.md) and [Security Model](SECURITY_MODEL.md) |
| Run tests/CI | [Testing](TESTING.md) |
| Release a version | [Release Process](RELEASE_PROCESS.md) |
| Understand terminology | [Glossary](GLOSSARY.md) |
| Follow product direction | [Roadmap](ROADMAP.md) |
| Validate real voice performance | [Voice acceptance](VOICE_ACCEPTANCE.md) |

## Documentation conventions

Each document should answer five questions where applicable:

- **Ownership:** which component owns the behavior?
- **Lifecycle:** when does it start, stop, retry, or expire?
- **Persistence:** what is stored, where, and for how long?
- **Failure:** what happens when the dependency is unavailable?
- **Security/privacy:** what data or authority crosses the boundary?

When implementation changes, update the affected contract documentation in the same change. Do not rely on tribal knowledge or comments in a single implementation file.

## Source of truth hierarchy

When two documents appear to disagree, use this order:

1. Executable tests and validators.
2. Checked-in configuration/constraints.
3. Public Python/IPC contracts.
4. Architecture/operations documentation.
5. Examples and prose in the README.

The README is intentionally an entry point, not the canonical source for detailed contracts.

## Current release

The current Virinda application release documented by this checkout is **0.25.4**.
