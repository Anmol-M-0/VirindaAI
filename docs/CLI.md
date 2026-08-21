# CLI Reference

The CLI is the smallest human-facing control surface for Virinda. It can run directly against the local application or through the long-lived `virindad` daemon.

## Basic commands

```bash
virinda status
virinda ask "Hello Virinda"
virinda history
virinda events
virinda sessions
virinda capabilities
virinda context
```

## Context

```bash
virinda context
virinda context private
virinda context normal
virinda context focus
virinda context quiet
```

Context changes are policy changes, not merely UI state changes. Private mode changes persistence/memory behavior; quiet/focus modes affect proactive and voice behavior.

## Diagnostics

```bash
virinda doctor
virinda doctor --audio
virinda doctor --services
virinda doctor --audio --services
virinda doctor --json
```

`--json` is designed for scripts/CI and should be preferred over parsing human-oriented output.

## Daemon mode

Start the local daemon:

```bash
virindad
```

Then use the same service over the Unix socket:

```bash
virinda --socket "$VIRINDA_SOCKET" status
virinda --socket "$VIRINDA_SOCKET" ask "hello"
virinda --socket "$VIRINDA_SOCKET" ask-stream "hello"
```

The socket is local and created with mode `0600`.

## Benchmarking & Acceptance
```bash
# Run voice latency benchmark across mock/live turns with UX gate evaluation
virinda benchmark voice --turns 5
virinda benchmark voice --mock --turns 10 --json

# Run end-to-end acceptance scenarios (A through E)
virinda acceptance voice
virinda acceptance voice --scenario C
virinda acceptance voice --json
```

## Data/diagnostic operations

The CLI also exposes history, semantic events, sessions, cancellation and SQLite backup operations. These are intended to be administrative application-plane operations; they do not bypass OVOS runtime policy.

## Exit codes

The CLI follows ordinary Unix conventions:

- `0` — successful operation.
- non-zero — invalid arguments, unavailable service, provider/configuration failure, or failed diagnostic.

For automation, prefer `--json` outputs and the dedicated validation scripts rather than matching human-readable error strings.
