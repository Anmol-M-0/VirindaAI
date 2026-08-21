# Migration from the original VirindaAI prototype

The old repository centered behavior in top-level scripts such as `main.py`, `TTS.py`, `transcriber.py`, `keyboard_handler.py`, `chat_completions.py`, and configuration scripts. The rewrite intentionally does not preserve those module-level entry points as internal architecture.

| Legacy concern | New home |
|---|---|
| main/orchestration | `virinda.application.service` |
| configuration | `virinda.config.settings` |
| provider selection | `virinda.infrastructure.providers.router` |
| completion backend | `virinda.infrastructure.providers.*` |
| durable history | `virinda.infrastructure.persistence.sqlite` |
| cancellation | `virinda.core.cancellation` |
| canonical state | `virinda.core.state` |
| event transport | `virinda.core.events` + persistent event sink |
| CLI | `virinda.interfaces.cli` |
| real-time audio | isolated `rust/audio-core` boundary |

The brainstorm documents in the original `docs/` tree are treated as design input, not as runtime dependencies. The final architecture is consolidated into this documentation set so there is one operational source of truth.
