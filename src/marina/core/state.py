from __future__ import annotations

from dataclasses import dataclass, replace
from threading import Lock

from marina.domain.events import LifecycleChanged
from marina.domain.models import InteractionMode, LifecycleState, Session, Snapshot


@dataclass(slots=True)
class AssistantState:
    session: Session
    transcript: str = ""
    response: str = ""
    sequence: int = 0


class AssistantStateMachine:
    """The sole owner of canonical in-memory runtime state."""

    def __init__(self, session: Session, publish) -> None:
        self._state = AssistantState(session=session)
        self._publish = publish
        self._lock = Lock()

    def snapshot(self) -> Snapshot:
        with self._lock:
            s = self._state
            return Snapshot(
                session_id=s.session.id,
                generation_id=s.session.generation_id,
                lifecycle=s.session.lifecycle,
                mode=s.session.mode,
                transcript=s.transcript,
                response=s.response,
                provider=s.session.provider,
                model=s.session.model,
                sequence=s.sequence,
            )

    def set_generation(self, generation_id: int) -> None:
        with self._lock:
            self._state.session = replace(self._state.session, generation_id=generation_id, lifecycle=LifecycleState.IDLE)
            self._state.transcript = ""
            self._state.response = ""
            self._state.sequence += 1

    def publish(self, event) -> None:
        self._publish(event)

    def set_mode(self, mode: InteractionMode) -> None:
        with self._lock:
            self._state.session = replace(self._state.session, mode=mode)

    def set_provider(self, provider: str, model: str) -> None:
        with self._lock:
            self._state.session = replace(self._state.session, provider=provider, model=model)

    def transition(self, lifecycle: LifecycleState, generation_id: int) -> None:
        with self._lock:
            if generation_id != self._state.session.generation_id:
                return
            if lifecycle == self._state.session.lifecycle:
                return
            self._state.session = replace(self._state.session, lifecycle=lifecycle)
            self._state.sequence += 1
            seq = self._state.sequence
        self._publish(LifecycleChanged(generation_id=generation_id, sequence=seq, state=lifecycle.value))

    def next_sequence(self, generation_id: int) -> int | None:
        with self._lock:
            if generation_id != self._state.session.generation_id:
                return None
            self._state.sequence += 1
            return self._state.sequence

    def set_transcript(self, text: str, generation_id: int) -> None:
        with self._lock:
            if generation_id == self._state.session.generation_id:
                self._state.transcript = text

    def append_response(self, text: str, generation_id: int) -> int | None:
        with self._lock:
            if generation_id != self._state.session.generation_id:
                return None
            self._state.response += text
            self._state.sequence += 1
            return self._state.sequence
