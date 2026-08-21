# Operations

## State directory

Set `MARINA_DATA_DIR` to isolate state:

```bash
export MARINA_DATA_DIR="$HOME/.local/share/marina-ai"
```

The database is `marina.sqlite3`.

## CLI diagnostics

```bash
marina status
marina providers
marina ask "hello"
marina history
marina events
marina sessions
marina cancel --reason shutdown
marina clear
marina backup "$HOME/.local/share/marina-ai/backups/marina.sqlite3"
```

## systemd user service

Install `deploy/systemd/marinad.service` as a user unit and adapt `ExecStart` to the installed binary path. The service is intentionally a user process and should start with the graphical/PipeWire session.

## Backup

SQLite is the only durable state in this release. For a cold backup, stop the daemon and copy the database plus its SQLite sidecar files. For a live application, use SQLite's backup facilities rather than copying an open WAL database blindly.

## Recovery

A restart recovers persisted messages/events. The runtime creates no fake continuation token: any in-flight generation from the previous process is considered cancelled by process death.

## Troubleshooting

If `marina` reports `provider not configured`, check `MARINA_PROVIDER` and, for the OpenAI-compatible adapter, all three `MARINA_OPENAI_*` variables. The `echo` provider is always the safe offline fallback.


## Health and backup

`marina status` performs a SQLite integrity check and reports session/message/event counts. Prefer `marina backup <path>` for live backups; it uses SQLite's backup API instead of copying a live WAL database.

## Daemon IPC

Start the long-lived daemon with:

```bash
marinad
```

It creates `$MARINA_DATA_DIR/marina.sock` with filesystem mode `0600`. A desktop client should
use `marina.interfaces.ipc.LocalRPCClient` rather than opening the SQLite database or embedding
its own application state machine. The socket is removed during normal daemon shutdown.

A minimal client call looks like:

```python
from pathlib import Path
from marina.interfaces.ipc import LocalRPCClient

client = LocalRPCClient(Path.home() / ".local/share/marina-ai/marina.sock")
print(client.call("ask", text="hello"))
```

## OVOS deployment checks

The local deployment now has a deployment-aware doctor:

```bash
.venv/bin/marina doctor
.venv/bin/marina doctor --services
.venv/bin/marina doctor --json
```

`doctor` validates the Marina/OVOS Python modules, configuration templates, Persona configuration, STT configuration, and wake-model path. `--services` additionally checks the four Marina-managed user units when `systemctl --user` is available. `--json` is intended for provisioning scripts and CI.

The recommended install path uses a dedicated virtual environment and the current OpenVoiceOS stable constraints. OVOS documents the stable constraints file as the mechanism for keeping the component versions compatible; individual listener/audio services can also be installed and managed independently. See `docs/REFERENCES.md` for upstream links.

## Audio diagnostics

On a Linux desktop, inspect the PipeWire/WirePlumber and ALSA topology without changing device state:

```bash
python -m marina doctor --audio
python -m marina doctor --json --audio
```

`wpctl status` is used when available to inspect the live PipeWire graph, while `arecord -l` and `aplay -l` provide the ALSA capture/playback inventory. This is deliberately read-only; use `wpctl` directly when changing defaults is required. WirePlumber documents `wpctl status`, source/sink listing, and the `@DEFAULT_SOURCE@` / `@DEFAULT_SINK@` identifiers for runtime device inspection. https://pipewire.pages.freedesktop.org/wireplumber/tools/wpctl.html


## NATS JetStream job backbone

Marina's durable background-job backend is NATS JetStream. The base installation remains broker-free; install the optional Python client with:

```bash
pip install -e '.[job-backbone]'
```

Provision a NATS server with JetStream enabled, then configure:

```bash
export MARINA_JOB_BROKER=nats
export MARINA_NATS_URL=nats://127.0.0.1:4222
export MARINA_NATS_STREAM=marina_jobs
export MARINA_NATS_SUBJECT_PREFIX=marina.jobs
export MARINA_NATS_DURABLE=marina-workers
export MARINA_NATS_ACK_WAIT_SECONDS=120
export MARINA_NATS_MAX_DELIVER=5
export MARINA_NATS_MAX_ACK_PENDING=32
```

Use `marina doctor --nats` to validate the client/configuration layer. A live connectivity check belongs in the provisioned-host acceptance test because this development environment does not include a NATS server.

## NATS live acceptance

After provisioning NATS JetStream, run:

```bash
python scripts/nats-acceptance.py
```

A result of `0` means the publish/consume/ack path passed. A result of `2` means the environment is not provisioned or reachable and must not be confused with a Marina source-code failure.
