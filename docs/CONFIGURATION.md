# Configuration Reference

Marina configuration is intentionally split between **environment variables**, **OVOS configuration**, and **local feature policy**. Do not put secrets in source-controlled JSON examples.

## Environment variables

| Variable | Default | Purpose | Sensitive |
|---|---|---|---|
| `MARINA_DATA_DIR` | `~/.local/share/marina-ai` | Durable Marina data and IPC socket | No |
| `MARINA_PROVIDER` | `echo` | Default provider name | No |
| `MARINA_MODEL` | `offline-demo` | Default model identifier | No |
| `MARINA_OPENAI_BASE_URL` | unset | OpenAI-compatible API base | No |
| `MARINA_OPENAI_API_KEY` | unset | API credential | **Yes** |
| `MARINA_OPENAI_MODEL` | unset | OpenAI-compatible model override | No |
| `MARINA_AUDIO_MODE` | `wake_word` | Standalone voice policy | No |
| `MARINA_WAKE_WORD` | `hey marina` | Standalone wake phrase label | No |
| `MARINA_WAKE_THRESHOLD` | `0.5` | Standalone detector threshold | No |
| `MARINA_END_SILENCE_MS` | `750` | End-of-utterance silence threshold | No |
| `MARINA_FOLLOW_UP_WINDOW_MS` | `8000` | Follow-up listening window | No |
| `MARINA_SOCKET` | `<data-dir>/marina.sock` | Unix IPC endpoint | No |
| `MARINA_TOOL_ROOTS` | `<data-dir>` | Extra filesystem roots allowed to tools | No |
| `MARINA_VENV` | project/user venv | Production virtualenv path | No |
| `MARINA_OVOS_PROFILE` | `stable` | OVOS package profile | No |
| `MARINA_OVOS_CONFIG_DIR` | system/user OVOS config | OVOS config location | No |
| `MARINA_OVOS_CONSTRAINTS` | checked-in stable constraints | Constraint source | No |
| `MARINA_OVOS_SKILL_DIR` | user OVOS skill directory | Skill installation destination | No |
| `MARINA_PERSONA_DIR` | user OVOS persona config | Persona config destination | No |
| `MARINA_WAKE_MODEL` | unset | Wake model file path | No |
| `MARINA_INSTALL_CONFIG` | unset/false | Allow first-boot config installation | No |
| `MARINA_INSTALL_SERVICES` | unset/true in installer | Install Marina systemd units | No |
| `MARINA_AUTO_START` | unset/false | Enable/start configured targets | No |
| `MARINA_SYSTEMD_DIR` | user systemd directory | Unit installation destination | No |
| `MARINA_REMOVE_CONFIG` | unset/false | Remove Marina-installed config during uninstall | No |
| `MARINA_REMOVE_PERSONA` | unset/false | Remove Marina Persona config during uninstall | No |
| `MARINA_REMOVE_SKILL` | unset/false | Remove installed skill during uninstall | No |
| `MARINA_REMOVE_SERVICES` | unset/true in uninstall | Remove Marina service units | No |
| `MARINA_JOB_BROKER` | `inprocess` | Background job backend (`inprocess` / `nats`) | No |
| `MARINA_NATS_URL` | unset | NATS server URL when the NATS backend is enabled | No |
| `MARINA_NATS_CREDS` | unset | NATS credentials file path | **Yes** |
| `MARINA_NATS_STREAM` | `marina_jobs` | JetStream stream name | No |
| `MARINA_NATS_SUBJECT_PREFIX` | `marina.jobs` | Subject namespace for Marina background jobs | No |
| `MARINA_NATS_DURABLE` | `marina-workers` | Durable JetStream consumer name | No |
| `MARINA_NATS_ACK_WAIT_SECONDS` | `120` | JetStream acknowledgement window before redelivery | No |
| `MARINA_NATS_MAX_DELIVER` | `5` | Maximum JetStream delivery attempts before terminal handling | No |
| `MARINA_NATS_MAX_ACK_PENDING` | `32` | Maximum unacknowledged jobs allowed for the worker consumer | No |

## Provider configuration

### Offline provider

```bash
export MARINA_PROVIDER=echo
export MARINA_MODEL=offline-demo
```

Use this for development, smoke tests, and deterministic CI.

### OpenAI-compatible provider

```bash
export MARINA_PROVIDER=openai
export MARINA_OPENAI_BASE_URL=https://example.invalid/v1
export MARINA_OPENAI_API_KEY=...
export MARINA_OPENAI_MODEL=...
```

The provider is deliberately behind a protocol/router boundary so another compatible server can be substituted without changing Marina's application layer.

## Tool roots

`MARINA_TOOL_ROOTS` is a colon-separated list of additional filesystem roots. The default write scope is Marina's own data directory. Tool access must remain explicitly bounded; do not point the variable at `/`, `/home`, or other broad roots unless the deployment intentionally accepts that authority.

## OVOS configuration ownership

Marina owns product-level configuration such as context modes, memory policy, tool permissions, and feature flags. OVOS owns the voice runtime configuration: listener, wake word, VAD, STT, TTS, audio devices, GUI, PHAL, and message-bus services.

Do not duplicate listener or audio configuration into Marina environment variables in production. The standalone `MARINA_AUDIO_*` settings exist for the compatibility runtime and unit tests.

### Background job broker

`MARINA_JOB_BROKER=inprocess` is the current default and requires no broker service. For durable background work, set `MARINA_JOB_BROKER=nats`, `MARINA_NATS_URL`, and authenticated credentials. Install the optional `job-backbone` extra. The in-process broker remains the default for development/test installations.

## Configuration validation

Use:

```bash
marina doctor
marina doctor --audio --services
python scripts/verify-ovos-compatibility.py
```

A missing optional service should be reported as missing/disabled, not silently treated as available.
