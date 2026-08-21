# Local IPC Protocol

MarinaAI's desktop control plane uses a Unix domain socket rather than a TCP listener.
The protocol is deliberately small and dependency-free so a GTK, Qt, overlay, shell client,
or another local process can talk to the same `AssistantService` instance.

## Framing

Each request and response is one UTF-8 JSON object followed by `\n`.
Maximum request size is 256 KiB.

Request:

```json
{"id": 42, "method": "status", "params": {}}
```

Success:

```json
{"id": 42, "ok": true, "result": {"status": "ok"}}
```

Failure:

```json
{"id": 42, "ok": false, "error": "provider not configured: missing"}
```

## Methods

| Method | Parameters | Result |
|---|---|---|
| `status` | none | health object |
| `providers` | none | provider-name array |
| `ask` | `text`, optional `provider`, `model` | final response string |
| `cancel` | optional `reason` | `null` |
| `clear` | none | `null` |
| `history` | none | current-session message array |
| `events` | optional `limit` | current-session event array |
| `sessions` | none | session-id array |
| `backup` | `destination` | resolved backup path |

`ask` is request/response at the IPC level. The in-process `AssistantService.events` stream remains
the incremental path for clients that need token-level UI updates. A future IPC streaming protocol
can be added without changing the service/domain contracts.

## Security boundary

The socket lives under the local state directory and is created with mode `0600`. There is no TCP
listener, authentication header, or cross-machine transport in this release. Filesystem permissions
are therefore part of the trust boundary: treat the state directory as private user data.


## Streaming requests

`ask_stream` is the low-latency desktop-client operation. It keeps the Unix socket open and sends one JSON frame per event, followed by a final `complete` frame.

Request:

```json
{"id": 7, "method": "ask_stream", "params": {"text": "Hello"}}
```

Event frame:

```json
{"id": 7, "ok": true, "type": "event", "event": {"type": "ResponseDelta", "text": "..."}}
```

Completion frame:

```json
{"id": 7, "ok": true, "type": "complete", "result": "..."}
```

The stream is local-only and authenticated by Unix-socket filesystem permissions (`0600`). Desktop clients should consume deltas rather than polling SQLite.
