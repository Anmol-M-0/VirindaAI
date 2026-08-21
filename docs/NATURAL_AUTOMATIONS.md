# Natural-language automations

## Goal

Marina can translate a small, deterministic subset of natural language into a reviewable automation plan. The plan is shown before persistence and is saved only after explicit confirmation.

## Examples

```text
create a routine every 2 hours, notify me to stretch
create a routine every weekday at 9 am, open https://example.com and notify me that the dashboard is ready
create a routine when I open VS Code, notify me to enter focus mode
create a routine at 8 pm, notify me to call home
```

## Safety model

The planner does not execute arbitrary natural-language instructions. Only known trigger and action forms are accepted. Browser actions are represented as approval-gated tool steps. Unknown actions are rejected instead of being guessed.

The lifecycle is:

```text
spoken/text request
  -> deterministic parser
  -> AutomationPlan
  -> user review
  -> explicit confirmation
  -> RoutineStore
  -> RoutineRunner
```

## Schedule semantics

Natural schedules are preserved as `schedule:` triggers rather than flattened into fixed 24-hour intervals. This matters for `every weekday at 9 am`, where a naive 86400-second interval would incorrectly execute on Saturday and Sunday.

The scheduler derives due occurrences from the supplied clock and the last successful run. This also makes schedule tests deterministic and supports future clock simulation.

## Supported actions

Current planner actions are intentionally narrow:

- `notify me ...` -> local notification
- `open/visit https://...` -> approval-gated browser action

Unsupported actions are rejected by the planner and continue through the normal assistant/provider path rather than being transformed into arbitrary automation.

## OVOS

OVOS remains responsible for voice capture and event delivery. The resulting routine plan is application-owned and can be triggered from text, OVOS utterances, application context, or scheduled events.
