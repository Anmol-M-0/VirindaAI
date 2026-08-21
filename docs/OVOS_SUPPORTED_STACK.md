# Virinda OVOS Supported Stack

**Snapshot:** 2026-08-20

## Verdict

OVOS is a good architectural choice for Virinda because it already provides the hard real-time voice lifecycle and a plugin/message-bus contract. The mistake would be treating all repositories in the OVOS GitHub organization as equally production-ready or mutually compatible.

Virinda therefore has a deliberately small supported stack. The **OVOS stable constraints file is authoritative for the core runtime**; Virinda only adds plugins that are either already in that lock or explicitly classified as separately validated add-ons.

## Tier A — Production baseline

These are the components Virinda should depend on for the default Linux desktop profile. They are part of the upstream stable constraints channel.

| Project | Role | Current stable range | Virinda status |
|---|---|---:|---|
| `ovos-core` | assistant runtime / skills / intents | `>=1.3.1,<1.4.0` | Required |
| `ovos-dinkum-listener` | microphone → wake → VAD → STT lifecycle | `>=0.4.0,<0.5.0` | Required |
| `ovos-audio` | audio/TTS playback service | `>=0.4.0,<0.5.0` | Required |
| `ovos-plugin-manager` | plugin discovery/loading | `>=0.9.0,<0.10.0` | Required |
| `ovos-persona` | fallback conversational persona | `>=0.6.23,<0.7.0` | Required |
| `ovos-openai-plugin` | OpenAI-compatible LLM solver | `>=2.0.3,<2.1.0` | Required |
| `ovos-messagebus` | service IPC | `>=0.0.10,<0.1.0` | Required |
| `ovos-bus-client` | Python bus client | `>=1.3.4,<1.4.0` | Required |
| `ovos-microphone-plugin-alsa` | Linux capture | `>=0.1.2,<0.2.0` | Recommended |
| `ovos-audio-plugin-mpv` | local playback backend | `>=0.2.1,<0.3.0` | Recommended |
| `ovos-ww-plugin-openwakeword` | wake word | `>=0.4.1,<0.5.0` | Recommended |
| `ovos-vad-plugin-silero` | speech activity detection | `>=0.0.5,<0.1.0` | Recommended |

OVOS publishes these ranges together specifically to avoid cross-repository dependency drift. Virinda should install the upstream stable constraints as a single unit, not resolve these repositories independently.

## Tier B — Stable local speech option

`ovos-stt-plugin-vosk` is also present in the upstream stable constraints at `>=0.2.3,<0.3.0`. It is the conservative local STT fallback for a machine where reproducibility matters more than Whisper-level transcription quality.

This is the default **compatibility fallback**, not necessarily Virinda's best-quality STT.

## Tier C — Virinda-validated add-ons

These are useful for a premium local voice experience but are not part of the upstream stable lock and therefore must be tested independently.

| Project | Role | Status |
|---|---|---|
| `ovos-stt-plugin-whispercpp==0.0.1` | higher-quality local STT | Add-on; not upstream-stable |
| `phoonnx==1.3.3` | local neural TTS / Piper migration target | Add-on; not upstream-stable |

The old `ovos-tts-plugin-piper` must not be used as a new dependency: its repository was archived on 2026-06-11 and directs users to `phoonnx`. ([upstream](https://github.com/OpenVoiceOS/ovos-tts-plugin-piper))

## Tier D — Do not use for the production profile

These are not necessarily bad projects. They simply should not silently become Virinda production dependencies.

### New OVOS agent / Persona generation

The newer `ovos-chat-openai-plugin` path currently targets a newer Persona/Plugin Manager generation than the stable OVOS lock. Virinda keeps it explicitly experimental.

### Pre-release listener/audio/core releases

Dinkum Listener currently has newer `0.x` alpha releases on GitHub while the stable channel continues to constrain it to the `0.4.x` line. Virinda stays on the stable constraint instead of chasing the latest repository tag.

### Archived/deprecated voice plugins

Do not introduce archived Piper or Mimic3 integrations for a new Virinda deployment. They may remain useful for legacy environments, but they are not the forward production choice.

### Arbitrary GitHub `main` installs

Never mix `main` branches from several OVOS repositories in production. A single repository can change its plugin ABI before the rest of the ecosystem catches up.

## Recommended Virinda profiles

### `production-local`

- OVOS stable constraints
- ALSA microphone on Linux
- Dinkum Listener
- OpenWakeWord
- Silero VAD
- Vosk STT as compatibility fallback
- Persona + legacy OpenAI solver
- local OpenAI-compatible LLM such as Ollama/llama.cpp/vLLM
- `ovos-audio` + MPV output
- `phoonnx` only after explicit local-voice validation

### `quality-local`

Same as `production-local`, but use Whisper.cpp instead of Vosk STT and phoonnx for local TTS. This is Virinda's **preferred quality profile**, but it is not claimed to be upstream-OVOS stable until tested against the target machine and pinned environment.

### `experimental-agent`

Use only for evaluating the newer OVOS agent/Persona generation. It must be isolated in its own virtualenv.

## Decision rule

For every new OVOS dependency, Virinda asks:

1. Is it in the upstream stable constraints?
2. Is there a released version in that stable range?
3. Does it have an active test suite / recent maintenance?
4. Does it introduce a new plugin ABI or framework generation?
5. Can Virinda exercise it in the compatibility harness?

If the answer to any of the last three is unfavorable, the dependency stays out of the production profile.

## Sources

- OVOS release constraints: <https://github.com/OpenVoiceOS/OpenVoiceOS/blob/main/constraints-stable.txt>
- OVOS installation guide: <https://github.com/OpenVoiceOS/OpenVoiceOS/blob/main/docs/installation.md>
- OVOS core: <https://github.com/OpenVoiceOS/ovos-core>
- Dinkum Listener: <https://github.com/OpenVoiceOS/ovos-dinkum-listener>
- Audio: <https://github.com/OpenVoiceOS/ovos-audio>
- Plugin Manager: <https://github.com/OpenVoiceOS/ovos-plugin-manager>
- OpenAI plugin: <https://github.com/OpenVoiceOS/ovos-openai-plugin>
- Stable OpenWakeWord plugin: <https://github.com/OpenVoiceOS/ovos-ww-plugin-openwakeword>
- Stable Silero VAD plugin: <https://github.com/OpenVoiceOS/ovos-vad-plugin-silero>
- Stable Vosk STT plugin: <https://github.com/OpenVoiceOS/ovos-stt-plugin-vosk>
