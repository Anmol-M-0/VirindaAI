# Providers

VirindaAI ships with two provider classes:

| Provider | Network | Dependencies | Purpose |
|---|---:|---:|---|
| `echo` | No | None | deterministic offline development/test path |
| `openai` | Yes | Python stdlib only | OpenAI-compatible `/chat/completions` endpoints |

Set the provider with:

```bash
export VIRINDA_PROVIDER=echo
export VIRINDA_MODEL=offline-demo
```

For an OpenAI-compatible endpoint:

```bash
export VIRINDA_PROVIDER=openai
export VIRINDA_OPENAI_BASE_URL=https://example.invalid/v1
export VIRINDA_OPENAI_API_KEY=...
export VIRINDA_OPENAI_MODEL=...
```

The adapter deliberately uses the Python standard library instead of a vendor SDK. This keeps the core installable offline and makes provider behavior easy to test with a local HTTP fixture.
