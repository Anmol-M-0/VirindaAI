# Observability

Marina's observability model is intentionally local-first and structured around lifecycle events rather than verbose application logs.

## Health

Use:

```bash
marina doctor --json
```

Health should answer:

- is Marina configured?
- is the SQLite store healthy?
- which provider is active?
- which OVOS profile is selected?
- which configured services are present/running?
- which audio tools/devices are visible?

## Semantic events

Marina emits events for lifecycle changes, user turns, response deltas, completion, cancellation, errors, context changes, feature actions, and voice lifecycle boundaries.

Events should be bounded and persistable without containing secrets.

## Voice metrics

The voice benchmark layer records:

```text
wake_detect_ms
speech_end_ms
stt_first_ms
stt_final_ms
llm_first_token_ms
tts_first_audio_ms
total_turn_ms
barge_in_ms
```

The goal is to optimize the user-perceived critical path, not just CPU time.

## Logs

Keep logs concise and structured. Never log:

- API keys
- bearer tokens
- raw audio
- full screenshots
- camera frames
- clipboard contents
- full filesystem contents

Use identifiers and summaries instead.

## Failure correlation

When debugging a voice turn, correlate these layers in order:

1. Listener state.
2. Utterance event.
3. Marina context update.
4. Provider request/first token.
5. TTS start.
6. TTS end.
7. Cancellation/barge-in if applicable.

This ordering makes it easier to isolate whether a latency problem belongs to audio, STT, application policy, provider, or TTS.
