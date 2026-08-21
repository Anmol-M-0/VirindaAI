from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Optional

from virinda.application.service import AssistantService
from virinda.core.acceptance.models import TurnState
from virinda.core.tokenizer import StreamingSentenceTokenizer
from virinda.infrastructure.audio.player import LinuxAudioPlayer
from virinda.infrastructure.audio.recorder import LinuxAudioRecorder
from virinda.infrastructure.audio.speech import GroqWhisperSTT, NativeTTS


class VoiceController:
    """Coordinates physical microphone capture, STT, LLM generation, and TTS audio playback

    with monotonic generation token invalidation for safe, race-free barge-in.
    """

    def __init__(
        self,
        service: AssistantService,
        recorder: Optional[LinuxAudioRecorder] = None,
        player: Optional[LinuxAudioPlayer] = None,
        tts: Optional[NativeTTS] = None,
        stt: Optional[GroqWhisperSTT] = None,
    ) -> None:
        self.service = service
        self.recorder = recorder or LinuxAudioRecorder()
        self.player = player or LinuxAudioPlayer()
        self.tts = tts or NativeTTS()
        self.stt = stt or GroqWhisperSTT()
        self.tokenizer = StreamingSentenceTokenizer()
        self._lock = threading.RLock()
        self._state: TurnState = TurnState.CREATED
        self._generation: int = 0

    @property
    def state(self) -> TurnState:
        with self._lock:
            return self._state

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def start_listening(self) -> Path:
        """Begin audio capture and transition state to LISTENING."""
        with self._lock:
            self.cancel_playback()
            self._generation += 1
            self._state = TurnState.LISTENING
            return self.recorder.start_recording()

    def stop_listening_and_process(
        self,
        *,
        stream_stdout: bool = True,
        speak_output: bool = True,
    ) -> str:
        """Finalize microphone recording, run STT, evaluate AssistantService, and speak response."""
        wav_path = self.recorder.stop_recording()
        try:
            with self._lock:
                self._state = TurnState.TRANSCRIBING

            # Transcribe audio
            transcription = self.stt.transcribe_file(wav_path) if self.stt else ""
            transcription = transcription.strip()

            if not transcription:
                with self._lock:
                    self._state = TurnState.CREATED
                return ""

            with self._lock:
                self._state = TurnState.THINKING

            if stream_stdout:
                sys.stdout.write(f"\nUser: {transcription}\nAssistant: ")
                sys.stdout.flush()

            # Execute turn via AssistantService
            current_gen = self.generation
            response_chunks: list[str] = []

            # Stream LLM tokens
            for event in (
                self.service.events_stream(transcription)
                if hasattr(self.service, "events_stream")
                else [transcription]
            ):
                if self.generation != current_gen:
                    break

                text_chunk = event if isinstance(event, str) else getattr(event, "text", "")
                if text_chunk:
                    response_chunks.append(text_chunk)
                    if stream_stdout:
                        sys.stdout.write(text_chunk)
                        sys.stdout.flush()

            full_response = "".join(response_chunks).strip()
            if not full_response:
                # Fallback to direct ask
                full_response = self.service.ask(transcription)
                if stream_stdout and not response_chunks:
                    sys.stdout.write(full_response)
                    sys.stdout.flush()

            if stream_stdout:
                sys.stdout.write("\n")
                sys.stdout.flush()

            # Speak output sentence by sentence
            if speak_output and full_response and self.generation == current_gen:
                with self._lock:
                    self._state = TurnState.SPEAKING

                sentences = list(self.tokenizer.feed(full_response))
                sentences.extend(self.tokenizer.flush())
                for sentence in sentences:
                    if self.generation != current_gen:
                        break
                    self.tts.speak(sentence, block=True)

            with self._lock:
                if self.generation == current_gen:
                    self._state = TurnState.COMPLETED

            return full_response

        finally:
            if wav_path.exists():
                try:
                    wav_path.unlink()
                except OSError:
                    pass

    def cancel_playback(self) -> None:
        """Cancel TTS playback and audio player immediately."""
        self.tts.stop()
        self.player.stop()

    def barge_in(self) -> None:
        """Hard barge-in: cancel current turn, stop playback/recording, and return to CREATED/IDLE."""
        with self._lock:
            self._generation += 1
            self.cancel_playback()
            self.recorder.cancel_recording()
            self._state = TurnState.CANCELLED
