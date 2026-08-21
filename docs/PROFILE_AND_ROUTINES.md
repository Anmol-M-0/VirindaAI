# User Profiles and Scheduled Routines

## User profiles

Virinda stores a single local user profile in SQLite. The profile is deliberately small and explicit:

- `display_name`
- `locale`
- `timezone`
- `preferred_provider`
- `preferred_model`
- `preferred_voice`

Profile values are inserted into provider context only when configured. The default profile is empty; Virinda does not invent a user identity or inject a default locale into prompts.

Private mode blocks profile writes. Clearing the profile removes the durable record but does not erase conversation history or other feature stores.

### CLI

```bash
virinda profile
virinda profile update --json '{"display_name":"Virinda User","timezone":"Asia/Kolkata"}'
virinda profile clear
```

### IPC

- `profile`
- `profile_update`
- `profile_clear`

`profile_update` expects a `changes` object.

## Scheduled routines

Routines use a deliberately constrained action DSL. Time-based routines use a one-shot trigger:

```text
at:<unix timestamp>
```

A scheduled routine executes once when its due time is reached and is then disabled. This makes the behavior deterministic and avoids accidental repeated execution.

Supported action kinds remain deliberately narrow:

- `notify:<title>|<body>`
- `tool:<tool-name>|<json-arguments>` (subject to Virinda's normal tool approval policy)

Quiet mode suppresses routine execution. Routine execution errors are emitted as feature events and do not terminate the main assistant service.

### CLI

```bash
virinda routines
virinda routines schedule morning 1770000000 'notify:Good morning|Stand up and stretch'
virinda routines run-due
```

### IPC

- `routines`
- `routine_save`
- `routine_schedule`
- `routine_run_due`
- `routine_delete`

## Design rules

The user profile is personalization data, not instruction data. It should never override higher-priority system/security policy.

Scheduled routines are local automation. They do not create arbitrary shell commands, bypass tool approvals, or disable quiet/private modes.

## Automation engine (v0.26.3)

Routines are now a small declarative automation engine rather than a single timer callback.

### Triggers

```text
at:<unix timestamp>
every:<seconds>
keyword:<text>
event:<event name>
app:<application substring>
```

Examples:

```text
at:1797930000
 every:3600
keyword:focus mode
event:voice.utterance
app:code
```

The `every:` trigger stores its next due time back into the routine after a successful run. `at:` is one-shot.

### Actions

Multiple actions can be chained with `||`:

```text
notify:Morning|Good morning||notify:Agenda|Review the calendar
```

Tool actions are explicit:

```text
tool:system.info|{}
```

An approval checkpoint can be required for a step:

```text
approve:tool:browser.open|{"url":"https://example.com"}
```

The routine engine never executes shell strings. Every tool step still enters Virinda's normal capability and approval boundary.

### Retries

Each routine can define:

- `retry_limit` from 0 through 10
- `retry_backoff_seconds` from 0 through 300
- `require_approval`

Every execution is recorded in `routine_runs`, including status, attempt count, timestamps, errors, and whether approval was required.

### Approval flow

A consequential routine can pause in `pending_approval` instead of executing a tool. The UI/CLI can then approve the specific run and Virinda resumes it through the same permission boundary.

The raw approval token is never required to be spoken or rendered to the user.

### CLI

```bash
virinda routines list
virinda routines runs
virinda routines event voice.utterance '{"text":"hello"}'
virinda routines approve <run-id>
```

### IPC

- `routine_save`
- `routine_schedule`
- `routine_run_due`
- `routine_event`
- `routine_runs`
- `routine_approve`
- `routine_delete`

### Event sources

The application currently forwards these useful events into the automation layer:

- `voice.utterance`
- `desktop.context`
- feature events emitted by the local runtime

OVOS listener/audio events are bridged into Virinda's live context first; event-driven routines can consume those normalized application events without depending directly on an OVOS message-bus topic name.
