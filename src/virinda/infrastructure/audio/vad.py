from __future__ import annotations

import collections
import math
import struct
from dataclasses import dataclass
from enum import Enum


class VADState(str, Enum):
    SILENCE = "silence"
    SPEECH = "speech"
    ENDPOINT = "endpoint"
    TIMEOUT = "timeout"


@dataclass(slots=True)
class VADFrameResult:
    state: VADState
    is_speech: bool
    rms_energy: float
    zcr: float


class EnergyVAD:
    """Frame-level energy and zero-crossing rate voice activity detector with pre-roll and endpointing."""

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 20,
        speech_start_energy: float = 0.015,
        speech_continue_energy: float = 0.008,
        min_zcr: float = 0.02,
        max_zcr: float = 0.65,
        pre_roll_ms: int = 300,
        endpoint_silence_ms: int = 800,
        max_duration_s: float = 15.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_samples = int(sample_rate * (frame_duration_ms / 1000.0))
        self.frame_bytes = self.frame_samples * 2  # 16-bit PCM

        self.speech_start_energy = speech_start_energy
        self.speech_continue_energy = speech_continue_energy
        self.min_zcr = min_zcr
        self.max_zcr = max_zcr

        self.pre_roll_frames = max(1, int(pre_roll_ms / frame_duration_ms))
        self.endpoint_silence_frames = max(1, int(endpoint_silence_ms / frame_duration_ms))
        self.max_frames = int((max_duration_s * 1000.0) / frame_duration_ms)

        self._state = VADState.SILENCE
        self._pre_roll_buffer: collections.deque[bytes] = collections.deque(
            maxlen=self.pre_roll_frames
        )
        self._speech_frames: list[bytes] = []
        self._silence_count = 0
        self._total_frames = 0

    def reset(self) -> None:
        self._state = VADState.SILENCE
        self._pre_roll_buffer.clear()
        self._speech_frames.clear()
        self._silence_count = 0
        self._total_frames = 0

    def _compute_metrics(self, frame_bytes: bytes) -> tuple[float, float]:
        num_samples = len(frame_bytes) // 2
        if num_samples == 0:
            return 0.0, 0.0

        samples = struct.unpack(f"<{num_samples}h", frame_bytes[: num_samples * 2])
        # Normalized samples in [-1.0, 1.0]
        norm_samples = [s / 32768.0 for s in samples]

        # RMS Energy
        sum_sq = sum(s * s for s in norm_samples)
        rms = math.sqrt(sum_sq / float(num_samples))

        # Zero-Crossing Rate
        zero_crossings = sum(
            1
            for i in range(1, len(norm_samples))
            if (norm_samples[i] >= 0 > norm_samples[i - 1])
            or (norm_samples[i] < 0 <= norm_samples[i - 1])
        )
        zcr = zero_crossings / float(num_samples)

        return rms, zcr

    def process_frame(self, frame_bytes: bytes) -> VADFrameResult:
        """Processes a single 20ms audio frame and updates VAD state."""
        self._total_frames += 1
        rms, zcr = self._compute_metrics(frame_bytes)

        is_voice_like = (
            rms
            >= (
                self.speech_continue_energy
                if self._state == VADState.SPEECH
                else self.speech_start_energy
            )
            and self.min_zcr <= zcr <= self.max_zcr
        )

        if self._state == VADState.SILENCE:
            self._pre_roll_buffer.append(frame_bytes)
            if is_voice_like:
                self._state = VADState.SPEECH
                self._speech_frames.extend(self._pre_roll_buffer)
                self._speech_frames.append(frame_bytes)
                self._pre_roll_buffer.clear()
                self._silence_count = 0
        elif self._state == VADState.SPEECH:
            self._speech_frames.append(frame_bytes)
            if is_voice_like:
                self._silence_count = 0
            else:
                self._silence_count += 1
                if self._silence_count >= self.endpoint_silence_frames:
                    self._state = VADState.ENDPOINT

        if self._total_frames >= self.max_frames and self._state != VADState.ENDPOINT:
            self._state = VADState.TIMEOUT

        return VADFrameResult(
            state=self._state,
            is_speech=is_voice_like,
            rms_energy=rms,
            zcr=zcr,
        )

    def get_recorded_audio(self) -> bytes:
        """Returns concatenated PCM bytes recorded during the utterance."""
        return b"".join(self._speech_frames)
