# Local voice profile

Virinda's recommended baseline is a fully local Linux voice path:

```text
Microphone
  -> OVOS Dinkum Listener
      -> OpenWakeWord
      -> Silero VAD
      -> whisper.cpp STT
  -> OVOS message bus
      -> Virinda skill / Persona
      -> local OpenAI-compatible LLM
  -> ovos-audio
      -> phoonnx TTS
      -> speaker
```

The reference configuration uses `ovos-stt-plugin-whispercpp` with `base.en` because it has a small dependency footprint and is explicitly designed for CPU inference. OVOS also supports a faster-whisper plugin when GPU acceleration or different model sizes are preferable.

## Model trade-offs

| Profile | STT engine | Suggested model | Use case |
| --- | --- | --- | --- |
| `cpu-small` | whisper.cpp | `tiny.en` | low-memory machines |
| `cpu-default` | whisper.cpp | `base.en` | balanced local desktop |
| `cpu-accuracy` | whisper.cpp | `small.en` | more accurate CPU transcription |
| `gpu` | faster-whisper | `large-v3` | high-end GPU |

Do not assume one profile is optimal for every machine. Measure first-token latency, end-of-speech latency, and real-world WER on the target hardware.

## Local LLM

The included Persona points to an OpenAI-compatible `/v1` server. For a fully local deployment, Ollama, llama.cpp, vLLM, or LocalAI can provide that API. The Virinda core should not own the model server lifecycle.

## Privacy defaults

- wake-word inference stays local;
- no pre-wake recordings are persisted;
- STT runs locally in the reference profile;
- LLM calls are local unless the user explicitly configures a remote endpoint;
- TTS is local;
- diagnostics should report configuration and latency, not raw microphone audio.
