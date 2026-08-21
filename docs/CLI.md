# CLI Reference

The CLI is the smallest human-facing control surface for Marina. It can run directly against the local application or through the long-lived `marinad` daemon.

## Basic commands

```bash
marina status
marina ask "Hello Marina"
marina history
marina events
marina sessions
marina capabilities
marina context
```

## Context

```bash
marina context
marina context private
marina context normal
marina context focus
marina context quiet
```

Context changes are policy changes, not merely UI state changes. Private mode changes persistence/memory behavior; quiet/focus modes affect proactive and voice behavior.

## Diagnostics

```bash
marina doctor
marina doctor --audio
marina doctor --services
marina doctor --audio --services
marina doctor --json
```

`--json` is designed for scripts/CI and should be preferred over parsing human-oriented output.

## Daemon mode

Start the local daemon:

```bash
marinad
```

Then use the same service over the Unix socket:

```bash
marina --socket "$MARINA_SOCKET" status
marina --socket "$MARINA_SOCKET" ask "hello"
marina --socket "$MARINA_SOCKET" ask-stream "hello"
```

The socket is local and created with mode `0600`.

## Data/diagnostic operations

The CLI also exposes history, semantic events, sessions, cancellation and SQLite backup operations. These are intended to be administrative application-plane operations; they do not bypass OVOS runtime policy.

## Exit codes

The CLI follows ordinary Unix conventions:

- `0` — successful operation.
- non-zero — invalid arguments, unavailable service, provider/configuration failure, or failed diagnostic.

For automation, prefer `--json` outputs and the dedicated validation scripts rather than matching human-readable error strings.
