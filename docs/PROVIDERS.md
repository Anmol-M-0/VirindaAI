# Providers

MarinaAI ships with two provider classes:

| Provider | Network | Dependencies | Purpose |
|---|---:|---:|---|
| `echo` | No | None | deterministic offline development/test path |
| `openai` | Yes | Python stdlib only | OpenAI-compatible `/chat/completions` endpoints |

Set the provider with:

```bash
export MARINA_PROVIDER=echo
export MARINA_MODEL=offline-demo
```

For an OpenAI-compatible endpoint:

```bash
export MARINA_PROVIDER=openai
export MARINA_OPENAI_BASE_URL=https://example.invalid/v1
export MARINA_OPENAI_API_KEY=...
export MARINA_OPENAI_MODEL=...
```

The adapter deliberately uses the Python standard library instead of a vendor SDK. This keeps the core installable offline and makes provider behavior easy to test with a local HTTP fixture.
