# OVOS GUI Integration

## Purpose

Virinda's production desktop/UI boundary is OpenVoiceOS, not a custom HTTP service.
OVOS installs `ovos-gui` as the GUI message-bus service, and GUI clients connect to that service; Virinda therefore publishes UI state through the OVOS MessageBus and accepts GUI commands through Virinda-owned bus messages. ([OVOS GUI](https://github.com/OpenVoiceOS/ovos-gui))

## Production path

```text
GTK / Qt / ovos-shell / other GUI client
                │
                ▼
           ovos-gui
                │
           OVOS MessageBus
                │
      ┌─────────┴─────────┐
      │                   │
  Virinda GUI events   Virinda GUI commands
      │                   │
      └─────────┬─────────┘
                ▼
        Virinda skill/service
                │
          Virinda feature plane
```

OVOS's current architecture defines `gui.value.set` and `gui.page.show` as GUI-facing bus operations and routes state through the session carrier. ([OVOS-GUI-1](https://github.com/OpenVoiceOS/architecture/blob/dev/CHANGELOG.md))

## Virinda-owned bus messages

### State publication

Virinda publishes state using `gui.value.set` under the `virinda.*` namespace. Examples:

```json
{"key":"virinda.status","value":"online"}
{"key":"virinda.listening","value":true}
{"key":"virinda.context_mode","value":"private"}
```

This keeps rendering technology out of Virinda. An OVOS GUI client decides how these values are rendered.

### GUI commands

The local GUI client sends:

```text
virinda.gui.command
```

with a payload shaped like:

```json
{
  "command": "routine_preview",
  "data": {
    "request_id": "abc-123",
    "params": {"id": "routine-id"}
  }
}
```

Virinda replies with:

```text
virinda.gui.response
```

The request is handled inside the existing Virinda capability/permission/routine service layer. The GUI never accesses SQLite directly.

## Security boundary

The OVOS MessageBus is a **local/private trust boundary**. The current `ovos-bus-client` documentation explicitly warns that the bus has no authentication and must not be exposed on a routable interface; remote access should use HiveMind instead. ([ovos-bus-client](https://github.com/OpenVoiceOS/ovos-bus-client))

Virinda therefore does not expose a GUI administration service over HTTP in production.

## HTTP overlay status

`virinda overlay` remains available only as an optional **localhost developer/diagnostics UI**. It is useful when OVOS GUI is unavailable or while debugging the standalone Virinda daemon. It is not part of the production OVOS control path.

The overlay must remain loopback-only unless Virinda gains an authenticated desktop gateway.

## Service ownership

| Concern | Owner |
|---|---|
| microphone / wake / VAD / STT | OVOS Dinkum Listener |
| TTS / playback | OVOS Audio |
| GUI service / client protocol | OVOS `ovos-gui` |
| message transport | OVOS MessageBus |
| persona / memory / automation / tools | Virinda |
| GUI state translation | Virinda `OVOSGuiBridge` |
| standalone diagnostics UI | optional Virinda localhost HTTP overlay |

OVOS explicitly supports running MessageBus, Core, Dinkum Listener, Audio, GUI, and PHAL as independently managed services, which is the deployment model Virinda uses. ([OVOS installation guide](https://github.com/OpenVoiceOS/OpenVoiceOS/blob/main/docs/installation.md))
