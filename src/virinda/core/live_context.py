from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import RLock
from time import time
from typing import Any


@dataclass(frozen=True, slots=True)
class LiveSessionContext:
    """Ephemeral context shared by the OVOS voice path, daemon, and UI.

    This is intentionally separate from durable conversation history. It lets OVOS
    events update Virinda's live state without forcing duplicate transcript writes.
    """

    session_id: str
    last_user_utterance: str = ""
    last_assistant_text: str = ""
    speaker: str | None = None
    meeting_active: bool = False
    listening: bool = False
    speaking: bool = False
    updated_at: float = 0.0


class LiveContextStore:
    def __init__(self, session_id: str) -> None:
        self._lock = RLock()
        self._context = LiveSessionContext(session_id=session_id, updated_at=time())

    def reset_session(self, session_id: str) -> None:
        with self._lock:
            self._context = LiveSessionContext(session_id=session_id, updated_at=time())

    def update(self, **changes: Any) -> LiveSessionContext:
        with self._lock:
            values = asdict(self._context)
            values.update(changes)
            values["updated_at"] = time()
            self._context = LiveSessionContext(**values)
            return self._context

    def snapshot(self) -> LiveSessionContext:
        with self._lock:
            return self._context
