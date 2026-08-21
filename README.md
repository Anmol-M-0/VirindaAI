# MarinaAI

MarinaAI is a local-first ambient desktop assistant for Linux built on OpenVoiceOS (OVOS). OVOS owns the production voice lifecycle—message bus, wake word, VAD, STT, TTS, and audio—while Marina owns the persona, product-specific skills, durable local state, and optional desktop IPC. The original script-heavy prototype has been replaced with a testable control plane and an explicit OVOS integration.

## What is implemented

- Passive local wake-word interaction with bounded pre-roll and VAD turn detection
- Push-to-talk, toggle listening, follow-up conversation, and TTS barge-in policy
- OpenVoiceOS-first production voice integration: OVOS listener, message bus, Persona, and audio services
- Deployable `skill-marin-ai.openvoiceos` skill and Marina Persona configuration

- Single authoritative `AssistantService` coordinator
- Protocol-based provider, persistence, cancellation, tokenization, and event boundaries
- Monotonic generation cancellation that makes late results harmless
- Thread-safe SQLite history and append-only semantic event logging
- Session recovery after process restart
- Deterministic offline `echo` provider
- OpenAI-compatible HTTP provider using only the Python standard library
- Streaming response event model
- CLI for status/health, provider discovery, prompting, history, events, sessions, cancellation, clearing, and SQLite backup
- systemd user-service template
- CI for Python 3.11–3.13
- Rust crate boundary for future real-time audio ownership

## Messaging architecture

Marina uses OVOS MessageBus for production interactive voice/GUI/service communication. Durable background work is isolated behind a `JobBroker` abstraction; in-process is the default and NATS JetStream is the supported production backend when durable/distributed work requires a broker; the in-process backend remains the default for development/test. See `docs/JOB_BACKBONE.md`.

## Architecture

```text
                    CLI / GTK / D-Bus / overlay
                              |
                              v
                     +-----------------+
                     | AssistantService|
                     +--------+--------+
                              |
            +-----------------+------------------+
            |                 |                  |
            v                 v                  v
       State Machine     Provider Router      SQLite Store
            |                 |                  |
            v                 v                  v
       generations       echo / HTTP       messages / events
       lifecycle          adapters             recovery
                              |
                              v
                     optional platform plane
                  Rust audio / STT / TTS / GNOME
```

The key ownership rule is simple: adapters produce data; the application service coordinates it; the state machine owns canonical runtime state.

## OpenVoiceOS quickstart

For the intended production voice experience, install the OVOS extra using the stable OVOS release constraints:

```bash
./scripts/install-ovos.sh
```

Then configure the user OVOS config from `config/ovos/mycroft.conf.example.json`, install a real `hey_marina` wake model, and review `config/ovos/marina-persona.json`. OVOS officially supports installing the core services separately or through its full `mycroft` extra, and its stable constraints file is the recommended way to keep component versions compatible.

See `docs/OVOS.md` for the complete production architecture.

For the reference local voice profile, Marina now configures OVOS to use `ovos-stt-plugin-whispercpp` with the `base.en` model. A GPU-oriented Faster-Whisper profile remains a documented alternative. See `docs/LOCAL_VOICE_PROFILE.md`.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

