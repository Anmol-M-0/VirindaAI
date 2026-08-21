from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic_ns
from uuid import UUID, uuid4


class VoiceInteractionState(StrEnum):
    STARTED = "started"
    WAKE_DETECTED = "wake_detected"
    STT_ACTIVE = "stt_active"
    GENERATING = "generating"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"


def _diff_ms(start_ns: int | None, end_ns: int | None) -> float | None:
    if start_ns is None or end_ns is None:
        return None
    if end_ns < start_ns:
        return 0.0
    return round((end_ns - start_ns) / 1_000_000.0, 2)


@dataclass(frozen=True, slots=True)
class LatencyMetrics:
    wake_to_stt_ms: float | None = None
    stt_duration_ms: float | None = None
    stt_to_llm_first_token_ms: float | None = None
    llm_first_token_to_tts_audio_ms: float | None = None
    wake_to_first_audio_ms: float | None = None
    barge_in_to_audio_stop_ms: float | None = None
    barge_in_to_cancellation_complete_ms: float | None = None
    total_interaction_ms: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "wake_to_stt_ms": self.wake_to_stt_ms,
            "stt_duration_ms": self.stt_duration_ms,
            "stt_to_llm_first_token_ms": self.stt_to_llm_first_token_ms,
            "llm_first_token_to_tts_audio_ms": self.llm_first_token_to_tts_audio_ms,
            "wake_to_first_audio_ms": self.wake_to_first_audio_ms,
            "barge_in_to_audio_stop_ms": self.barge_in_to_audio_stop_ms,
            "barge_in_to_cancellation_complete_ms": self.barge_in_to_cancellation_complete_ms,
            "total_interaction_ms": self.total_interaction_ms,
        }


