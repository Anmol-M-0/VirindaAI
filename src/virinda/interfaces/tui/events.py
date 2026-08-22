"""
Typed event contracts and state models for the VirindaAI Terminal User Interface (TUI).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class TUIState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"


class UICommandKind(str, Enum):
    TOGGLE_LISTENING = "TOGGLE_LISTENING"
    START_LISTENING = "START_LISTENING"
    STOP_LISTENING = "STOP_LISTENING"
    BARGE_IN = "BARGE_IN"
    CLEAR_HISTORY = "CLEAR_HISTORY"
    QUIT = "QUIT"


@dataclass(kw_only=True)
class TUIEvent:
    """Base class for all TUI events."""

    timestamp: float = field(default_factory=time.time)


@dataclass(kw_only=True)
class VoiceStateChanged(TUIEvent):
    """Fired when the underlying voice state changes."""

    state: TUIState
    model: str = ""
    backend: str = ""
    message: str = ""


@dataclass(kw_only=True)
class AudioLevelChanged(TUIEvent):
    """High-frequency audio VU meter update."""

    rms_dbfs: float
    peak_dbfs: float = -60.0


@dataclass(kw_only=True)
class TranscriptDelta(TUIEvent):
    """Incremental user speech transcript."""

    text: str
    is_final: bool = False
    speaker: str = "User"


@dataclass(kw_only=True)
class AssistantDelta(TUIEvent):
    """Streaming response token from AI engine."""

    text: str
    is_final: bool = False
    model: str = ""


@dataclass(kw_only=True)
class ErrorRaised(TUIEvent):
    """Diagnostics or runtime error event."""

    title: str
    description: str


@dataclass
class UICommand:
    """Command emitted from user input in TUI to the voice runtime."""

    kind: UICommandKind
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
