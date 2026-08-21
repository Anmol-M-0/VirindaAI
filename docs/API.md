# Application API

`AssistantService` is the stable application boundary.

## Snapshot

`service.snapshot()` returns:

- `session_id`
- `generation_id`
- `lifecycle`
- `mode`
- `transcript`
- `response`
- `provider`
- `model`
- `sequence`

## Mutations

### `ask(text, provider=None, model=None) -> str`

Starts a new generation, persists the user message, streams provider output, persists the assistant message, and returns the final text. An interrupted or stale generation returns an empty string.

### `cancel(reason="user") -> None`

Invalidates the active generation immediately. It does not wait for the provider to cooperate.

### `clear() -> None`

Invalidates the active generation and clears the volatile transcript/response projection while retaining durable history.

### `close() -> None`

Closes the local persistence connection. Call this from daemons/tests on shutdown.

## Events

Semantic events include lifecycle changes, final transcripts, response deltas, response completion, cancellation, and errors. They are persisted and also published to the live event bus.

## Diagnostics

`service.health() -> dict` reports service state, configured providers, and SQLite integrity/row counts. This is intended for CLI, daemon, and future D-Bus/GUI health surfaces.

## Concurrency guarantee

`ask()` may consume a provider stream outside the commit lock. Generation changes (`ask`, `cancel`, `clear`) and the final assistant-message commit are fenced so the following invariant holds: once a newer generation is accepted, an older generation cannot persist a final assistant message.

## Persistence backup

`service.store.backup(path)` uses SQLite's backup API and is safe to invoke while the service is running.

## Event subscriptions

`service.events` exposes the local bounded event bus. `subscribe(sink)` and `unsubscribe(sink)` are safe for long-lived clients. Subscriber exceptions are isolated and counted rather than propagated into the application operation that emitted the event.

## Local IPC

`virindad` exposes the same application service over a local Unix domain socket at
`$VIRINDA_DATA_DIR/virinda.sock` (mode `0600`). The protocol is newline-delimited JSON:

```json
{"id": 1, "method": "ask", "params": {"text": "hello"}}
```

Supported methods are `status`, `providers`, `ask`, `cancel`, `clear`, `history`, `events`,
`sessions`, and `backup`. This is intentionally a local control protocol rather than a TCP
API: desktop clients do not need a web framework or an open listening port.
