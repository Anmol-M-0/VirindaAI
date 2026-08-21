# Contributing to VirindaAI

## Scope

VirindaAI is a local-first desktop assistant runtime. Keep the control plane deterministic and platform-independent; integrations for audio, desktop UI, and providers belong behind contracts.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

The default runtime and test suite do not require network access or vendor SDKs.

## Design rules

1. Do not let adapters mutate canonical state directly.
2. Preserve generation checks around every asynchronous/streaming result.
3. Keep high-frequency audio/media out of SQLite and D-Bus.
4. Add new providers behind `CompletionProvider` and new storage behind `ConversationStore`.
5. Update architecture/decision docs when a boundary or ownership rule changes.
6. Keep the CLI usable without a desktop session so core regressions are easy to reproduce.

## Verification

Run `./scripts/check.sh`. CI also compiles the source tree and runs the full test suite.
