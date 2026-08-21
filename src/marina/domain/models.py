from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from time import time
from typing import Any
from uuid import uuid4


class LifecycleState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    CANCELLING = "cancelling"
    DEGRADED = "degraded"


class InteractionMode(StrEnum):
    CONVERSATION = "conversation"
    DICTATION = "dictation"


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str
    created_at: float = field(default_factory=time)


@dataclass(frozen=True, slots=True)
class Session:
    id: str = field(default_factory=lambda: uuid4().hex)
    generation_id: int = 0
    lifecycle: LifecycleState = LifecycleState.IDLE
    mode: InteractionMode = InteractionMode.CONVERSATION
    provider: str = "echo"
    model: str = "offline-demo"


@dataclass(frozen=True, slots=True)
class Snapshot:
    session_id: str
    generation_id: int
    lifecycle: LifecycleState
    mode: InteractionMode
    transcript: str
    response: str
    provider: str
    model: str
    sequence: int


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    generation_id: int
    model: str
    messages: tuple[Message, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
