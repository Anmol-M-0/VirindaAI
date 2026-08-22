"""
VirindaAI Modular Terminal User Interface (TUI) Package.
"""

from virinda.interfaces.tui.app import VirindaTUIApp, run_tui
from virinda.interfaces.tui.bridge import TUIEventBridge
from virinda.interfaces.tui.events import (
    AssistantDelta,
    AudioLevelChanged,
    ErrorRaised,
    TranscriptDelta,
    TUIEvent,
    TUIState,
    UICommand,
    UICommandKind,
    VoiceStateChanged,
)

__all__ = [
    "VirindaTUIApp",
    "run_tui",
    "TUIEventBridge",
    "TUIState",
    "TUIEvent",
    "UICommand",
    "UICommandKind",
    "VoiceStateChanged",
    "AudioLevelChanged",
    "TranscriptDelta",
    "AssistantDelta",
    "ErrorRaised",
]
