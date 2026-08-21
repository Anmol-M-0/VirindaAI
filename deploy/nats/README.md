# Virinda NATS JetStream deployment

Virinda uses NATS JetStream as its only durable job backend. OVOS MessageBus remains the interactive assistant bus.

## Single-node development server

The checked-in `virinda-nats.conf` is a simple single-node configuration intended for a local development/desktop deployment.

Start a NATS server with JetStream enabled, then configure Virinda:

```bash
export VIRINDA_JOB_BROKER=nats
export VIRINDA_NATS_URL=nats://127.0.0.1:4222
export VIRINDA_NATS_STREAM=virinda_jobs
export VIRINDA_NATS_SUBJECT_PREFIX=virinda.jobs
export VIRINDA_NATS_DURABLE=virinda-workers
```

## Live acceptance

Run:

```bash
python scripts/nats-acceptance.py
```

Exit codes:

- `0`: NATS JetStream publish/consume/ack path passed.
- `2`: NATS is not provisioned or is unreachable. This is not a source-code failure.
- `1`: NATS was reachable but the acceptance contract failed.

The acceptance test uses a temporary stream and subject and does not touch Virinda's production stream.

## Production guidance

For networked deployments, enable TLS and use scoped NATS credentials. Keep JetStream data on durable storage and back it up according to the host's disaster-recovery policy. Do not expose the NATS port directly to an untrusted network.

## Supported version target

Virinda currently targets NATS Server 2.14.x with JetStream enabled. The compatibility target is NATS Server 2.14.x; the current recommended patch is 2.14.5. Verify the installed server with `nats-server -v`. The Python client target is `nats-py` 2.15.x.

For a durable crash/recovery check, run:

```bash
python scripts/nats-durability-acceptance.py
```

This simulates a worker crash by closing the first client without acknowledging the message, then reconnects with the same durable consumer and requires JetStream to redeliver the job before acknowledging it.
