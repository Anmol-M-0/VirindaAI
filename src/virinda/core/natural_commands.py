from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from datetime import time as dt_time
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo


def _resolve_timezone(
    timezone: str | dt_timezone | ZoneInfo | None, default_tz: dt_timezone | None = None
) -> dt_timezone | ZoneInfo | None:
    if timezone is None:
        return default_tz
    if isinstance(timezone, (dt_timezone, ZoneInfo)):
        return timezone
    tz_str = str(timezone).strip()
    if tz_str.startswith(("+", "-")):
        try:
            sign = -1 if tz_str[0] == "-" else 1
            parts = tz_str[1:].split(":")
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            return dt_timezone(sign * timedelta(hours=hours, minutes=minutes))
        except Exception:
            return default_tz
    if tz_str.upper() == "UTC":
        return UTC
    try:
        return ZoneInfo(tz_str)
    except Exception:
        return default_tz


@dataclass(frozen=True, slots=True)
class LocalCommand:
    kind: str
    args: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AutomationPlan:
    """Reviewable deterministic automation plan produced from natural language."""

    name: str
    trigger: str
    action: str
    require_approval: bool
    summary: str


class NaturalCommandParser:
    """Deterministic parser for high-confidence Virinda commands.

    The parser deliberately handles only phrases whose intent and arguments can be
    established without an LLM. Unknown/ambiguous utterances are returned as
    ``None`` and continue through the normal provider path.
    """

    _REMEMBER_PRIVATE = re.compile(
        r"^(?:please\s+)?remember(?:\s+that)?\s+(?:this\s+is\s+)?private(?:ly)?\s+(?P<key>.+?)\s+(?:is|=)\s+(?P<value>.+)$",
        re.IGNORECASE,
    )
    _REMEMBER_SECRET = re.compile(
        r"^(?:please\s+)?remember(?:\s+that)?\s+(?:my\s+)?(?P<key>password|passcode|pin|otp|api key|api token|secret|private key|credit card|bank account)\s+(?:is|=)\s+(?P<value>.+)$",
        re.IGNORECASE,
    )
    _REMEMBER_UNCERTAIN = re.compile(
        r"^(?:please\s+)?(?:i think|i believe)\s+(?:my\s+)?(?P<key>.+?)\s+(?:is|=)\s+(?P<value>.+)$",
        re.IGNORECASE,
    )
    _REMEMBER = re.compile(
        r"^(?:please\s+)?remember(?:\s+that)?\s+(?P<key>.+?)\s+(?:is|=)\s+(?P<value>.+)$",
        re.IGNORECASE,
    )
    _MY_FACT = re.compile(
        r"^(?:please\s+)?my\s+(?P<key>.+?)\s+(?:is|=)\s+(?P<value>.+)$", re.IGNORECASE
    )
    _CALL_ME = re.compile(r"^(?:please\s+)?(?:call me|my name is)\s+(?P<name>.+)$", re.IGNORECASE)
    _GET_FACT = re.compile(r"^(?:what(?:'s| is)|tell me)\s+my\s+(?P<key>.+?)[?!.]*$", re.IGNORECASE)
    _GET_NAME = re.compile(r"^(?:what(?:'s| is)|who is)\s+my name[?!.]*$", re.IGNORECASE)
    _PRIVATE_ON = re.compile(
        r"^(?:go|turn)\s+(?:into\s+)?private(?:\s+mode)?[.!?]*$", re.IGNORECASE
    )
    _PRIVATE_OFF = re.compile(
        r"^(?:leave|exit|turn off)\s+private(?:\s+mode)?[.!?]*$", re.IGNORECASE
    )
    _QUIET_ON = re.compile(r"^(?:go|turn)\s+(?:into\s+)?quiet(?:\s+mode)?[.!?]*$", re.IGNORECASE)
    _QUIET_OFF = re.compile(r"^(?:leave|exit|turn off)\s+quiet(?:\s+mode)?[.!?]*$", re.IGNORECASE)
    _NORMAL = re.compile(
        r"^(?:go|switch)\s+(?:back\s+)?(?:to\s+)?normal(?:\s+mode)?[.!?]*$", re.IGNORECASE
    )
    _REMINDER = re.compile(
        r"^(?:please\s+)?remind me(?: to)?\s+(?P<task>.+?)\s+(?P<when>in\s+\d+\s+(?:second|seconds|minute|minutes|hour|hours)|at\s+.+)$",
        re.IGNORECASE,
    )
    _RECURRING_REMINDER = re.compile(
        r"^(?:please\s+)?remind me(?: to)?\s+(?P<task>.+?)\s+(?P<repeat>every\s+(?:day|weekday|week|\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks))(?:\s+at\s+.+)?)$",
        re.IGNORECASE,
    )
    _PROVIDER = re.compile(
        r"^(?:please\s+)?(?:use|switch to|select)\s+(?P<provider>[a-zA-Z0-9_.-]+)(?:\s+provider)?[.!?]*$",
        re.IGNORECASE,
    )
    _MODEL = re.compile(
        r"^(?:please\s+)?(?:use|switch to)\s+(?:model\s+)?(?P<model>[a-zA-Z0-9_.:/-]+)[.!?]*$",
        re.IGNORECASE,
    )
    _OPEN_URL = re.compile(
        r"^(?:please\s+)?(?:open|visit)\s+(?P<url>https?://\S+)[.!?]*$", re.IGNORECASE
    )
    _WEB_SEARCH = re.compile(
        r"^(?:please\s+)?(?:search the web for|search for)\s+(?P<query>.+)$", re.IGNORECASE
    )
    _BRIEFING = re.compile(
        r"^(?:give me|show me|what(?:\'s| is)|tell me)\s+(?:my\s+)?(?:daily\s+|morning\s+)?briefing[.!?]*$",
        re.IGNORECASE,
    )
    _CONFIRM = re.compile(
        r"^(?:yes|yeah|yep|approve|approved|go ahead|do it|confirm)(?:[.!?]*)$", re.IGNORECASE
    )
    _CREATE_AUTOMATION = re.compile(
        r"^(?:please\s+)?(?:create|make|set up|schedule)\s+(?:a\s+)?(?:routine|automation)\s+(?P<body>.+)$",
        re.IGNORECASE,
    )
    _DISABLE_ROUTINE = re.compile(
        r"^(?:please\s+)?disable\s+(?:the\s+)?routine\s+(?P<name>.+)$", re.IGNORECASE
    )
    _DELETE_ROUTINE = re.compile(
        r"^(?:please\s+)?delete\s+(?:the\s+)?routine\s+(?P<name>.+)$", re.IGNORECASE
    )
    _PREVIEW_ROUTINE = re.compile(
        r"^(?:please\s+)?(?:preview|dry[- ]run|what will)\s+(?:the\s+)?routine\s+(?P<name>.+?)(?:\s+do)?[.!?]*$",
        re.IGNORECASE,
    )
    _EDIT_ROUTINE = re.compile(
        r"^(?:please\s+)?(?:change|edit|update)\s+(?:the\s+)?routine\s+(?P<name>.+?)\s+to\s+(?P<body>.+)$",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> LocalCommand | None:
        value = " ".join(text.strip().split())
        if not value:
            return None
        for pattern, kind, args in (
            (
                self._REMEMBER_SECRET,
                "remember_secret",
                lambda m: (m.group("key").strip(), m.group("value").strip()),
            ),
            (
                self._REMEMBER_PRIVATE,
                "remember_private",
                lambda m: (m.group("key").strip(), m.group("value").strip()),
            ),
            (
                self._REMEMBER_UNCERTAIN,
                "remember_fact_uncertain",
                lambda m: (m.group("key").strip(), m.group("value").strip()),
            ),
            (
                self._REMEMBER,
                "remember_fact",
                lambda m: (m.group("key").strip(), m.group("value").strip()),
            ),
            (
                self._MY_FACT,
                "remember_fact",
                lambda m: (m.group("key").strip(), m.group("value").strip()),
            ),
            (self._CALL_ME, "set_name", lambda m: (m.group("name").strip(),)),
            (self._GET_NAME, "get_name", lambda m: tuple()),
            (self._GET_FACT, "get_fact", lambda m: (m.group("key").strip(),)),
            (self._PRIVATE_ON, "context", lambda m: ("private",)),
            (self._PRIVATE_OFF, "context", lambda m: ("normal",)),
            (self._QUIET_ON, "context", lambda m: ("quiet",)),
            (self._QUIET_OFF, "context", lambda m: ("normal",)),
            (self._NORMAL, "context", lambda m: ("normal",)),
            (
                self._RECURRING_REMINDER,
                "recurring_reminder",
                lambda m: (m.group("task").strip(), m.group("repeat").strip()),
            ),
            (
                self._REMINDER,
                "reminder",
                lambda m: (m.group("task").strip(), m.group("when").strip()),
            ),
            (self._PROVIDER, "set_provider", lambda m: (m.group("provider").strip(),)),
            (self._MODEL, "set_model", lambda m: (m.group("model").strip(),)),
            (self._OPEN_URL, "tool_request", lambda m: ("browser.open", m.group("url").strip())),
            (
                self._WEB_SEARCH,
                "tool_request",
                lambda m: ("browser.search", m.group("query").strip()),
            ),
            (self._BRIEFING, "briefing", lambda m: tuple()),
            (self._CREATE_AUTOMATION, "create_automation", lambda m: (m.group("body").strip(),)),
            (
                self._EDIT_ROUTINE,
                "edit_routine",
                lambda m: (m.group("name").strip(), m.group("body").strip()),
            ),
            (self._DISABLE_ROUTINE, "disable_routine", lambda m: (m.group("name").strip(),)),
            (self._DELETE_ROUTINE, "delete_routine", lambda m: (m.group("name").strip(),)),
            (self._PREVIEW_ROUTINE, "preview_routine", lambda m: (m.group("name").strip(),)),
            (self._CONFIRM, "confirm", lambda m: tuple()),
        ):
            match = pattern.match(value)
            if match:
                return LocalCommand(kind, args(match))
        return None


def plan_automation(text: str, *, now: datetime, timezone: str | None = None) -> AutomationPlan:
    """Create a safe automation plan from a narrow deterministic grammar.

    Supported forms intentionally avoid free-form code generation:
      - ``every 2 hours, notify me to stretch``
      - ``every weekday at 9 am, open https://... and notify me that it is ready``
      - ``when I open VS Code, notify me to enter focus mode``
      - ``at 8 pm, notify me to call home``
    Unknown actions/schedules raise ``ValueError`` rather than guessing.
    """
    value = " ".join(text.strip().split())
    body = value
    m = re.match(r"^(?:every|at|when)\b.+", body, re.IGNORECASE)
    if not m:
        raise ValueError(
            "automation must start with a supported trigger such as 'every 2 hours', 'at 8 pm', or 'when I open VS Code'"
        )
    trigger_text, action_text = None, None
    # Event/app trigger.
    m = re.match(
        r"^when\s+(?:i\s+)?(?:open|start|launch|switch to)\s+(?P<app>.+?)\s*,\s*(?P<action>.+)$",
        body,
        re.IGNORECASE,
    )
    if m:
        trigger_text = f"app:{m.group('app').strip()}"
        action_text = m.group("action").strip()
    else:
        # Time/interval trigger.
        m = re.match(r"^(?P<when>every\s+.+?|at\s+.+?)\s*,\s*(?P<action>.+)$", body, re.IGNORECASE)
        if not m:
            raise ValueError("automation must use '<trigger>, <actions>'")
        trigger_text = m.group("when").strip()
        action_text = m.group("action").strip()

    steps: list[str] = []
    needs_approval = False
    for raw in re.split(r"\s+and\s+", action_text, flags=re.IGNORECASE):
        step = raw.strip().strip(".,")
        if not step:
            continue
        url_match = re.fullmatch(
            r"(?:then\s+)?(?:open|visit)\s+(https?://\S+)", step, re.IGNORECASE
        )
        if url_match:
            steps.append(f"approve:tool:browser.open|{json.dumps({'url': url_match.group(1)})}")
            needs_approval = True
            continue
        notify_match = re.fullmatch(
            r"(?:then\s+)?(?:notify me|remind me)\s+(?:to\s+)?(.+)", step, re.IGNORECASE
        )
        if notify_match:
            body_text = notify_match.group(1).strip()
            steps.append(f"notify:Virinda|{body_text}")
            continue
        raise ValueError(f"unsupported automation action: {step}")

    if not steps:
        raise ValueError("automation must contain at least one supported action")

    if trigger_text.lower().startswith("when ") or trigger_text.lower().startswith("when"):
        trigger = trigger_text
    elif trigger_text.lower().startswith("at "):
        due = parse_due_time(trigger_text, now=now, timezone=timezone)
        trigger = f"at:{due}"
    elif trigger_text.lower().startswith("every "):
        parse_recurrence(trigger_text, now=now, timezone=timezone)
        # Preserve the human schedule instead of flattening weekday schedules into
        # a 24-hour interval, which would incorrectly fire on weekends.
        trigger = f"schedule:{trigger_text}"
    else:
        raise ValueError("unsupported automation trigger")

    notification_steps = [
        step.split("|", 1)[1].strip()
        for step in steps
        if step.startswith("notify:") and "|" in step
    ]
    if notification_steps:
        name = notification_steps[0][:48]
    else:
        url_match = re.search(r"https?://([^\s/]+)", action_text)
        name = (url_match.group(1) if url_match else "Virinda automation")[:48]
    summary = f"Trigger: {trigger_text}; Actions: " + "; ".join(steps)
    return AutomationPlan(
        name=name,
        trigger=trigger,
        action="||".join(steps),
        require_approval=needs_approval,
        summary=summary,
    )


def parse_recurrence(
    repeat: str, *, now: datetime, timezone: str | None = None
) -> tuple[float, float]:
    """Return the first due timestamp and recurrence interval for common schedules.

    Supported schedules are ``every day``, ``every weekday``, ``every week``,
    ``every N minutes/hours/days/weeks`` and the corresponding ``at HH:MM`` suffix
    for daily/weekday schedules.
    """
    zone = ZoneInfo(timezone) if timezone else now.tzinfo
    current = now.astimezone(zone) if zone else now
    value = repeat.strip().lower().replace(".", "")
    daily_time = None
    m = re.fullmatch(r"every\s+(day|weekday|week)(?:\s+at\s+(.+))?", value, re.IGNORECASE)
    if m:
        unit, clock = m.group(1), m.group(2)
        seconds = {"day": 86400.0, "weekday": 86400.0, "week": 604800.0}[unit]
        if clock:
            candidate_text = f"at {clock}"
            due = datetime.fromtimestamp(
                parse_due_time(candidate_text, now=current, timezone=timezone), zone
            )
        else:
            due = current + timedelta(days=1 if unit != "week" else 7)
            if unit == "weekday":
                while due.weekday() >= 5:
                    due += timedelta(days=1)
        return due.timestamp(), seconds
    m = re.fullmatch(r"every\s+(\d+)\s+(minutes?|hours?|days?|weeks?)", value, re.IGNORECASE)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        seconds_per = {
            "minute": 60.0,
            "minutes": 60.0,
            "hour": 3600.0,
            "hours": 3600.0,
            "day": 86400.0,
            "days": 86400.0,
            "week": 604800.0,
            "weeks": 604800.0,
        }
        seconds = amount * seconds_per[unit]
        return (current + timedelta(seconds=seconds)).timestamp(), seconds
    raise ValueError(
        "unsupported recurrence; use 'every day', 'every weekday at 8 am', or 'every 2 hours'"
    )


def parse_due_time(when: str, *, now: datetime, timezone: str | None = None) -> float:
    """Parse deterministic reminder expressions into a Unix timestamp.

    Supported forms are ``in N seconds/minutes/hours`` and ``at HH:MM`` with
    optional AM/PM and ``at noon``/``at midnight``. Absolute date phrases remain
    provider/skill territory until we can parse them without ambiguity.
    """
    zone = _resolve_timezone(timezone, now.tzinfo)
    current = now.astimezone(zone) if zone else now
    relative = re.fullmatch(r"in\s+(\d+)\s+(seconds?|minutes?|hours?)", when.strip(), re.IGNORECASE)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).lower()
        delta = {
            "second": 1,
            "seconds": 1,
            "minute": 60,
            "minutes": 60,
            "hour": 3600,
            "hours": 3600,
        }[unit]
        return (current + timedelta(seconds=amount * delta)).timestamp()

    normalized = when.strip().lower().replace(".", "")
    if normalized.startswith("at "):
        normalized = normalized[3:].strip()
    target: dt_time | None = None
    if normalized == "noon":
        target = dt_time(12, 0)
    elif normalized == "midnight":
        target = dt_time(0, 0)
    else:
        for fmt in ("%I:%M %p", "%I %p", "%H:%M", "%H"):
            try:
                target = datetime.strptime(normalized, fmt).time()
                break
            except ValueError:
                continue
    if target is None:
        raise ValueError("unsupported reminder time; use 'in 10 minutes' or 'at 8:30 pm'")
    candidate = datetime.combine(current.date(), target, tzinfo=zone)
    if candidate <= current:
        candidate += timedelta(days=1)
    return candidate.timestamp()
