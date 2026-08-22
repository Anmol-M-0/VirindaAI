"""
Thread-safe, bounded event transport bridge linking Virinda Voice runtime to TUI presentation.
"""

from __future__ import annotations

import queue
import time
from typing import Optional

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


class TUIEventBridge:
    """
    Decoupled event broker between VoiceController / AssistantService and TUI.
    Enforces bounded queues and lossy latest-value updates for high-frequency audio levels.
    """

    def __init__(self, max_queue_size: int = 256) -> None:
        self.events_queue: queue.Queue[TUIEvent] = queue.Queue(maxsize=max_queue_size)
        self.commands_queue: queue.Queue[UICommand] = queue.Queue(maxsize=64)
        self._latest_audio_level: Optional[AudioLevelChanged] = None
        self._last_audio_emit_time: float = 0.0
        self._audio_throttle_interval: float = 0.033  # ~30 Hz max rate for VU meter

    def emit_event(self, event: TUIEvent) -> None:
        """Publishes an event to the presentation layer."""
        if isinstance(event, AudioLevelChanged):
            # Throttle high-frequency audio samples
            now = time.time()
            self._latest_audio_level = event
            if now - self._last_audio_emit_time >= self._audio_throttle_interval:
                self._last_audio_emit_time = now
                try:
                    self.events_queue.put_nowait(event)
                except queue.Full:
                    pass
            return

        try:
            self.events_queue.put_nowait(event)
        except queue.Full:
            # Drop oldest non-critical event if full
            try:
                _ = self.events_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.events_queue.put_nowait(event)
            except queue.Full:
                pass

    def emit_state(
        self, state: TUIState, model: str = "", backend: str = "", message: str = ""
    ) -> None:
        self.emit_event(
            VoiceStateChanged(state=state, model=model, backend=backend, message=message)
        )

    def emit_audio_level(self, rms_dbfs: float, peak_dbfs: float = -60.0) -> None:
        self.emit_event(AudioLevelChanged(rms_dbfs=rms_dbfs, peak_dbfs=peak_dbfs))

    def emit_transcript(self, text: str, is_final: bool = False, speaker: str = "User") -> None:
        self.emit_event(TranscriptDelta(text=text, is_final=is_final, speaker=speaker))

    def emit_assistant_delta(self, text: str, is_final: bool = False, model: str = "") -> None:
        self.emit_event(AssistantDelta(text=text, is_final=is_final, model=model))

    def emit_error(self, title: str, description: str) -> None:
        self.emit_event(ErrorRaised(title=title, description=description))

    def post_command(self, kind: UICommandKind, **payload: object) -> None:
        """Sends a user command from TUI to the voice engine."""
        try:
            self.commands_queue.put_nowait(UICommand(kind=kind, payload=dict(payload)))
        except queue.Full:
            pass

    def get_command(self, timeout: float = 0.0) -> Optional[UICommand]:
        """Retrieves a pending user command for the voice runtime."""
        try:
            return self.commands_queue.get(
                block=timeout > 0, timeout=timeout if timeout > 0 else None
            )
        except (queue.Empty, TimeoutError):
            return None
