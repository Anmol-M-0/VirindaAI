# Feature Implementation Matrix

This table is the operational companion to `FEATURE_CATALOG.md`.

| Feature | Implementation | External runtime | Persistent state | Requires hardware | Acceptance path |
|---|---|---|---:|---:|---|
| Memory | Native | None | Yes | No | Unit/integration tests |
| Context modes | Native | None | Ephemeral/policy | No | Unit/integration tests |
| Alerts | Native + OVOS adapter | Optional OVOS Alerts | Yes | No | Unit + OVOS bus smoke |
| Notifications | Native + OVOS adapter | Optional OVOS GUI/bus | Yes | No | Unit + bus smoke |
| Tools | Native | Host OS/browser | Audit only | Optional | Security tests |
| Automations | Native DSL | Optional tools | Yes | No | Unit tests |
| Desktop overlay | Native loopback | Browser | Ephemeral | No | HTTP/API tests |
| OVOS GUI | Adapter | `ovos-gui` | No | Optional display | Live OVOS test |
| Wake word | OVOS | Dinkum/OpenWakeWord | No | Microphone | Live hardware test |
| VAD | OVOS | Dinkum/Silero | No | Microphone | Live hardware test |
| STT | OVOS | Vosk or Whisper.cpp | Optional transcript | Microphone | Live hardware test |
| TTS | OVOS | selected TTS plugin | No | Speaker | Live hardware test |
| Meeting mode | Native | OVOS utterance feed | Yes | No | Unit + live event test |
| Screenshot | Native/host | Varies | Optional | Desktop | Host integration test |
| Camera | Adapter | V4L2 | Optional | Camera | Host integration test |
| Vision LLM | Provider adapter | Optional endpoint | No | No | HTTP contract test |
| Satellite | Adapter | Optional transport | No | No | protocol/security tests |
| Proactive briefing | Native + adapters | Optional alerts/context | Optional | Optional | deterministic policy tests |
| Speaker identification | Native primitive | Optional audio feed | Optional | Microphone | algorithm tests + live audio |

| Natural recurring reminders / provider switching / approval-aware tool requests | Marina native | Implemented | Hardware-independent |