export MARINA_DATA_DIR="$PWD/.local/marina"
marina status
marina ask "Hello Marina"
marina history
marina events
marina capabilities
marina context
marina context private
```

The default path is fully offline and has no mandatory third-party runtime dependency.

## Providers

Use the deterministic offline provider:

```bash
export MARINA_PROVIDER=echo
export MARINA_MODEL=offline-demo
```

Or configure an OpenAI-compatible endpoint:

```bash
export MARINA_PROVIDER=openai
export MARINA_OPENAI_BASE_URL=https://example.invalid/v1
export MARINA_OPENAI_API_KEY=your-key
export MARINA_OPENAI_MODEL=your-model
```

See `docs/PROVIDERS.md`.

## Development checks

```bash
./scripts/check.sh
```

The script runs compilation, the complete test suite, and optional Ruff/Cargo checks when those tools are installed. The test suite includes a real threaded cancellation scenario and a local HTTP fixture for the OpenAI-compatible adapter.

## Documentation

See `docs/PERSONALIZATION_AND_APPROVALS.md` for the profile, memory confidence/sensitivity, briefing, and conversational approval contracts.

- `docs/ARCHITECTURE.md` — canonical system design and ownership rules
- `docs/API.md` — application contract
- `docs/EXTENDING.md` — adding providers and presentation adapters
- `docs/PROVIDERS.md` — provider configuration
- `docs/OPERATIONS.md` — local state, service operation, diagnostics, recovery
- `docs/SECURITY.md` — local-first privacy and secret-handling guidance
- `docs/MIGRATION.md` — mapping from the original prototype
- `docs/DECISIONS.md` — architecture decisions and rationale
- `docs/AUDIO_INTERACTIONS.md` — voice UX, wake word/VAD/STT/TTS research, privacy model, and implementation roadmap
- `docs/OVOS.md` — canonical OpenVoiceOS architecture, installation model, wake-word setup, and migration rules
- `docs/OVOS_SUPPORTED_STACK.md` — supported OVOS projects, reliability tiers, and the production dependency policy
- `docs/REFERENCES.md` — upstream OVOS references used by the architecture
- `docs/LOCAL_VOICE_PROFILE.md` — concrete local STT/LLM/TTS profile and model choices
- `docs/PERFORMANCE.md` — latency metrics and voice benchmarking protocol
- `docs/ROADMAP.md` — prioritized product feature roadmap and safety/reliability gates
- `docs/FEATURE_IMPLEMENTATION_MATRIX.md` — feature ownership and runtime-acceptance matrix
- `docs/INSTALLATION.md` — clean-machine installation and first-boot procedure
- `docs/CONFIGURATION.md` — complete environment/configuration reference
- `docs/CLI.md` — command-line reference and exit/daemon behavior
- `docs/TESTING.md` — unit, release, OVOS, live-runtime, and hardware acceptance layers
- `docs/TROUBLESHOOTING.md` — operator diagnosis playbook
- `docs/SECURITY_MODEL.md` — trust zones, tool authority, privacy, and remote boundaries
- `docs/OBSERVABILITY.md` — health, events, voice metrics, and diagnostic methodology
- `docs/CONTRIBUTOR_GUIDE.md` — code ownership and extension rules
- `docs/RELEASE_PROCESS.md` — release/version/compatibility process
- `docs/GLOSSARY.md` — common Marina/OVOS terminology
- `docs/DOCUMENTATION_POLICY.md` — documentation quality contract
- `docs/FAQ.md` — common architecture and deployment questions
- `docs/README.md` — documentation hub and source-of-truth hierarchy
- `models/README.md` — wake-word model requirements and acceptance criteria

## Runtime hardening

The service fences generation changes and final persistence commits with a small critical section. This prevents a cancelled or superseded provider worker from writing stale assistant messages after a newer generation starts. SQLite exposes an integrity/row-count health check and uses the native backup API for safe live backups.

## Release boundary

GNOME/D-Bus, PipeWire, STT, and TTS are intentionally not faked inside the control plane. Their interfaces are isolated so those integrations can be added without reintroducing the coupling that made the original prototype difficult to maintain.

## License

MIT.

## Long-lived daemon

For a desktop client, run `marinad` once and talk to the same application service through its local
Unix socket. The CLI can use that socket explicitly:

```bash
marinad
marina --socket "$MARINA_DATA_DIR/marina.sock" status
marina --socket "$MARINA_DATA_DIR/marina.sock" ask "hello"
marina --socket "$MARINA_DATA_DIR/marina.sock" ask-stream "hello"
```

This avoids opening SQLite from multiple UI processes and gives GUI/overlay clients one authoritative
state owner. See [`docs/reference/IPC.md`](docs/reference/IPC.md).

## Voice configuration

The control plane supports passive wake-word interaction, push-to-talk, toggle listening, and short follow-up turns. Configure the policy with environment variables:

```bash
MARINA_AUDIO_MODE=wake_word
MARINA_WAKE_WORD="hey marina"
MARINA_WAKE_THRESHOLD=0.5
MARINA_END_SILENCE_MS=750
MARINA_FOLLOW_UP_WINDOW_MS=8000
```

These settings remain useful for the standalone compatibility runtime. In the production OVOS runtime, configure microphone, wake-word, VAD, STT, TTS, and hybrid listening through OVOS configuration. See `docs/OVOS.md`.

## OVOS diagnostics

After installing the OVOS extra/runtime, run:

```bash
marina doctor
```

The doctor checks the OVOS core/listener/persona/audio modules, Marina's Persona JSON, the OVOS configuration template, and the configured `hey_marina` wake model. A source checkout can run it with `PYTHONPATH=src python -m marina doctor`.

A `FAIL` for the wake model is intentional until a real custom `hey_marina` model file is installed. The OVOS OpenWakeWord plugin accepts model files through the `hotwords` configuration, but the repository does not bundle a fake or unrelated model. See `docs/REFERENCES.md` for the upstream OpenWakeWord plugin reference.


## OVOS compatibility

Marina supports two OVOS Persona generations, but they are not mixed. The production profile follows the current OVOS stable constraints and uses the legacy OpenAI solver API. The newer `ovos-chat-openai-plugin` agent framework is isolated under `config/ovos/experimental-agent/` until OVOS publishes a stable constraints set that contains compatible Persona and plugin-manager versions. See `docs/OVOS_COMPATIBILITY.md`.


### OVOS runtime smoke test

After installing the OVOS profile, run `python scripts/ovos-smoke.py` from the Marina checkout. It verifies that the expected OVOS and Marina-selected audio distributions are actually installed in the active virtual environment. It does not require a microphone, speaker, wake model, or running message bus.

## OVOS environment profiles

Marina supports two explicit verification profiles:

```bash
python scripts/ovos-smoke.py --profile stable
python scripts/ovos-smoke.py --profile local-voice
```

`stable` checks only the packages in the checked-in OVOS stable lock. `local-voice` additionally checks the Marina-selected Whisper.cpp STT and phoonnx TTS add-ons.

For hardware diagnostics:

```bash
marina doctor --audio --services
```

The doctor determines the required STT/TTS dependencies from the selected OVOS configuration rather than hard-coding a single engine.


Current release: **v0.26.3**. See `docs/FEATURE_CATALOG.md` for the implemented feature plane and `docs/ROADMAP.md` for the remaining live-runtime acceptance work.


## Natural assistant commands

See [`docs/NATURAL_COMMANDS.md`](docs/NATURAL_COMMANDS.md) for the deterministic command grammar used before provider/LLM execution.

## Product direction

Marina is intentionally product-first. OVOS owns realtime voice; Marina owns personal-assistant behavior;
NATS JetStream owns durable background work. See [`docs/PRODUCT_NORTH_STAR.md`](docs/PRODUCT_NORTH_STAR.md)
and [`docs/PRODUCT_GATES.md`](docs/PRODUCT_GATES.md).
