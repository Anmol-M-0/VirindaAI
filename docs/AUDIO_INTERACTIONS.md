# MarinaAI Audio Interaction Design

## Design decision

Marina's production audio experience is implemented by OpenVoiceOS, not by a second Marina voice loop.

OVOS's Dinkum Listener already provides a modular microphone → wake word → VAD → STT pipeline, while `ovos-audio` owns TTS and sound output. OVOS also supports hybrid listening for follow-up turns without repeatedly requiring a wake word.

Marina therefore defines **interaction policy and UX expectations**, while OVOS provides the actual audio machinery.

## Target user experience

The default experience should feel like a classic ambient assistant:

```text
         idle
          |
          v
    local wake detector
          |
   "Hey Marina" detected
          |
          v
       listening
          |
          v
       processing
          |
          v
       speaking
          |
          +---- user interrupts ----> stop / new turn
          |
          v
    short follow-up window
          |
          +---- speech -----------> listening
          |
          +---- timeout ----------> idle
```

The important privacy property is that wake-word inference can remain local and full STT is activated only for an interaction.

## Interaction modes

### Passive wake word

Recommended default. Keep a local wake-word detector armed and use VAD/STT only after activation.

### Push-to-talk

Keyboard shortcut, headset button, or GUI button. This is the deterministic privacy fallback.

### Toggle-to-listen

A tray/overlay button enters listening mode until the user finishes the turn.

### Follow-up / hybrid listening

After a response, keep the listener open for a short configurable window. Dinkum Listener exposes `hybrid_listen` and `listen_timeout` specifically for this model.

### Barge-in

The user must be able to interrupt TTS. The correct implementation is to stop audio playback and cancel the current conversation generation, then return to listening. The Marina standalone service already has generation fencing for this; the OVOS path should use the standard `mycroft.stop` / listener lifecycle rather than inventing a parallel cancellation bus.
For the standalone compatibility audio boundary, playback adapters may implement `play_interruptible(..., cancel_event=...)`. A production adapter must make `stop()` and the worker cancellation event interrupt any already-running playback; checking generation only before playback is insufficient for strict interruption latency.

### Text fallback

CLI, Unix IPC, and future GUI clients remain first-class. Audio is a transport, not the assistant's only interface.

## Wake word: “Hey Marina”

OVOS can load openWakeWord models through `ovos-ww-plugin-openwakeword`. The plugin supports arbitrary `.onnx` or `.tflite` model paths and configurable thresholds. The current plugin ships example pretrained models such as `hey_jarvis`, not a built-in `hey_marina` model.

Marina therefore ships an explicit model placeholder:

```json
"hotwords": {
  "hey_marina": {
    "module": "ovos-ww-plugin-openwakeword",
    "models": ["/ABSOLUTE/PATH/TO/hey_marina.tflite"],
    "inference_framework": "tflite",
    "threshold": 0.5,
    "listen": true
  }
}
```

Do not silently map `hey marina` to another phrase. A dedicated model should be trained/selected and evaluated for false accept and false reject rates before calling the feature production-ready.

## VAD and STT

Recommended OVOS strategy:

- Silero VAD through `ovos-vad-plugin-silero` for local speech boundaries.
- A local Whisper-family OVOS STT plugin for robust transcription.
- Use Dinkum Listener's configurable `speech_begin`, `silence_end`, recording limits, and `vad_pre_wake_enabled` to tune responsiveness.

The application should measure the following instead of guessing about quality:

- wake false accept rate;
- wake false reject rate;
- time from wake to listening;
- end-of-speech detection latency;
- STT latency;
- TTS first-audio latency;
- interruption latency;
- total turn latency.

## TTS and response streaming

OVOS audio should receive sentence-sized or appropriately chunked text as soon as the persona produces it. Do not wait for the entire answer when the underlying engine and TTS pipeline support incremental playback.

The current Marina tokenizer and streamed IPC are still useful for desktop clients, but an OVOS-native path should prefer the native `speak`/audio pipeline.

### Current TTS direction

The former `ovos-tts-plugin-piper` repository is archived and documents migration to `ovos-tts-plugin-phoonnx`. Marina's OVOS configuration therefore uses `ovos-tts-plugin-phoonnx` and Piper-compatible voice IDs through phoonnx.

## Audio UX states

Marina's UI should expose, at minimum:

- `ARMED` — microphone available, wake detector active;
- `LISTENING` — speech capture active;
- `THINKING` — request is being processed;
- `SPEAKING` — response audio playing;
- `FOLLOW_UP` — waiting for the next turn without a wake word;
- `ERROR` — audio/provider failure requiring user-visible recovery.

These are presentation states. The underlying source of truth is the OVOS event/message lifecycle.

## Privacy model

Default passive mode should be:

1. local wake-word inference;
2. no persistent pre-wake recording;
3. bounded in-memory audio buffering only;
4. utterance recording/transcription only after activation;
5. explicit diagnostic controls for enabling saved recordings;
6. network providers opt-in and clearly identified.

Dinkum Listener supports optional utterance saving for diagnostics. Marina should keep that disabled by default.

## Recommended Linux stack

```text
PipeWire / ALSA
      |
      v
OVOS microphone plugin
      |
      v
ovos-dinkum-listener
   |       |       |
 wake     VAD     STT
   |       |       |
   +-------+-------+
           |
           v
      ovos-messagebus
           |
     ovos-core/pipeline
        /         \
       /           \
Marina skills     Marina persona
                     |
              ovos-openai-plugin
                     |
               local LLM server
                     |
                ovos-audio
                     |
                 TTS/output
```

## Alternative deployment patterns

### Pure local

Wake, VAD, STT, LLM, TTS and persistence remain on the machine.

### Hybrid

Wake/VAD local, STT or LLM remote/self-hosted, TTS local.

### Satellite

OVOS listener runs on a lightweight microphone device and sends voice interactions to a more capable Marina/OVOS host. HiveMind is the natural future transport rather than inventing another network protocol.

## Implementation roadmap

### Phase A — OVOS migration (current)

- production ownership transferred to OVOS;
- Marina skill created;
- Marina persona created;
- Dinkum Listener configuration documented;
- OpenWakeWord integration documented;
- phoonnx TTS configuration used;
- standalone runtime retained as compatibility path.

### Phase B — installable local voice profile

- validate a specific Linux audio device profile;
- choose and package the local STT plugin/model;
- provide a tested `hey_marina` wake model;
- benchmark first-audio/turn latency;
- add privacy diagnostics.

### Phase C — desktop UX

- tray/overlay indicator;
- push-to-talk;
- headset/media-button integration;
- audible wake/stop chimes;
- GUI settings for wake sensitivity, follow-up timeout, voice and privacy mode.

### Phase D — advanced conversation

- robust echo cancellation;
- speaker-aware interruption;
- adaptive follow-up windows;
- multi-device sessions;
- optional HiveMind satellite support.
