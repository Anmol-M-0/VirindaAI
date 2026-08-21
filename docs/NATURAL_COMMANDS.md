# Natural Assistant Commands

## Purpose

Virinda has a small deterministic command parser that runs before the LLM/provider path. It is intentionally conservative: only commands with high-confidence structure are executed locally. Ambiguous requests continue through the normal provider flow.

## Supported commands

### Memory

```text
remember my favorite color is blue
remember that my timezone is Asia/Kolkata
my preferred editor is neovim
```

These create or update a durable local fact. In `private` mode they are rejected and are never persisted.

### Personalization

```text
call me Anmol
my name is Anmol
what's my name?
```

The name is stored in the local user profile. Profile persistence is disabled in `private` mode.

### Memory lookup

```text
what is my favorite color?
what's my timezone?
```

When an exact durable fact exists, Virinda can answer without invoking the LLM. Unknown or ambiguous questions continue through the normal provider path.

### Context modes

```text
go private mode
leave private mode
go quiet mode
leave quiet mode
go back to normal
```

Mode changes are local control operations and do not require the LLM.

### Reminders

```text
remind me to stretch in 10 minutes
remind me to call home in 2 hours
remind me to start the meeting at 8:30 pm
remind me to take a break at noon
```

Supported deterministic time forms are:

- `in N seconds`
- `in N minutes`
- `in N hours`
- `at HH:MM`
- `at H:MM AM/PM`
- `at H AM/PM`
- `at noon`
- `at midnight`

A clock time that has already passed today is scheduled for the next day. Relative times are calculated from the configured profile timezone when present, otherwise the host timezone.

## What is intentionally not parsed locally

Virinda does not attempt deterministic parsing for ambiguous natural language such as:

```text
remind me sometime tomorrow afternoon
schedule something for after lunch
remember what I told you about my trip
```

Those utterances continue through the normal provider/skill path instead of being guessed locally.

## Privacy behavior

Natural commands respect the active context policy:

- `normal`: durable memory/profile writes are allowed.
- `private`: durable memory/profile writes are rejected; private turns do not persist conversation transcripts or inject durable memory context.
- `quiet`: proactive notifications and scheduled routine execution are suppressed.

## Implementation boundary

The parser lives in `src/virinda/core/natural_commands.py` and returns a typed `LocalCommand`. `AssistantService` is the only component allowed to execute those commands so capability, privacy, persistence, and event semantics remain centralized.

## Testing

The grammar is covered by `tests/test_natural_commands.py`. Release validation also checks that the documentation exists and that environment/configuration references remain documented.

### Recurring reminders

Virinda can create local recurring reminders without invoking the LLM:

```text
remind me to stand up every day
remind me to stand up every weekday at 8 am
remind me to stretch every 2 hours
remind me to call home every week
```

Supported recurrence forms are `every day`, `every weekday`, `every week`, and `every N minutes/hours/days/weeks`. Daily and weekday schedules may include an `at HH:MM` or `at <hour> am/pm` time. The first firing is calculated in the profile timezone when configured, otherwise the host timezone.

Recurring reminder execution is persisted by the local alert scheduler and is suppressed in quiet mode.

### Provider and model selection

High-confidence provider/model changes can be made without an LLM turn:

```text
switch to echo provider
use openai provider
use model llama3.2
```

Unknown providers still fail explicitly rather than falling through to a different backend.

### Approval-aware web actions

Consequential web actions are never executed implicitly from a natural-language command. For example:

```text
open https://example.com
search the web for the latest OVOS release
```

Virinda returns a short-lived approval token. A trusted UI, CLI, or IPC caller must consume that token before the action executes. Read-only local capabilities remain available without approval.