@dataclass(slots=True)
class VoiceInteractionTrace:
    interaction_id: UUID = field(default_factory=uuid4)
    session_id: str = ""
    started_at_mono_ns: int = field(default_factory=monotonic_ns)

    wake_at_mono_ns: int | None = None
    stt_start_at_mono_ns: int | None = None
    stt_first_result_at_mono_ns: int | None = None
    stt_end_at_mono_ns: int | None = None

    llm_start_at_mono_ns: int | None = None
    llm_first_token_at_mono_ns: int | None = None
    llm_end_at_mono_ns: int | None = None

    tts_first_sentence_at_mono_ns: int | None = None
    tts_first_audio_at_mono_ns: int | None = None
    tts_end_at_mono_ns: int | None = None

    barge_in_at_mono_ns: int | None = None
    audio_stop_at_mono_ns: int | None = None
    cancellation_complete_at_mono_ns: int | None = None

    ended_at_mono_ns: int | None = None

    state: VoiceInteractionState = VoiceInteractionState.STARTED
    transcript: str = ""
    response_text: str = ""
    error: str | None = None

    def mark_wake(self) -> None:
        if self.wake_at_mono_ns is None:
            self.wake_at_mono_ns = monotonic_ns()
        self.state = VoiceInteractionState.WAKE_DETECTED

    def mark_stt_start(self) -> None:
        if self.stt_start_at_mono_ns is None:
            self.stt_start_at_mono_ns = monotonic_ns()
        self.state = VoiceInteractionState.STT_ACTIVE

    def mark_stt_first_result(self, partial_text: str = "") -> None:
        if self.stt_first_result_at_mono_ns is None:
            self.stt_first_result_at_mono_ns = monotonic_ns()

    def mark_stt_end(self, transcript: str) -> None:
        if self.stt_end_at_mono_ns is None:
            self.stt_end_at_mono_ns = monotonic_ns()
        self.transcript = transcript

    def mark_llm_start(self) -> None:
        if self.llm_start_at_mono_ns is None:
            self.llm_start_at_mono_ns = monotonic_ns()
        self.state = VoiceInteractionState.GENERATING

    def mark_llm_first_token(self) -> None:
        if self.llm_first_token_at_mono_ns is None:
            self.llm_first_token_at_mono_ns = monotonic_ns()

    def mark_llm_end(self, full_text: str = "") -> None:
        if self.llm_end_at_mono_ns is None:
            self.llm_end_at_mono_ns = monotonic_ns()
        if full_text:
            self.response_text = full_text

    def mark_tts_first_sentence(self) -> None:
        if self.tts_first_sentence_at_mono_ns is None:
            self.tts_first_sentence_at_mono_ns = monotonic_ns()

    def mark_tts_first_audio(self) -> None:
        if self.tts_first_audio_at_mono_ns is None:
            self.tts_first_audio_at_mono_ns = monotonic_ns()
        self.state = VoiceInteractionState.SPEAKING

    def mark_tts_end(self) -> None:
        if self.tts_end_at_mono_ns is None:
            self.tts_end_at_mono_ns = monotonic_ns()

    def mark_barge_in(self) -> None:
        if self.barge_in_at_mono_ns is None:
            self.barge_in_at_mono_ns = monotonic_ns()
        self.state = VoiceInteractionState.INTERRUPTED

    def mark_audio_stop(self) -> None:
        if self.audio_stop_at_mono_ns is None:
            self.audio_stop_at_mono_ns = monotonic_ns()

    def mark_cancellation_complete(self) -> None:
        if self.cancellation_complete_at_mono_ns is None:
            self.cancellation_complete_at_mono_ns = monotonic_ns()
        self.ended_at_mono_ns = self.cancellation_complete_at_mono_ns

    def mark_completed(self) -> None:
        if self.ended_at_mono_ns is None:
            self.ended_at_mono_ns = monotonic_ns()
        if self.state not in {VoiceInteractionState.INTERRUPTED, VoiceInteractionState.FAILED}:
            self.state = VoiceInteractionState.COMPLETED

    def mark_failed(self, error: str) -> None:
        if self.ended_at_mono_ns is None:
            self.ended_at_mono_ns = monotonic_ns()
        self.state = VoiceInteractionState.FAILED
        self.error = error

    def compute_metrics(self) -> LatencyMetrics:
        ref_start = self.wake_at_mono_ns or self.started_at_mono_ns
        wake_to_stt = _diff_ms(ref_start, self.stt_end_at_mono_ns)
        stt_dur = _diff_ms(self.stt_start_at_mono_ns, self.stt_end_at_mono_ns)
        stt_to_llm = _diff_ms(self.stt_end_at_mono_ns, self.llm_first_token_at_mono_ns)
        llm_to_tts = _diff_ms(self.llm_first_token_at_mono_ns, self.tts_first_audio_at_mono_ns)
        wake_to_audio = _diff_ms(ref_start, self.tts_first_audio_at_mono_ns)
        barge_in_stop = _diff_ms(self.barge_in_at_mono_ns, self.audio_stop_at_mono_ns)
        barge_in_cancel = _diff_ms(self.barge_in_at_mono_ns, self.cancellation_complete_at_mono_ns)
        total = _diff_ms(self.started_at_mono_ns, self.ended_at_mono_ns or monotonic_ns())

        return LatencyMetrics(
            wake_to_stt_ms=wake_to_stt,
            stt_duration_ms=stt_dur,
            stt_to_llm_first_token_ms=stt_to_llm,
            llm_first_token_to_tts_audio_ms=llm_to_tts,
            wake_to_first_audio_ms=wake_to_audio,
            barge_in_to_audio_stop_ms=barge_in_stop,
            barge_in_to_cancellation_complete_ms=barge_in_cancel,
            total_interaction_ms=total,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "interaction_id": str(self.interaction_id),
            "session_id": self.session_id,
            "state": self.state.value,
            "transcript": self.transcript,
            "response_text": self.response_text,
            "error": self.error,
            "metrics": self.compute_metrics().to_dict(),
        }


@dataclass(frozen=True, slots=True)
class VoiceTurnResult:
    trace: VoiceInteractionTrace
    metrics: LatencyMetrics
    transcript: str
    response: str
    interrupted: bool
