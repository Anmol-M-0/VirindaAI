# Troubleshooting

Start every incident with:

```bash
marina doctor --audio --services --json
python scripts/verify-ovos-compatibility.py
```

## Marina CLI works but voice does not

Check the runtime layers separately:

```bash
systemctl --user status marina-ovos-core.target
systemctl --user status marina-voice.target
journalctl --user -u marina-messagebus.service -e
journalctl --user -u marina-core.service -e
journalctl --user -u marina-listener.service -e
journalctl --user -u marina-audio.service -e
```

If core works but listener does not, do not debug the LLM first. Fix microphone/wake/VAD/STT first.

## Wake word never fires

1. Confirm the wake model file exists.
2. Confirm the model is referenced by OVOS configuration.
3. Run the audio/device diagnostic.
4. Test with a known-good microphone.
5. Inspect Dinkum Listener logs.
6. Tune the detector threshold only after verifying the microphone signal.

Do not lower thresholds indefinitely; false wake rates matter as much as missed wakes.

## Wake word fires but nothing is transcribed

The likely boundary is VAD or STT. Check listener state and selected STT plugin. In the stable profile Vosk is the conservative compatibility fallback; Marina's local-voice profile can add Whisper.cpp separately.

## Transcription works but no response

Test the application plane without audio:

```bash
python scripts/ovos-runtime-smoke.py "marina status" --expect "Marina is online"
```

If this fails, inspect OVOS Persona/provider configuration rather than the microphone.

## TTS does not play

Check:

- `marina-audio.service` state
- selected audio output device
- `ovos-audio` logs
- PipeWire/WirePlumber or ALSA state
- configured TTS plugin

Run:

```bash
marina doctor --audio
```

## The desktop overlay cannot connect

Check the Marina daemon/socket first:

```bash
systemctl --user status marinad.service
ls -l "$MARINA_SOCKET"
```

The socket should be a Unix socket with mode `0600`. The overlay should never open SQLite directly.

## OpenAI-compatible provider fails

Verify:

```bash
echo "$MARINA_OPENAI_BASE_URL"
echo "$MARINA_OPENAI_MODEL"
```

Do not print or log `MARINA_OPENAI_API_KEY`. Use provider diagnostics and a minimal deterministic request. For private/self-hosted endpoints, verify the endpoint is actually reachable and the configured model name exists.

## Memory appears to be missing

Check the current context mode first:

```bash
marina context
```

Private mode intentionally avoids durable transcript/memory persistence. Also check whether the queried content exists with the memory inspection API/CLI.

## Tool execution is denied

This is expected when a tool has a risk class requiring approval. Use the approval flow from the desktop UI or another trusted local client. Do not weaken the global policy to get one action through.

## Upgrade broke an older database

Marina uses additive SQLite migrations. Preserve a backup before investigating:

```bash
marina backup
```

Then inspect database health and migration logs. Do not manually delete the database unless data loss is acceptable.

## OVOS package conflicts

Do not install arbitrary latest versions of individual OVOS repositories. Recreate the environment using the pinned stable constraints and then add Marina-selected optional voice components. The OVOS release tracker explicitly provides constraint files to keep independently released components compatible.
