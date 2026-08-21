from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ContextMode(StrEnum):
    NORMAL = "normal"
    FOCUS = "focus"
    PRIVATE = "private"
    QUIET = "quiet"


@dataclass(frozen=True, slots=True)
class ContextPolicy:
    """Local interaction policy that future OVOS/GUI adapters can consume."""

    mode: ContextMode = ContextMode.NORMAL
    proactive_notifications: bool = True
    follow_up_listening: bool = True
    announce_wake: bool = False
    persist_transcripts: bool = True


POLICIES: dict[ContextMode, ContextPolicy] = {
    ContextMode.NORMAL: ContextPolicy(),
    ContextMode.FOCUS: ContextPolicy(mode=ContextMode.FOCUS, proactive_notifications=False),
    ContextMode.PRIVATE: ContextPolicy(
        mode=ContextMode.PRIVATE, proactive_notifications=False, persist_transcripts=False
    ),
    ContextMode.QUIET: ContextPolicy(
        mode=ContextMode.QUIET, proactive_notifications=False, follow_up_listening=False
    ),
}
