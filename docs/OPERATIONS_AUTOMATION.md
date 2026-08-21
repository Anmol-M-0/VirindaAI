# Automation Operations and Recovery

Virinda's automation worker is durable-aware and can report its runtime state without direct SQLite access.

## Health

`virinda status` exposes `job_broker` and `automation` health objects.

`automation.stale_runs` identifies queued/running executions older than the configured reconciliation window.

## Inspecting runs

```bash
virinda routines runs
virinda routines health
```

## Reconciliation

Mark stale queued/running runs as failed:

```bash
virinda routines reconcile 900
```

Requeue eligible stale runs after first marking the old execution terminal:

```bash
virinda routines reconcile 900 requeue
```

Requeue is only attempted for enabled routines. Existing terminal runs remain unchanged.

## Recovery model

A run has one authoritative terminal record. NATS redelivery of a run already marked `succeeded` is a no-op. Approval-paused runs remain `pending_approval` until explicitly resumed.

The reconciliation command is an operator recovery tool; it should be used after confirming that a worker is no longer processing the stale execution.
