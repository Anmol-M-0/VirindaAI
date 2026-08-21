from __future__ import annotations

from pathlib import Path
from time import sleep

from virinda.application.service import AssistantService
from virinda.core.events import InMemoryEventBus
from virinda.core.tokenizer import StreamingSentenceTokenizer
from virinda.core.trace import VoiceInteractionState, VoiceTurnResult
from virinda.core.voice import VoiceInteractionController
from virinda.core.voice_runtime import VoiceTurnRuntime
from virinda.domain.audio import AudioFrame, AudioPolicy, VoiceActivity
from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore
from virinda.infrastructure.providers.echo import EchoProvider
from virinda.infrastructure.providers.router import StaticProviderRouter


class StressVad:
    def reset(self):
        pass

    def process(self, frame):
        return VoiceActivity(True)


class StressRecognizer:
    def transcribe(self, frames):
        return "repeat test sentence for stress testing"


class StressTTS:
    def __init__(self):
        self.count = 0

    def synthesize(self, text):
        self.count += 1
        return [AudioFrame(b"stress_audio")]


class StressInterruptibleOutput:
    def __init__(self):
        self.playback_count = 0
        self.stopped_count = 0

    def play_interruptible(self, frames, *, cancel_event):
        self.playback_count += 1
        for _ in range(20):
            if cancel_event.is_set():
                self.stopped_count += 1
                return
            sleep(0.002)

    def stop(self):
        self.stopped_count += 1


def test_rapid_barge_in_cycles(tmp_path: Path):
    store = SQLiteConversationStore(tmp_path / "stress.sqlite3")
    bus = InMemoryEventBus()
    router = StaticProviderRouter({"echo": EchoProvider()}, default="echo")
    service = AssistantService(router=router, store=store, event_bus=bus)

    results: list[VoiceTurnResult] = []
    output = StressInterruptibleOutput()
    tts = StressTTS()
    controller = VoiceInteractionController(
        policy=AudioPolicy(min_speech_ms=0, end_silence_ms=0),
        vad=StressVad(),
    )
    runtime = VoiceTurnRuntime(
        service=service,
        controller=controller,
        recognizer=StressRecognizer(),
        synthesizer=tts,
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
        on_turn_result=results.append,
    )

    # Run 25 rapid speech-and-interrupt cycles
    for i in range(25):
        controller.arm()
        controller.trigger_listening("wake_word")
        controller.on_audio(AudioFrame(b"x"), now=0.0)
        controller.push_to_talk_released()

        # Let it begin processing / speaking briefly
        sleep(0.01)

        # Interrupt mid-turn
        controller.on_wake_while_speaking()

        # Brief settle time
        sleep(0.005)

    # Let runtime settle
    for _ in range(50):
        if len(results) == 25:
            break
        sleep(0.01)

    assert len(results) == 25
    for res in results:
        assert res.interrupted is True
        assert res.trace.state == VoiceInteractionState.INTERRUPTED
        assert res.metrics.barge_in_to_cancellation_complete_ms is not None

    runtime.close()
    service.close()


def test_cancellation_during_active_playback(tmp_path: Path):
    store = SQLiteConversationStore(tmp_path / "cancel_playback.sqlite3")
    bus = InMemoryEventBus()
    router = StaticProviderRouter({"echo": EchoProvider()}, default="echo")
    service = AssistantService(router=router, store=store, event_bus=bus)

    results: list[VoiceTurnResult] = []
    output = StressInterruptibleOutput()
    controller = VoiceInteractionController()
    runtime = VoiceTurnRuntime(
        service=service,
        controller=controller,
        recognizer=StressRecognizer(),
        synthesizer=StressTTS(),
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
        on_turn_result=results.append,
    )

    controller.arm()
    controller.trigger_listening("push_to_talk")
    controller.on_audio(AudioFrame(b"x"), now=0.0)
    controller.push_to_talk_released()

    for _ in range(50):
        if output.playback_count > 0:
            break
        sleep(0.005)

    assert output.playback_count > 0

    # User interrupts while audio is playing
    runtime.stop(reason="user_barge_in")

    for _ in range(50):
        if results:
            break
        sleep(0.005)

    assert len(results) == 1
    assert results[0].interrupted is True
    assert output.stopped_count > 0

    runtime.close()
    service.close()
