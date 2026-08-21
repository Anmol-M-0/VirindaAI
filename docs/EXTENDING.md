# Extending MarinaAI

## Add a completion provider

Implement `marina.domain.contracts.CompletionProvider`:

```python
class MyProvider:
    name = "my-provider"

    def stream(self, request):
        yield "first chunk"
        yield "second chunk"
```

Register it in `application/runtime.py` or a future provider factory. The provider must not depend on UI, persistence, audio, or the global state machine.

## Add a presentation client

Use `AssistantService` as the only application-facing boundary. A GUI or D-Bus adapter should:

1. request `snapshot()`;
2. subscribe to the event sink;
3. invoke `ask()`, `cancel()`, and `clear()` mutations;
4. reconnect by getting a new snapshot after a restart.

The presentation layer should never inspect SQLite directly.

## Add voice

The intended voice boundary is:

```text
capture -> real-time audio core -> bounded semantic/PCM queues -> STT -> AssistantService
                                                     |
                                                     +-> TTS -> audio core
```

Audio callbacks must never perform network I/O, Python calls, SQLite writes, unbounded logging, or blocking UI work.
