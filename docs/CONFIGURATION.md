# Configuration Reference

Virinda configuration is intentionally split between **environment variables**, **OVOS configuration**, and **local feature policy**. Do not put secrets in source-controlled JSON examples.

## Environment variables

| Variable | Default | Purpose | Sensitive |
|---|---|---|---|
| `VIRINDA_DATA_DIR` | `~/.local/share/virinda-ai` | Durable Virinda data and IPC socket | No |
| `VIRINDA_PROVIDER` | `echo` | Default provider name | No |
| `VIRINDA_MODEL` | `offline-demo` | Default model identifier | No |
| `VIRINDA_OPENAI_BASE_URL` | unset | OpenAI-compatible API base | No |
| `VIRINDA_OPENAI_API_KEY` | unset | API credential | **Yes** |
| `VIRINDA_OPENAI_MODEL` | unset | OpenAI-compatible model override | No |
| `VIRINDA_AUDIO_MODE` | `wake_word` | Standalone voice policy | No |
| `VIRINDA_WAKE_WORD` | `hey virinda` | Standalone wake phrase label | No |
| `VIRINDA_WAKE_THRESHOLD` | `0.5` | Standalone detector threshold | No |
| `VIRINDA_END_SILENCE_MS` | `750` | End-of-utterance silence threshold | No |
| `VIRINDA_FOLLOW_UP_WINDOW_MS` | `8000` | Follow-up listening window | No |
| `VIRINDA_SOCKET` | `<data-dir>/virinda.sock` | Unix IPC endpoint | No |
| `VIRINDA_TOOL_ROOTS` | `<data-dir>` | Extra filesystem roots allowed to tools | No |
| `VIRINDA_VENV` | project/user venv | Production virtualenv path | No |
| `VIRINDA_OVOS_PROFILE` | `stable` | OVOS package profile | No |
| `VIRINDA_OVOS_CONFIG_DIR` | system/user OVOS config | OVOS config location | No |
| `VIRINDA_OVOS_CONSTRAINTS` | checked-in stable constraints | Constraint source | No |
| `VIRINDA_OVOS_SKILL_DIR` | user OVOS skill directory | Skill installation destination | No |
| `VIRINDA_PERSONA_DIR` | user OVOS persona config | Persona config destination | No |
| `VIRINDA_WAKE_MODEL` | unset | Wake model file path | No |
| `VIRINDA_INSTALL_CONFIG` | unset/false | Allow first-boot config installation | No |
| `VIRINDA_INSTALL_SERVICES` | unset/true in installer | Install Virinda systemd units | No |
| `VIRINDA_AUTO_START` | unset/false | Enable/start configured targets | No |
| `VIRINDA_SYSTEMD_DIR` | user systemd directory | Unit installation destination | No |
| `VIRINDA_REMOVE_CONFIG` | unset/false | Remove Virinda-installed config during uninstall | No |
| `VIRINDA_REMOVE_PERSONA` | unset/false | Remove Virinda Persona config during uninstall | No |
| `VIRINDA_REMOVE_SKILL` | unset/false | Remove installed skill during uninstall | No |
| `VIRINDA_REMOVE_SERVICES` | unset/true in uninstall | Remove Virinda service units | No |
| `VIRINDA_JOB_BROKER` | `inprocess` | Background job backend (`inprocess` / `nats`) | No |
| `VIRINDA_NATS_URL` | unset | NATS server URL when the NATS backend is enabled | No |
| `VIRINDA_NATS_CREDS` | unset | NATS credentials file path | **Yes** |
| `VIRINDA_NATS_STREAM` | `virinda_jobs` | JetStream stream name | No |
| `VIRINDA_NATS_SUBJECT_PREFIX` | `virinda.jobs` | Subject namespace for Virinda background jobs | No |
| `VIRINDA_NATS_DURABLE` | `virinda-workers` | Durable JetStream consumer name | No |
| `VIRINDA_NATS_ACK_WAIT_SECONDS` | `120` | JetStream acknowledgement window before redelivery | No |
| `VIRINDA_NATS_MAX_DELIVER` | `5` | Maximum JetStream delivery attempts before terminal handling | No |
| `VIRINDA_NATS_MAX_ACK_PENDING` | `32` | Maximum unacknowledged jobs allowed for the worker consumer | No |
| `VIRINDA_STT_CLOUD_FALLBACK` | `0` | Enable opt-in cloud STT fallback when local STT is unavailable | No |
| `VIRINDA_BRIDGE_CMD` | `./virinda ovos bridge` | Command line invoked by OVOS supervisor to run Virinda bridge | No |

## Provider configuration

### Offline provider

```bash
export VIRINDA_PROVIDER=echo
export VIRINDA_MODEL=offline-demo
```

Use this for development, smoke tests, and deterministic CI.

### OpenAI-compatible provider

```bash
export VIRINDA_PROVIDER=openai
export VIRINDA_OPENAI_BASE_URL=https://example.invalid/v1
export VIRINDA_OPENAI_API_KEY=...
export VIRINDA_OPENAI_MODEL=...
```

The provider is deliberately behind a protocol/router boundary so another compatible server can be substituted without changing Virinda's application layer.

## Tool roots

`VIRINDA_TOOL_ROOTS` is a colon-separated list of additional filesystem roots. The default write scope is Virinda's own data directory. Tool access must remain explicitly bounded; do not point the variable at `/`, `/home`, or other broad roots unless the deployment intentionally accepts that authority.

## OVOS configuration ownership

Virinda owns product-level configuration such as context modes, memory policy, tool permissions, and feature flags. OVOS owns the voice runtime configuration: listener, wake word, VAD, STT, TTS, audio devices, GUI, PHAL, and message-bus services.

Do not duplicate listener or audio configuration into Virinda environment variables in production. The standalone `VIRINDA_AUDIO_*` settings exist for the compatibility runtime and unit tests.

### Background job broker

`VIRINDA_JOB_BROKER=inprocess` is the current default and requires no broker service. For durable background work, set `VIRINDA_JOB_BROKER=nats`, `VIRINDA_NATS_URL`, and authenticated credentials. Install the optional `job-backbone` extra. The in-process broker remains the default for development/test installations.

## Configuration validation

Use:

```bash
virinda doctor
virinda doctor --audio --services
python scripts/verify-ovos-compatibility.py
```

A missing optional service should be reported as missing/disabled, not silently treated as available.
