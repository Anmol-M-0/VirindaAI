# Routine Editor

## Purpose

Virinda exposes a loopback-only visual routine editor so users can manage automations without editing JSON, using a second automation engine, or bypassing the existing policy boundary.

## UI lifecycle

1. **Create** a routine with a name, trigger, action sequence, and optional approval/conflict flags.
2. **Preview** a saved routine to inspect expanded steps, conflicts, approvals, and expected side effects.
3. **Edit** the stored routine through the same service contract used by CLI and IPC clients.
4. **Disable** without deleting history.
5. **Delete** only when the user explicitly confirms in the UI.
6. **Run due** asks the existing scheduler to evaluate due time-based routines; it does not execute arbitrary user code.
7. **Recent runs** exposes the persisted execution ledger.

## Transport boundary

Production routine editing is an OVOS GUI client communicating through `ovos-gui` and the OVOS MessageBus. The Virinda localhost HTTP overlay remains an optional developer/diagnostics surface only; it does not define the production UI contract or access SQLite directly.

The production transport is OVOS GUI/MessageBus. The HTTP routes below are **developer diagnostics only** and are intentionally not part of the production UI contract.

### Developer diagnostics HTTP API

Read endpoints include:

- `GET /api/status`
- `GET /api/live-context`
- `GET /api/routines`
- `GET /api/routine-runs`

Mutation endpoints include:

- `POST /api/routine-save`
- `POST /api/routine-update`
- `POST /api/routine-preview`
- `POST /api/routine-disable`
- `POST /api/routine-delete`
- `POST /api/routine-run`

The overlay reuses the same conflict detection, preview, approval, retry, and run-ledger behavior as CLI, IPC, and OVOS flows.

## Security

The overlay is not a remote administration API. Keep the default `127.0.0.1` binding. Exposing it on a LAN should require an authenticated desktop gateway rather than changing the bind address casually.
