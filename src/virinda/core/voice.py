from __future__ import annotations

from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import monotonic

from virinda.domain.audio import (
    AudioFrame,
    AudioInteractionMode,
    AudioPolicy,
    AudioStage,
    VoiceActivityDetector,
    WakeDetection,
    WakeWordDetector,
)


@dataclass(frozen=True, slots=True)
class VoiceSignal:
    name: str
    payload: dict[str, object]


class VoiceInteractionController:
    """Pure control-plane policy for passive listening and alternate voice entry modes.

    The controller never performs DSP or model inference itself. It consumes microphone
    frames and detector results, and emits small control signals for the audio worker.
    This keeps realtime audio concerns independent from the assistant coordinator.
    """

    def __init__(
        self,
        *,
        policy: AudioPolicy | None = None,
        wakeword: WakeWordDetector | None = None,
        vad: VoiceActivityDetector | None = None,
        emit: Callable[[VoiceSignal], None] | None = None,
    ) -> None:
        self.policy = policy or AudioPolicy()
        self.wakeword = wakeword
        self.vad = vad
        self.emit = emit or (lambda _signal: None)
        self.mode = AudioInteractionMode.WAKE_WORD
        self.stage = AudioStage.DISARMED
        self._pre_roll: deque[AudioFrame] = deque(maxlen=self._pre_roll_frames())
        self._utterance: list[AudioFrame] = []
        self._speech_started_at: float | None = None
        self._last_speech_at: float | None = None
        self._listening_started_at: float | None = None
        self._follow_up_deadline: float | None = None
        self._wake_latched = False

    def arm(self) -> None:
        self.stage = AudioStage.ARMED
        self._reset_buffers()
        self.emit(VoiceSignal("armed", {"mode": self.mode.value}))

    def disarm(self) -> None:
        self.stage = AudioStage.DISARMED
        self._reset_buffers()
        self.emit(VoiceSignal("disarmed", {}))

    def set_mode(self, mode: AudioInteractionMode) -> None:
        self.mode = mode
        self._reset_buffers()
        self.emit(VoiceSignal("mode_changed", {"mode": mode.value}))

    def trigger_listening(self, reason: str = "external", *, now: float | None = None) -> None:
        self._start_listening(reason, now=now)

    def push_to_talk_pressed(self, *, now: float | None = None) -> None:
        if self.stage == AudioStage.SPEAKING:
            self.emit(VoiceSignal("barge_in", {"reason": "push_to_talk"}))
        self._start_listening("push_to_talk", now=now)

    def push_to_talk_released(self) -> None:
        if self.stage == AudioStage.LISTENING:
            self._finish_listening("push_to_talk_released")

    def toggle_listen(self, *, now: float | None = None) -> None:
        if self.stage == AudioStage.LISTENING:
            self._finish_listening("toggle_released")
        else:
            self._start_listening("toggle_listen", now=now)

    def speaking_started(self) -> None:
        self.stage = AudioStage.SPEAKING
        self._reset_buffers(keep_pre_roll=False)
        self.emit(VoiceSignal("speaking_started", {}))

    def speaking_finished(self, *, allow_follow_up: bool = True) -> None:
        if allow_follow_up:
            self.stage = AudioStage.FOLLOW_UP
            self._follow_up_deadline = monotonic() + self.policy.follow_up_window_ms / 1000
            self.emit(
                VoiceSignal("follow_up_window_open", {"window_ms": self.policy.follow_up_window_ms})
            )
        else:
            self.arm()

    def cancel(self) -> None:
        self._reset_buffers()
        self.stage = (
            AudioStage.ARMED if self.mode == AudioInteractionMode.WAKE_WORD else AudioStage.DISARMED
        )
        self.emit(VoiceSignal("cancelled", {}))

    def on_audio(self, frame: AudioFrame, now: float | None = None) -> None:
        now = monotonic() if now is None else now
        if self.stage == AudioStage.DISARMED:
            return

        self._pre_roll.append(frame)

        if self.stage == AudioStage.FOLLOW_UP:
            if self._follow_up_deadline is not None and now > self._follow_up_deadline:
                self.arm()
                return
            if self.vad is not None:
                activity = self.vad.process(frame)
                if activity.speech:
                    self._start_listening("follow_up", now=now)
                else:
                    return

        elif self.stage == AudioStage.ARMED:
            if self.mode == AudioInteractionMode.WAKE_WORD and self.wakeword is not None:
                detection = self.wakeword.process(frame)
                if detection is not None and detection.confidence >= self.policy.wake_threshold:
                    self._wake_latched = True
                    self._start_listening("wake_word", detection, now=now)
            elif self.mode in {
                AudioInteractionMode.TOGGLE_LISTEN,
                AudioInteractionMode.PUSH_TO_TALK,
            }:
                return

        if self.stage != AudioStage.LISTENING:
            return

        self._utterance.append(frame)
        if self.vad is not None:
            activity = self.vad.process(frame)
            if activity.speech:
                if self._speech_started_at is None:
                    self._speech_started_at = now
                    self.emit(VoiceSignal("speech_started", {"at": now}))
                self._last_speech_at = now
            elif self._speech_started_at is not None and self._last_speech_at is not None:
                silence_ms = (now - self._last_speech_at) * 1000
                speech_ms = (self._last_speech_at - self._speech_started_at) * 1000
                if (
                    speech_ms >= self.policy.min_speech_ms
                    and silence_ms >= self.policy.end_silence_ms
                ):
                    self._finish_listening("silence")
                    return
        if self._listening_started_at is not None:
            elapsed_ms = (now - self._listening_started_at) * 1000
            if elapsed_ms >= self.policy.max_utterance_ms:
                self._finish_listening("max_duration")

    def mark_processing(self) -> None:
        self.stage = AudioStage.PROCESSING
        self.emit(VoiceSignal("processing_started", {}))

    def on_wake_while_speaking(self, detection: WakeDetection | None = None) -> None:
        if self.stage != AudioStage.SPEAKING:
            return
        payload: dict[str, object] = {"reason": "wake_word"}
        if detection is not None:
            payload.update(wake_word=detection.wake_word, confidence=detection.confidence)
        self.emit(VoiceSignal("barge_in", payload))
        self._start_listening("barge_in", detection)

    def utterance(self) -> Sequence[AudioFrame]:
        return tuple(self._utterance)

    def _start_listening(
        self,
        reason: str,
        detection: WakeDetection | None = None,
        *,
        now: float | None = None,
    ) -> None:
        self.stage = AudioStage.LISTENING
        self._utterance = list(self._pre_roll)
        self._speech_started_at = None
        self._last_speech_at = None
        self._listening_started_at = monotonic() if now is None else now
        self._follow_up_deadline = None
        if self.vad is not None:
            self.vad.reset()
        payload: dict[str, object] = {"reason": reason, "pre_roll_ms": self.policy.pre_roll_ms}
        if detection is not None:
            payload.update(wake_word=detection.wake_word, confidence=detection.confidence)
        self.emit(VoiceSignal("listening_started", payload))

    def _finish_listening(self, reason: str) -> None:
        frames = tuple(self._utterance)
        self.stage = AudioStage.PROCESSING
        self.emit(VoiceSignal("utterance_ready", {"reason": reason, "frames": len(frames)}))
        self._utterance = []
        self._speech_started_at = None
        self._last_speech_at = None
        self._listening_started_at = None

    def _reset_buffers(self, *, keep_pre_roll: bool = True) -> None:
        self._utterance.clear()
        self._speech_started_at = None
        self._last_speech_at = None
        self._listening_started_at = None
        self._follow_up_deadline = None
        self._wake_latched = False
        if not keep_pre_roll:
            self._pre_roll.clear()
        if self.vad is not None:
            self.vad.reset()

    def _pre_roll_frames(self) -> int:
        # 20 ms frames are the default for the audio worker; keeping this bounded matters
        # because the always-on wake stage must remain cheap and predictable.
        frame_ms = 20
        return max(1, self.policy.pre_roll_ms // frame_ms)
