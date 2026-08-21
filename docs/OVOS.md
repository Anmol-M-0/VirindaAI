# OpenVoiceOS Integration

MarinaAI's production voice runtime is OpenVoiceOS (OVOS). The standalone Marina runtime remains available for headless automation, testing, and non-OVOS clients, but it is no longer the preferred owner of microphone, wake-word, VAD, STT, TTS, or message-bus lifecycle.

## Ownership model

```text
PipeWire / ALSA / microphone plugin
             |
             v
     ovos-dinkum-listener
        |     |     |
        |     |     +--> STT plugin
        |     +--------> VAD plugin
        +--------------> wake-word plugin
             |
             v
       ovos-messagebus
             |
             v
          ovos-core
             |
       +-----+------+
       |            |
       v            v
 Marina skill   OVOS Persona
                    |
                    v
          ovos-openai-plugin
                    |
          Ollama / llama.cpp /
          vLLM / LocalAI / API
                    |
                    v
             ovos-audio / TTS
```

OVOS documents the message bus as the internal communication layer between independent services, while Dinkum Listener owns microphone, wake-word, VAD and STT processing. OVOS also loads speech and wake-word implementations through its plugin manager. See the upstream references in `docs/REFERENCES.md`.

## Why this is better

The old Marina audio runtime duplicated responsibilities that OVOS already solves. With OVOS as the voice framework:

- wake-word detection becomes a plugin choice instead of a Marina implementation;
- VAD and STT remain replaceable without changing Marina;
- TTS/audio output are coordinated by `ovos-audio`;
- follow-up listening can use OVOS hybrid-listen behavior;
- conversation routing can use `ovos-persona`;
- OpenAI-compatible local models can be selected through `ovos-openai-plugin`;
- external desktop clients can subscribe to the existing OVOS message bus instead of a second voice event protocol.

## Recommended local stack

For a Linux desktop build, start with:

- `ovos-dinkum-listener`
- `ovos-ww-plugin-openwakeword`
- `ovos-vad-plugin-silero`
- `ovos-stt-plugin-whispercpp` for the default CPU-local profile, with `ovos-stt-plugin-fasterwhisper` as a GPU-oriented alternative
- `ovos-audio`
- `phoonnx`/Piper-compatible voices through `ovos-tts-plugin-phoonnx`
- `ovos-persona`
- `ovos-openai-plugin`
- Ollama, llama.cpp, vLLM, or LocalAI as the local model server

Dinkum Listener supports hybrid listening, where a follow-up utterance can be accepted for a configured time after an interaction without requiring another wake word. It also supports pre-wake VAD to reduce false activations.

## Wake phrase: “Hey Marina”

OVOS supports arbitrary openWakeWord model files through `ovos-ww-plugin-openwakeword`. The plugin's built-in model examples include "hey_jarvis"; a true "hey marina" experience therefore requires a compatible custom model file. Do not silently substitute a different wake phrase in a production configuration.

Recommended configuration once the custom model exists:

```json
{
  "listener": {"wake_word": "hey_marina"},
  "hotwords": {
    "hey_marina": {
      "module": "ovos-ww-plugin-openwakeword",
      "models": ["/path/to/hey_marina.tflite"],
      "inference_framework": "tflite",
      "threshold": 0.5,
      "listen": true
    }
  }
}
```

## Persona design

The included `config/ovos/marina-persona.json` is the **stable production profile**. It uses the legacy `ovos-solver-openai-plugin` API because the current OVOS stable constraints pair `ovos-persona 0.6.x`, `ovos-plugin-manager 0.9.x`, and `ovos-openai-plugin 2.0.x`. The newer `ovos-chat-openai-plugin` agent configuration is intentionally isolated under `config/ovos/experimental-agent/` because the current development plugin requires newer Persona/OPM versions than the stable channel provides. See `docs/OVOS_COMPATIBILITY.md` before switching tracks.

Keep action-oriented skills ahead of the persona pipeline. The persona should be the conversational/fallback layer, not the mechanism for executing every desktop action.

## Migration rule

New voice functionality should be implemented as one of:

1. an OVOS skill,
2. an OVOS plugin,
3. an OVOS persona/agent configuration,
4. a message-bus integration.

Do not add another microphone loop, wake-word engine, TTS scheduler, or conversational bus to Marina itself.

## TTS note

The former `ovos-tts-plugin-piper` repository is archived as of June 11, 2026 and documents migration to `ovos-tts-plugin-phoonnx`. Marina therefore uses phoonnx in the current configuration template while preserving the Piper voice catalogue through phoonnx.

### Conversation feel

Marina enables OVOS `hybrid_listen` and `instant_listen` in the example profile. Dinkum Listener documents hybrid listening as a follow-up window that avoids repeating the wake word, and instant listen as removing the pause between the wake word and the spoken command. Both are hardware/STT dependent, so tune them from measured latency and transcription quality rather than treating the example values as universal. https://github.com/OpenVoiceOS/ovos-dinkum-listener

The profile keeps `vad_pre_wake_enabled` enabled and does not also enable the Silero wake-word verifier, avoiding duplicate Silero VAD work; Dinkum documents these as alternative false-activation reduction strategies. https://github.com/OpenVoiceOS/ovos-dinkum-listener

## Live runtime smoke test

After provisioning a stable OVOS environment and starting the message bus + core:

```bash
.venv/bin/python scripts/ovos-runtime-smoke.py "marina status" --expect "Marina is online"
```

This injects a text utterance at `recognizer_loop:utterance` and waits for a `speak` event. It proves the bus → core → skill → response path without requiring a microphone, wake-word model, or speaker. A return code of `2` means the OVOS environment/bus is not provisioned; `1` means the stack booted but the expected response did not arrive.

For full cross-repository conformance, Marina should additionally run the upstream `ovos-test-harness`, which validates a real pinned OVOS stack against the formal OVOS architecture specifications.


## GUI transport

Marina does not use its HTTP overlay as the OVOS desktop control plane. Production GUI state and commands use `ovos-gui`/MessageBus; see [OVOS GUI Integration](OVOS_GUI.md).
