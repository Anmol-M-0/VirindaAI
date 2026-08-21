# VirindaAI 0.27.0 Production Release

## Highlights

### 1. Unified SQLite Schema Versioning & Safe Upgrade Path
- Implemented `src/virinda/infrastructure/persistence/migrations.py` with explicit `PRAGMA user_version` tracking.
- Guarantees 100% preservation of all historical sessions, messages, and events across legacy upgrades.
- Enforces atomic savepoints with automated rollback on failure, `PRAGMA integrity_check`, and `PRAGMA foreign_key_check`.
- Refuses future unknown schemas with `IncompatibleSchemaError`.

### 2. Live Voice Runtime & Deterministic Acceptance Suite
- Full `VoiceTurnRuntime` lifecycle engine (`IDLE -> LISTENING -> THINKING -> SPEAKING -> DEGRADED`).
- Automated 5-scenario acceptance test suite (`virinda acceptance voice`):
  - **Scenario A**: Cold Start & First Turn Latency (< 100ms CLI cold start).
  - **Scenario B**: 5-Turn Continuous Multi-Turn Conversation.
  - **Scenario C**: 30-Trial Rapid Barge-In Torture Suite across STT, LLM streaming, and TTS synthesis.
  - **Scenario D**: 20-Cycle Resource Soak Probing Zero Thread & Zero FD Leaks.
  - **Scenario E**: Desktop Web Overlay & OVOS MessageBus WebSocket State Synchronization.

### 3. Production Systemd & Packaging Validation
- Validated systemd user units (`virindad.service`, `virindai.service`, `deploy/ovos/*`).
- Added standalone runners (`virinda`, `virindad`) and system installer (`install.sh`).
- Created unified release gate (`scripts/release_check.sh`) validating wheel/sdist packaging, isolated virtualenv execution, migrations, systemd units, and voice scenarios.

## Validation Status

- Full Pytest Suite: **198/198 tests passing** (100%)
- Documentation Validation: **49 markdown files passing**
- OVOS Compatibility & MessageBus: **PASS**
- Rust audio-core: **PASS**
- Isolated Wheel Installation: **PASS**
- Voice UX Target Gates: **All P0 Latency Budgets Met**
