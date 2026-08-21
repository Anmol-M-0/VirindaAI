# Virinda Automations

Virinda automations are intentionally local, declarative, permission-aware, and observable.
They are not arbitrary shell scripts.

## Goals

- predictable execution
- durable run history
- safe retries
- explicit approval for consequential tools
- composable multi-step actions
- event-driven and time-driven triggers
- clean separation from the OVOS voice runtime

## Execution model

```text
trigger
  -> RoutineRunner
  -> RoutineRun ledger
  -> action plan
  -> capability/approval boundary
  -> result
  -> run history + event
```

A routine can finish as:

- `succeeded`
- `failed`
- `pending_approval`

No routine is considered successful merely because it was queued.

## Action DSL

The supported action forms are deliberately small:

```text
notify:<title>|<body>
tool:<name>|<json kwargs>
approve:tool:<name>|<json kwargs>
```

Use `||` to compose multiple actions.

Example:

```text
notify:Build complete|The build finished||approve:tool:browser.open|{"url":"https://example.com/builds/latest"}
```

## Error handling

A failing tool step is recorded and retried according to the routine's retry policy. Backoff is bounded. After the retry budget is exhausted, the run is marked `failed` and the routine emits a `routine.failed` event.

## Safety

Routines cannot:

- execute arbitrary shell strings
- bypass capability enablement
- bypass tool approval
- write outside configured filesystem roots
- access private-mode persisted context automatically

## OVOS integration

OVOS remains responsible for the microphone, wake word, VAD, STT, audio output, and message bus. Virinda normalizes relevant OVOS events into application-level automation events. This keeps routines portable between standalone and OVOS-backed modes.
