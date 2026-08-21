from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from time import time
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class AssistantEvent:
    generation_id: int
    sequence: int
    created_at: float = field(default_factory=time)

    def to_payload(self) -> dict[str, Any]:
        if not is_dataclass(self):
            return {}
        return {item.name: _json_value(getattr(self, item.name)) for item in fields(self)}


def _json_value(value: Any) -> Any:
    return getattr(value, "value", value)


@dataclass(frozen=True, slots=True)
class LifecycleChanged(AssistantEvent):
    state: str = "idle"


@dataclass(frozen=True, slots=True)
class TranscriptFinal(AssistantEvent):
    text: str = ""


@dataclass(frozen=True, slots=True)
class ResponseDelta(AssistantEvent):
    text: str = ""


@dataclass(frozen=True, slots=True)
class ResponseCompleted(AssistantEvent):
    text: str = ""


@dataclass(frozen=True, slots=True)
class Cancelled(AssistantEvent):
    reason: str = "user"


@dataclass(frozen=True, slots=True)
class Error(AssistantEvent):
    code: str = "internal_error"
    message: str = ""


class EventSink(Protocol):
    def publish(self, event: AssistantEvent) -> None: ...


EVENT_TYPES = {
    event.__name__: event
    for event in (LifecycleChanged, TranscriptFinal, ResponseDelta, ResponseCompleted, Cancelled, Error)
}
