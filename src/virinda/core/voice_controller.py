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
from virinda.infrastructure.audio.streaming_tts import StreamingTTSWorker


class VoiceController:
    """Coordinates physical microphone capture, STT, concurrent LLM generation, and streaming TTS playback

    with monotonic generation token invalidation for safe, race-free barge-in.
    """

    def __init__(
        self,
        service: AssistantService,
        recorder: Optional[LinuxAudioRecorder] = None,
        player: Optional[LinuxAudioPlayer] = None,
        tts: Optional[NativeTTS] = None,
        stt: Optional[GroqWhisperSTT] = None,
        streaming_tts: Optional[StreamingTTSWorker] = None,
    ) -> None:
        self.service = service
        self.recorder = recorder or LinuxAudioRecorder()
        self.player = player or LinuxAudioPlayer()
        self.tts = tts or NativeTTS()
        self.stt = stt or GroqWhisperSTT()
        self.streaming_tts = streaming_tts or StreamingTTSWorker(tts=self.tts)
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
            self.streaming_tts.set_generation(self._generation)
            self._state = TurnState.LISTENING
            return self.recorder.start_recording()

    def stop_listening_and_process(
        self,
        *,
        stream_stdout: bool = True,
        speak_output: bool = True,
    ) -> str:
        """Finalize microphone recording, run STT, stream LLM tokens, feed concurrent TTS, and finalize."""
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

            # Stream LLM tokens and feed sentences concurrently to TTS
            tokenizer = StreamingSentenceTokenizer()
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

                    if speak_output:
                        for sentence in tokenizer.feed(text_chunk):
                            with self._lock:
                                self._state = TurnState.SPEAKING
                            self.streaming_tts.feed(current_gen, sentence)

            # Flush remaining sentence from tokenizer buffer
            if speak_output:
                for sentence in tokenizer.flush():
                    with self._lock:
                        self._state = TurnState.SPEAKING
                    self.streaming_tts.feed(current_gen, sentence)

            full_response = "".join(response_chunks).strip()
            if not full_response:
                # Fallback to direct ask
                full_response = self.service.ask(transcription)
                if stream_stdout and not response_chunks:
                    sys.stdout.write(full_response)
                    sys.stdout.flush()
                if speak_output and full_response:
                    with self._lock:
                        self._state = TurnState.SPEAKING
                    self.streaming_tts.feed(current_gen, full_response)

            if stream_stdout:
                sys.stdout.write("\n")
                sys.stdout.flush()

            # Wait for queued audio sentences to finish playing
            if speak_output:
                self.streaming_tts.flush_and_wait(current_gen, timeout=20.0)

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
        self.streaming_tts.cancel()
        self.tts.stop()
        self.player.stop()

    def barge_in(self) -> None:
        """Hard barge-in: cancel current turn, stop playback/recording, and return to CANCELLED."""
        with self._lock:
            self._generation += 1
            self.cancel_playback()
            self.recorder.cancel_recording()
            self._state = TurnState.CANCELLED

    def close(self) -> None:
        self.cancel_playback()
        self.streaming_tts.close()
