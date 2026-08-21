from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from threading import Event
from time import monotonic
from typing import Protocol


class AudioInteractionMode(StrEnum):
    """How a voice interaction is initiated."""

    WAKE_WORD = "wake_word"
    PUSH_TO_TALK = "push_to_talk"
    TOGGLE_LISTEN = "toggle_listen"
    FOLLOW_UP = "follow_up"


class AudioStage(StrEnum):
    DISARMED = "disarmed"
    ARMED = "armed"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    FOLLOW_UP = "follow_up"


@dataclass(frozen=True, slots=True)
class AudioFrame:
    pcm: bytes
    sample_rate: int = 16_000
    channels: int = 1
    sample_width: int = 2
    captured_at: float = field(default_factory=monotonic)


@dataclass(frozen=True, slots=True)
class WakeDetection:
    wake_word: str
    confidence: float
    detected_at: float = field(default_factory=monotonic)


@dataclass(frozen=True, slots=True)
class VoiceActivity:
    speech: bool
    confidence: float = 0.0
    detected_at: float = field(default_factory=monotonic)


@dataclass(frozen=True, slots=True)
class AudioPolicy:
    wake_word: str = "hey virinda"
    wake_threshold: float = 0.5
    pre_roll_ms: int = 300
    min_speech_ms: int = 250
    end_silence_ms: int = 750
    max_utterance_ms: int = 30_000
    follow_up_window_ms: int = 8_000
    barge_in_ms: int = 180


class WakeWordDetector(Protocol):
    def process(self, frame: AudioFrame) -> WakeDetection | None: ...


class VoiceActivityDetector(Protocol):
    def process(self, frame: AudioFrame) -> VoiceActivity: ...
    def reset(self) -> None: ...


class SpeechRecognizer(Protocol):
    def transcribe(self, frames: Sequence[AudioFrame]) -> str: ...


class SpeechSynthesizer(Protocol):
    def synthesize(self, text: str) -> Sequence[AudioFrame]: ...


class AudioOutput(Protocol):
    def play(self, frames: Sequence[AudioFrame]) -> None: ...
    def stop(self) -> None: ...


class InterruptibleAudioOutput(AudioOutput, Protocol):
    """Audio output that can cooperatively abort an in-progress playback.

    Production realtime adapters should implement this contract so a barge-in can
    interrupt audio already being rendered, not merely prevent queued audio from
    starting. ``cancel_event`` belongs to the playback worker and must not be reused
    for a later turn.
    """

    def play_interruptible(
        self,
        frames: Sequence[AudioFrame],
        *,
        cancel_event: Event,
    ) -> None: ...
