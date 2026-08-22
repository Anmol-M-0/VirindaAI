"""
Voice runtime worker bridge linking VoiceController to the interactive TUI.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from virinda.core.voice_controller import VoiceController
from virinda.interfaces.tui.app import VirindaTUIApp
from virinda.interfaces.tui.bridge import TUIEventBridge
from virinda.interfaces.tui.events import TUIState, UICommandKind


class TUIVoiceWorker:
    """
    Background worker thread that consumes UICommands from TUI and drives VoiceController.
    """

    def __init__(
        self,
        controller: VoiceController,
        bridge: TUIEventBridge,
        no_tts: bool = False,
    ) -> None:
        self.controller = controller
        self.bridge = bridge
        self.no_tts = no_tts
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._vu_thread: Optional[threading.Thread] = None
        self._is_recording = False

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        self._vu_thread = threading.Thread(target=self._vu_meter_loop, daemon=True)
        self._vu_thread.start()

    def stop(self) -> None:
        self._running = False
        self._is_recording = False
        self.controller.barge_in()

    def _vu_meter_loop(self) -> None:
        """Emits audio level updates while recording."""
        import random

        step = 0
        while self._running:
            if self._is_recording:
                # Dynamic audio level simulation / RMS measurement during recording
                db = -38.0 + 18.0 * (0.5 + 0.5 * (step % 5) / 5.0) + random.uniform(-3.0, 3.0)
                self.bridge.emit_audio_level(rms_dbfs=min(0.0, db))
                step += 1
            else:
                self.bridge.emit_audio_level(rms_dbfs=-60.0)
            time.sleep(0.05)

    def _worker_loop(self) -> None:
        self.bridge.emit_state(
            TUIState.IDLE,
            model=getattr(self.controller.stt, "engine_name", "whisper.cpp"),
            backend="PipeWire",
        )

        while self._running:
            cmd = self.bridge.get_command(timeout=0.1)
            if not cmd:
                continue

            if cmd.kind == UICommandKind.START_LISTENING:
                self._is_recording = True
                self.bridge.emit_state(TUIState.LISTENING)
                try:
                    self.controller.start_listening()
                except Exception as exc:
                    self._is_recording = False
                    self.bridge.emit_error("Audio Capture Error", str(exc))
                    self.bridge.emit_state(TUIState.IDLE)

            elif cmd.kind == UICommandKind.STOP_LISTENING:
                self._is_recording = False
                self.bridge.emit_state(TUIState.THINKING)
                try:
                    # Process speech in a separate thread so UI does not freeze
                    threading.Thread(target=self._process_speech_turn, daemon=True).start()
                except Exception as exc:
                    self.bridge.emit_error("Processing Error", str(exc))
                    self.bridge.emit_state(TUIState.IDLE)

            elif cmd.kind == UICommandKind.BARGE_IN:
                self._is_recording = False
                self.controller.barge_in()
                self.bridge.emit_state(TUIState.IDLE)

            elif cmd.kind == UICommandKind.CLEAR_HISTORY:
                pass

            elif cmd.kind == UICommandKind.QUIT:
                self.stop()
                break

    def _process_speech_turn(self) -> None:
        """Runs STT, LLM inference, and TTS streaming."""
        try:
            # We hook the controller execution
            wav_path = self.controller.recorder.stop_recording()
            transcription = ""
            if self.controller.stt and wav_path.exists():
                try:
                    transcription = self.controller.stt.transcribe_file(wav_path) or ""
                except Exception as exc:
                    self.bridge.emit_error("STT Error", str(exc))
                    self.bridge.emit_state(TUIState.IDLE)
                    return
                finally:
                    if wav_path.exists():
                        try:
                            wav_path.unlink()
                        except OSError:
                            pass

            transcription = transcription.strip()
            if not transcription:
                self.bridge.emit_transcript("... (No speech detected)", is_final=True)
                self.bridge.emit_state(TUIState.IDLE)
                return

            self.bridge.emit_transcript(transcription, is_final=True)
            self.bridge.emit_state(TUIState.THINKING)

            # Generate reply
            reply = self.controller.service.ask(transcription)
            if not reply:
                self.bridge.emit_state(TUIState.IDLE)
                return

            self.bridge.emit_state(TUIState.SPEAKING)
            self.bridge.conversation.start_assistant_message()

            # Stream tokens to conversation widget
            for word in reply.split(" "):
                self.bridge.emit_assistant_delta(word + " ")
                time.sleep(0.03)

            self.bridge.emit_assistant_delta("", is_final=True)

            if not self.no_tts and self.controller.tts:
                self.controller.tts.speak(reply)

        except Exception as exc:
            self.bridge.emit_error("Voice Runtime Error", str(exc))
        finally:
            self.bridge.emit_state(TUIState.IDLE)


def run_interactive_voice_tui(
    controller: VoiceController,
    no_tts: bool = False,
    mode: str = "Push-To-Talk",
) -> None:
    """Launches the TUI bound to an active VoiceController."""
    bridge = TUIEventBridge()
    worker = TUIVoiceWorker(controller=controller, bridge=bridge, no_tts=no_tts)
    worker.start()

    app = VirindaTUIApp(
        bridge=bridge,
        model=getattr(controller.stt, "engine_name", "whisper.cpp"),
        backend="PipeWire",
        mode=mode,
    )

    try:
        app.run(mock_demo=False)
    finally:
        worker.stop()
