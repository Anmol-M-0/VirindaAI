# Automation Preview and Dry Run

Marina can explain a routine without executing it. This is the review boundary for scheduled and event-driven automation.

## CLI

```bash
marina routines preview <routine-id>
```

## IPC

Call `routine_preview` with `{ "id": "...", "trigger_context": {} }`.

## What preview guarantees

Preview is side-effect free. It does not:

- create a `routine_runs` record
- emit notifications
- invoke tools
- issue approval tokens
- modify the routine

The returned object describes the routine, expanded steps, approval requirements, conflicts, and whether the routine would currently be eligible to execute.

## Conversational form

Marina also accepts:

```text
preview the routine Morning Review
what will the routine Morning Review do?
dry run routine Morning Review
```

The conversational form is intentionally concise and human-readable; the CLI/IPC forms expose the full structured explanation.

## Conflicts

A routine is considered conflicting when another enabled routine has the same normalized trigger. Preview reports those conflicts and marks `will_execute` false. Saving or updating a routine still requires explicit conflict override when a conflict exists.

## Context interpolation

Preview uses the same bounded interpolation rules as execution. Supported values include profile, mode, desktop signals, and the current trigger context. Unknown variables resolve to an empty string.
