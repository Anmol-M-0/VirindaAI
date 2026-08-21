# Migration from the original MarinaAI prototype

The old repository centered behavior in top-level scripts such as `main.py`, `TTS.py`, `transcriber.py`, `keyboard_handler.py`, `chat_completions.py`, and configuration scripts. The rewrite intentionally does not preserve those module-level entry points as internal architecture.

| Legacy concern | New home |
|---|---|
| main/orchestration | `marina.application.service` |
| configuration | `marina.config.settings` |
| provider selection | `marina.infrastructure.providers.router` |
| completion backend | `marina.infrastructure.providers.*` |
| durable history | `marina.infrastructure.persistence.sqlite` |
| cancellation | `marina.core.cancellation` |
| canonical state | `marina.core.state` |
| event transport | `marina.core.events` + persistent event sink |
| CLI | `marina.interfaces.cli` |
| real-time audio | isolated `rust/audio-core` boundary |

The brainstorm documents in the original `docs/` tree are treated as design input, not as runtime dependencies. The final architecture is consolidated into this documentation set so there is one operational source of truth.
