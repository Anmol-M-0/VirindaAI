# Operations

## State directory

Set `VIRINDA_DATA_DIR` to isolate state:

```bash
export VIRINDA_DATA_DIR="$HOME/.local/share/virinda-ai"
```

The database is `virinda.sqlite3`.

## CLI diagnostics

```bash
virinda status
virinda providers
virinda ask "hello"
virinda history
virinda events
virinda sessions
virinda cancel --reason shutdown
virinda clear
virinda backup "$HOME/.local/share/virinda-ai/backups/virinda.sqlite3"
```

## systemd user service

Install `deploy/systemd/virindad.service` as a user unit and adapt `ExecStart` to the installed binary path. The service is intentionally a user process and should start with the graphical/PipeWire session.

## Backup

SQLite is the only durable state in this release. For a cold backup, stop the daemon and copy the database plus its SQLite sidecar files. For a live application, use SQLite's backup facilities rather than copying an open WAL database blindly.

## Recovery

A restart recovers persisted messages/events. The runtime creates no fake continuation token: any in-flight generation from the previous process is considered cancelled by process death.

## Troubleshooting

If `virinda` reports `provider not configured`, check `VIRINDA_PROVIDER` and, for the OpenAI-compatible adapter, all three `VIRINDA_OPENAI_*` variables. The `echo` provider is always the safe offline fallback.


## Health and backup

`virinda status` performs a SQLite integrity check and reports session/message/event counts. Prefer `virinda backup <path>` for live backups; it uses SQLite's backup API instead of copying a live WAL database.

## Daemon IPC

Start the long-lived daemon with:

```bash
virindad
```

It creates `$VIRINDA_DATA_DIR/virinda.sock` with filesystem mode `0600`. A desktop client should
use `virinda.interfaces.ipc.LocalRPCClient` rather than opening the SQLite database or embedding
its own application state machine. The socket is removed during normal daemon shutdown.

A minimal client call looks like:

```python
from pathlib import Path
from virinda.interfaces.ipc import LocalRPCClient

client = LocalRPCClient(Path.home() / ".local/share/virinda-ai/virinda.sock")
print(client.call("ask", text="hello"))
```

## OVOS deployment checks

The local deployment now has a deployment-aware doctor:

```bash
.venv/bin/virinda doctor
.venv/bin/virinda doctor --services
.venv/bin/virinda doctor --json
```

`doctor` validates the Virinda/OVOS Python modules, configuration templates, Persona configuration, STT configuration, and wake-model path. `--services` additionally checks the four Virinda-managed user units when `systemctl --user` is available. `--json` is intended for provisioning scripts and CI.

The recommended install path uses a dedicated virtual environment and the current OpenVoiceOS stable constraints. OVOS documents the stable constraints file as the mechanism for keeping the component versions compatible; individual listener/audio services can also be installed and managed independently. See `docs/REFERENCES.md` for upstream links.

## Audio diagnostics

On a Linux desktop, inspect the PipeWire/WirePlumber and ALSA topology without changing device state:

```bash
python -m virinda doctor --audio
python -m virinda doctor --json --audio
```

`wpctl status` is used when available to inspect the live PipeWire graph, while `arecord -l` and `aplay -l` provide the ALSA capture/playback inventory. This is deliberately read-only; use `wpctl` directly when changing defaults is required. WirePlumber documents `wpctl status`, source/sink listing, and the `@DEFAULT_SOURCE@` / `@DEFAULT_SINK@` identifiers for runtime device inspection. https://pipewire.pages.freedesktop.org/wireplumber/tools/wpctl.html


## NATS JetStream job backbone

Virinda's durable background-job backend is NATS JetStream. The base installation remains broker-free; install the optional Python client with:

```bash
pip install -e '.[job-backbone]'
```

Provision a NATS server with JetStream enabled, then configure:

```bash
export VIRINDA_JOB_BROKER=nats
export VIRINDA_NATS_URL=nats://127.0.0.1:4222
export VIRINDA_NATS_STREAM=virinda_jobs
export VIRINDA_NATS_SUBJECT_PREFIX=virinda.jobs
export VIRINDA_NATS_DURABLE=virinda-workers
export VIRINDA_NATS_ACK_WAIT_SECONDS=120
export VIRINDA_NATS_MAX_DELIVER=5
export VIRINDA_NATS_MAX_ACK_PENDING=32
```

Use `virinda doctor --nats` to validate the client/configuration layer. A live connectivity check belongs in the provisioned-host acceptance test because this development environment does not include a NATS server.

## NATS live acceptance

After provisioning NATS JetStream, run:

```bash
python scripts/nats-acceptance.py
```

A result of `0` means the publish/consume/ack path passed. A result of `2` means the environment is not provisioned or reachable and must not be confused with a Virinda source-code failure.
