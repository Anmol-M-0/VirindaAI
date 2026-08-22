"""
Main Terminal User Interface (TUI) application loop for VirindaAI.
Implements double-buffered Rich Live rendering with non-blocking stdin hotkey handling.
"""

from __future__ import annotations

import queue
import select
import sys
import termios
import threading
import time
import tty
from typing import Optional

from rich.console import Console, Group
from rich.live import Live

from virinda.interfaces.tui.bridge import TUIEventBridge
from virinda.interfaces.tui.events import (
    AssistantDelta,
    AudioLevelChanged,
    ErrorRaised,
    TranscriptDelta,
    TUIState,
    UICommandKind,
    VoiceStateChanged,
)
from virinda.interfaces.tui.widgets import (
    ConversationBuffer,
    render_conversation,
    render_footer,
    render_header,
    render_vu_meter,
)


class VirindaTUIApp:
    """
    Presentation-only, double-buffered TUI for ambient desktop voice interaction.
    """

    def __init__(
        self,
        bridge: Optional[TUIEventBridge] = None,
        model: str = "whisper.cpp / local",
        backend: str = "PipeWire",
        mode: str = "Push-To-Talk",
    ) -> None:
        self.bridge = bridge or TUIEventBridge()
        self.model = model
        self.backend = backend
        self.mode = mode

        self.current_state = TUIState.IDLE
        self.current_rms_dbfs = -60.0
        self.current_peak_dbfs = -60.0
        self.conversation = ConversationBuffer()

        self.console = Console()
        self._running = False
        self._key_thread: Optional[threading.Thread] = None

    def compose_layout(self) -> Group:
        """Assembles the complete full-screen double-buffered layout."""
        header = render_header(
            state=self.current_state,
            model=self.model,
            backend=self.backend,
            mode=self.mode,
        )
        vu = render_vu_meter(
            rms_dbfs=self.current_rms_dbfs,
            peak_dbfs=self.current_peak_dbfs,
            is_active=(self.current_state in (TUIState.LISTENING, TUIState.SPEAKING)),
        )
        convo = render_conversation(self.conversation)
        footer = render_footer(state=self.current_state)

        return Group(header, vu, convo, footer)

    def _process_events(self) -> None:
        """Drains pending events from the event bridge."""
        while True:
            try:
                event = self.bridge.events_queue.get_nowait()
            except queue.Empty:
                break

            if isinstance(event, VoiceStateChanged):
                self.current_state = event.state
                if event.model:
                    self.model = event.model
                if event.backend:
                    self.backend = event.backend

            elif isinstance(event, AudioLevelChanged):
                self.current_rms_dbfs = event.rms_dbfs
                self.current_peak_dbfs = event.peak_dbfs

            elif isinstance(event, TranscriptDelta):
                if event.is_final:
                    self.conversation.add_user_message(event.text)

            elif isinstance(event, AssistantDelta):
                if event.is_final:
                    self.conversation.finish_assistant_message()
                else:
                    self.conversation.append_assistant_token(event.text)

            elif isinstance(event, ErrorRaised):
                self.current_state = TUIState.ERROR

    def _read_keys(self) -> None:
        """Non-blocking raw stdin reader thread for hotkeys."""
        if not sys.stdin.isatty():
            return

        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setcbreak(sys.stdin.fileno())
            while self._running:
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r:
                    ch = sys.stdin.read(1)
                    if not ch:
                        continue

                    # Enter key -> Toggle listening
                    if ch in ("\n", "\r"):
                        if self.current_state == TUIState.LISTENING:
                            self.bridge.post_command(UICommandKind.STOP_LISTENING)
                        else:
                            self.bridge.post_command(UICommandKind.START_LISTENING)

                    # 'b' or ESC -> Barge-In
                    elif ch in ("b", "B", "\x1b"):
                        self.bridge.post_command(UICommandKind.BARGE_IN)

                    # 'c' -> Clear History
                    elif ch in ("c", "C"):
                        self.conversation.clear()
                        self.bridge.post_command(UICommandKind.CLEAR_HISTORY)

                    # 'q' or Ctrl+C -> Quit
                    elif ch in ("q", "Q", "\x03"):
                        self.bridge.post_command(UICommandKind.QUIT)
                        self._running = False
                        break
        except Exception:
            pass
        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

    def run(self, mock_demo: bool = False) -> None:
        """Runs the TUI event loop."""
        self._running = True

        if mock_demo:
            # Spawn mock background event generator for standalone demonstration
            threading.Thread(target=self._run_mock_demo, daemon=True).start()

        self._key_thread = threading.Thread(target=self._read_keys, daemon=True)
        self._key_thread.start()

        try:
            with Live(
                self.compose_layout(),
                console=self.console,
                refresh_per_second=30,
                screen=False,
            ) as live:
                while self._running:
                    self._process_events()
                    live.update(self.compose_layout())
                    time.sleep(0.033)
        finally:
            self._running = False

    def _run_mock_demo(self) -> None:
        """Simulates ambient voice interaction for visual verification."""
        time.sleep(1.0)
        self.bridge.emit_state(TUIState.LISTENING)
        for i in range(20):
            db = -35.0 + 15.0 * (i % 4)
            self.bridge.emit_audio_level(rms_dbfs=db)
            time.sleep(0.1)

        self.bridge.emit_transcript(
            "What is the current desktop system load and battery level?", is_final=True
        )
        self.bridge.emit_state(TUIState.THINKING)
        time.sleep(1.0)

        self.bridge.emit_state(TUIState.SPEAKING)
        sample_reply = (
            "System load is nominal at 1.15 across 8 CPU cores. Battery is at 94% on AC power."
        )
        for token in sample_reply.split(" "):
            self.bridge.emit_assistant_delta(token + " ")
            time.sleep(0.08)
        self.bridge.emit_assistant_delta("", is_final=True)
        self.bridge.emit_state(TUIState.IDLE)


def run_tui(
    bridge: Optional[TUIEventBridge] = None,
    model: str = "whisper.cpp / local",
    backend: str = "PipeWire",
    mode: str = "Push-To-Talk",
    mock_demo: bool = False,
) -> None:
    """Convenience entry point for starting the VirindaAI TUI."""
    app = VirindaTUIApp(bridge=bridge, model=model, backend=backend, mode=mode)
    app.run(mock_demo=mock_demo)
