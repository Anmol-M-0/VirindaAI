# Automation lifecycle

Virinda automations are persistent, reviewable objects rather than arbitrary scripts.

## Lifecycle

```text
create
  -> plan
  -> review
  -> save
  -> schedule/event trigger
  -> run ledger
  -> success / retry / approval / failure
  -> edit / disable / delete
```

## Conflict detection

Virinda rejects creation or edits that reuse an active trigger unless the caller explicitly sets `allow_conflict=true`. This prevents accidental duplicate schedules and duplicate notifications.

## Editing

Natural-language examples:

```text
change the routine Morning Review to every weekday at 10 am, notify me to review the dashboard
disable the routine Morning Review
delete the routine Morning Review
```

The edit operation re-plans the trigger/actions through the same deterministic automation grammar used for creation.

## Context interpolation

Action payloads may contain a small, read-only placeholder syntax:

```text
{{profile.display_name}}
{{profile.timezone}}
{{context.mode}}
{{desktop.active_application}}
{{now.iso}}
```

Unknown paths resolve to an empty string. This prevents routines from becoming a general-purpose templating or code-execution system.

## Approval checkpoints

External/destructive actions remain gated. A routine can pause in `pending_approval`; the run ledger retains the state, and the same run can be resumed once the approval is granted.
