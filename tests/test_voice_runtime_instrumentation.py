from __future__ import annotations

from pathlib import Path
from threading import Event
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


class FakeVad:
    def reset(self):
        pass

    def process(self, frame):
        return VoiceActivity(True)


class FakeRecognizer:
    def transcribe(self, frames):
        return "hello virinda"


class FakeTTS:
    def __init__(self):
        self.texts = []

    def synthesize(self, text):
        self.texts.append(text)
        return [AudioFrame(b"speech")]


class InterruptibleOutput:
    def __init__(self):
        self.played = []
        self.stopped = 0
        self.started = Event()

    def play_interruptible(self, frames, *, cancel_event):
        self.started.set()
        for _ in range(5):
            if cancel_event.is_set():
                self.stopped += 1
                return
            sleep(0.005)
        self.played.append(list(frames))

    def stop(self):
        self.stopped += 1


def test_voice_runtime_records_trace_on_completed_turn(tmp_path: Path):
    store = SQLiteConversationStore(tmp_path / "m.sqlite3")
    bus = InMemoryEventBus()
    router = StaticProviderRouter({"echo": EchoProvider()}, default="echo")
    service = AssistantService(router=router, store=store, event_bus=bus)

    results: list[VoiceTurnResult] = []
    output = InterruptibleOutput()
    tts = FakeTTS()
    controller = VoiceInteractionController(
        policy=AudioPolicy(min_speech_ms=0, end_silence_ms=0),
        vad=FakeVad(),
    )
    runtime = VoiceTurnRuntime(
        service=service,
        controller=controller,
        recognizer=FakeRecognizer(),
        synthesizer=tts,
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
        on_turn_result=results.append,
    )

    controller.arm()
    controller.trigger_listening("wake_word")
    controller.on_audio(AudioFrame(b"x"), now=0.0)
    controller.push_to_talk_released()

    for _ in range(50):
        if results:
            break
        sleep(0.01)

    assert len(results) == 1
    result = results[0]
    assert result.transcript == "hello virinda"
    assert result.interrupted is False
    assert result.trace.state == VoiceInteractionState.COMPLETED
    assert result.metrics.stt_duration_ms is not None
    assert result.metrics.stt_to_llm_first_token_ms is not None

    runtime.close()
    service.close()


def test_voice_runtime_records_trace_on_barge_in(tmp_path: Path):
    store = SQLiteConversationStore(tmp_path / "m.sqlite3")
    bus = InMemoryEventBus()
    router = StaticProviderRouter({"echo": EchoProvider()}, default="echo")
    service = AssistantService(router=router, store=store, event_bus=bus)

    results: list[VoiceTurnResult] = []
    output = InterruptibleOutput()
    controller = VoiceInteractionController(
        policy=AudioPolicy(min_speech_ms=0, end_silence_ms=0),
        vad=FakeVad(),
    )
    runtime = VoiceTurnRuntime(
        service=service,
        controller=controller,
        recognizer=FakeRecognizer(),
        synthesizer=FakeTTS(),
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
        on_turn_result=results.append,
    )

    controller.arm()
    controller.trigger_listening("push_to_talk")
    controller.on_audio(AudioFrame(b"x"), now=0.0)
    controller.push_to_talk_released()

    # Wait for TTS output to start
    for _ in range(50):
        if output.started.is_set():
            break
        sleep(0.01)

    assert output.started.is_set()

    # User interrupts via wake while speaking
    controller.on_wake_while_speaking()

    for _ in range(50):
        if results:
            break
        sleep(0.01)

    assert len(results) == 1
    result = results[0]
    assert result.interrupted is True
    assert result.trace.state == VoiceInteractionState.INTERRUPTED
    assert result.metrics.barge_in_to_cancellation_complete_ms is not None

    runtime.close()
    service.close()
