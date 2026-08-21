# OVOS GUI Integration

## Purpose

Marina's production desktop/UI boundary is OpenVoiceOS, not a custom HTTP service.
OVOS installs `ovos-gui` as the GUI message-bus service, and GUI clients connect to that service; Marina therefore publishes UI state through the OVOS MessageBus and accepts GUI commands through Marina-owned bus messages. ([OVOS GUI](https://github.com/OpenVoiceOS/ovos-gui))

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
  Marina GUI events   Marina GUI commands
      │                   │
      └─────────┬─────────┘
                ▼
        Marina skill/service
                │
          Marina feature plane
```

OVOS's current architecture defines `gui.value.set` and `gui.page.show` as GUI-facing bus operations and routes state through the session carrier. ([OVOS-GUI-1](https://github.com/OpenVoiceOS/architecture/blob/dev/CHANGELOG.md))

## Marina-owned bus messages

### State publication

Marina publishes state using `gui.value.set` under the `marina.*` namespace. Examples:

```json
{"key":"marina.status","value":"online"}
{"key":"marina.listening","value":true}
{"key":"marina.context_mode","value":"private"}
```

This keeps rendering technology out of Marina. An OVOS GUI client decides how these values are rendered.

### GUI commands

The local GUI client sends:

```text
marina.gui.command
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

Marina replies with:

```text
marina.gui.response
```

The request is handled inside the existing Marina capability/permission/routine service layer. The GUI never accesses SQLite directly.

## Security boundary

The OVOS MessageBus is a **local/private trust boundary**. The current `ovos-bus-client` documentation explicitly warns that the bus has no authentication and must not be exposed on a routable interface; remote access should use HiveMind instead. ([ovos-bus-client](https://github.com/OpenVoiceOS/ovos-bus-client))

Marina therefore does not expose a GUI administration service over HTTP in production.

## HTTP overlay status

`marina overlay` remains available only as an optional **localhost developer/diagnostics UI**. It is useful when OVOS GUI is unavailable or while debugging the standalone Marina daemon. It is not part of the production OVOS control path.

The overlay must remain loopback-only unless Marina gains an authenticated desktop gateway.

## Service ownership

| Concern | Owner |
|---|---|
| microphone / wake / VAD / STT | OVOS Dinkum Listener |
| TTS / playback | OVOS Audio |
| GUI service / client protocol | OVOS `ovos-gui` |
| message transport | OVOS MessageBus |
| persona / memory / automation / tools | Marina |
| GUI state translation | Marina `OVOSGuiBridge` |
| standalone diagnostics UI | optional Marina localhost HTTP overlay |

OVOS explicitly supports running MessageBus, Core, Dinkum Listener, Audio, GUI, and PHAL as independently managed services, which is the deployment model Marina uses. ([OVOS installation guide](https://github.com/OpenVoiceOS/OpenVoiceOS/blob/main/docs/installation.md))
