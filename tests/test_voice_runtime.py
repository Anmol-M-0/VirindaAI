from __future__ import annotations

from pathlib import Path
from threading import Event
from time import sleep

from virinda.application.service import AssistantService
from virinda.core.events import InMemoryEventBus
from virinda.core.tokenizer import StreamingSentenceTokenizer
from virinda.core.voice import VoiceInteractionController, VoiceSignal
from virinda.core.voice_runtime import VoiceTurnRuntime
from virinda.domain.audio import AudioFrame, AudioPolicy, VoiceActivity
from virinda.domain.events import ResponseCompleted, ResponseDelta
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
        return "hello from voice"


class FakeTTS:
    def __init__(self):
        self.texts = []

    def synthesize(self, text):
        self.texts.append(text)
        return [AudioFrame(b"speech")]


class FakeOutput:
    def __init__(self):
        self.played = []
        self.stopped = 0

    def play(self, frames):
        self.played.append(list(frames))

    def stop(self):
        self.stopped += 1


class InterruptibleOutput(FakeOutput):
    def __init__(self):
        super().__init__()
        self.started = Event()

    def play_interruptible(self, frames, *, cancel_event):
        self.started.set()
        while not cancel_event.is_set():
            sleep(0.005)
        self.stopped += 1


def make_service(tmp_path: Path):
    store = SQLiteConversationStore(tmp_path / "m.sqlite3")
    bus = InMemoryEventBus()
    router = StaticProviderRouter({"echo": EchoProvider()}, default="echo")
    return AssistantService(router=router, store=store, event_bus=bus)


def test_voice_turn_uses_same_service_and_serialized_tts(tmp_path: Path):
    service = make_service(tmp_path)
    signals = []
    output = FakeOutput()
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
        emit=signals.append,
    )
    controller.arm()
    controller.trigger_listening("test")
    controller.on_audio(AudioFrame(b"x"), now=0.0)
    controller.push_to_talk_released()
    for _ in range(30):
        if len(service.store.load_messages(service.snapshot().session_id)) == 2:
            break
        sleep(0.01)
    for _ in range(30):
        if output.played:
            break
        sleep(0.01)
    messages = service.store.load_messages(service.snapshot().session_id)
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].content == "hello from voice"
    assert tts.texts == ["Virinda received: hello from voice"]
    assert output.played
    runtime.close()
    service.close()


def test_barge_in_stops_tts_and_cancels_service(tmp_path: Path):
    service = make_service(tmp_path)
    output = FakeOutput()
    runtime = VoiceTurnRuntime(
        service=service,
        controller=VoiceInteractionController(),
        recognizer=FakeRecognizer(),
        synthesizer=FakeTTS(),
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
    )
    runtime.controller.arm()
    runtime.controller.speaking_started()
    runtime.controller.on_wake_while_speaking()
    assert output.stopped > 0
    assert runtime.controller.stage.value == "listening"
    runtime.close()
    service.close()


class BlockingRecognizer(FakeRecognizer):
    def __init__(self):
        import threading

        self.started = threading.Event()
        self.release = threading.Event()

    def transcribe(self, frames):
        self.started.set()
        self.release.wait(timeout=2)
        return "stale utterance"


def test_barge_in_invalidates_inflight_stt(tmp_path: Path):
    service = make_service(tmp_path)
    output = FakeOutput()
    recognizer = BlockingRecognizer()
    runtime = VoiceTurnRuntime(
        service=service,
        controller=VoiceInteractionController(),
        recognizer=recognizer,
        synthesizer=FakeTTS(),
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
    )
    runtime.controller.arm()
    runtime.controller.trigger_listening("test")
    runtime.controller.on_audio(AudioFrame(b"x"), now=0.0)
    runtime.controller.push_to_talk_released()
    assert recognizer.started.wait(timeout=1)
    runtime.controller.emit(VoiceSignal("barge_in", {"reason": "test"}))
    recognizer.release.set()
    for _ in range(30):
        if not service.store.load_messages(service.snapshot().session_id):
            break
        sleep(0.01)
    assert service.store.load_messages(service.snapshot().session_id) == []
    runtime.close()
    service.close()


class BlockingTTS(FakeTTS):
    def __init__(self):
        super().__init__()
        import threading

        self.started = threading.Event()
        self.release = threading.Event()

    def synthesize(self, text):
        self.started.set()
        self.release.wait(timeout=2)
        return super().synthesize(text)


def test_barge_in_invalidates_queued_tts_generation(tmp_path: Path):
    service = make_service(tmp_path)
    output = FakeOutput()
    tts = BlockingTTS()
    runtime = VoiceTurnRuntime(
        service=service,
        controller=VoiceInteractionController(),
        recognizer=FakeRecognizer(),
        synthesizer=tts,
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
    )

    generation = service.generations.start()
    runtime.publish(ResponseDelta(generation_id=generation, sequence=1, text="stale"))
    runtime.publish(ResponseCompleted(generation_id=generation, sequence=2, text="stale"))
    assert tts.started.wait(timeout=1)
    service.cancel("barge_in")
    tts.release.set()
    for _ in range(50):
        if output.played:
            break
        sleep(0.01)
    assert output.played == []
    runtime.close()
    service.close()


def test_barge_in_interrupts_in_progress_tts_playback(tmp_path: Path):
    service = make_service(tmp_path)
    output = InterruptibleOutput()
    runtime = VoiceTurnRuntime(
        service=service,
        controller=VoiceInteractionController(),
        recognizer=FakeRecognizer(),
        synthesizer=FakeTTS(),
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
    )

    generation = service.generations.start()
    runtime.publish(ResponseDelta(generation_id=generation, sequence=1, text="interrupt me"))
    runtime.publish(ResponseCompleted(generation_id=generation, sequence=2, text="interrupt me"))
    assert output.started.wait(timeout=1)
    service.cancel("barge_in")
    runtime.stop("barge_in")
    for _ in range(30):
        if runtime._tts_worker is None:
            break
        sleep(0.01)
    assert output.played == []
    runtime.close()
    service.close()


def test_new_tts_worker_cannot_uncancel_old_worker(tmp_path: Path):
    service = make_service(tmp_path)
    output = InterruptibleOutput()
    runtime = VoiceTurnRuntime(
        service=service,
        controller=VoiceInteractionController(),
        recognizer=FakeRecognizer(),
        synthesizer=FakeTTS(),
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
    )

    first = service.generations.start()
    runtime.publish(ResponseDelta(generation_id=first, sequence=1, text="first"))
    runtime.publish(ResponseCompleted(generation_id=first, sequence=2, text="first"))
    assert output.started.wait(timeout=1)
    runtime._stop_tts()
    second = service.generations.start()
    output.started.clear()
    runtime.publish(ResponseDelta(generation_id=second, sequence=3, text="second"))
    runtime.publish(ResponseCompleted(generation_id=second, sequence=4, text="second"))
    assert output.started.wait(timeout=1)
    runtime._stop_tts()
    assert output.stopped >= 2
    runtime.close()
    service.close()


class FailingInterruptibleOutput(InterruptibleOutput):
    def play_interruptible(self, frames, *, cancel_event):
        self.started.set()
        cancel_event.wait(timeout=1)
        raise RuntimeError("stopped by audio backend")


def test_expected_playback_cancel_is_not_reported_as_tts_error(tmp_path: Path):
    service = make_service(tmp_path)
    output = FailingInterruptibleOutput()
    signals = []
    runtime = VoiceTurnRuntime(
        service=service,
        controller=VoiceInteractionController(),
        recognizer=FakeRecognizer(),
        synthesizer=FakeTTS(),
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
        emit=signals.append,
    )
    generation = service.generations.start()
    runtime.publish(ResponseDelta(generation_id=generation, sequence=1, text="cancel me"))
    runtime.publish(ResponseCompleted(generation_id=generation, sequence=2, text="cancel me"))
    assert output.started.wait(timeout=1)
    runtime.stop("barge_in")
    for _ in range(50):
        if runtime._tts_worker is None:
            break
        sleep(0.01)
    assert not any(signal.name == "tts_error" for signal in signals)
    runtime.close()
    service.close()


class FirstCallBlockingTTS(FakeTTS):
    def __init__(self):
        super().__init__()
        self.first_started = Event()
        self.release_first = Event()
        self.calls = 0

    def synthesize(self, text):
        self.calls += 1
        if self.calls == 1:
            self.first_started.set()
            self.release_first.wait(timeout=2)
        return super().synthesize(text)


def test_new_tts_worker_uses_isolated_queue_while_old_worker_is_stopping(tmp_path: Path):
    service = make_service(tmp_path)
    output = FakeOutput()
    tts = FirstCallBlockingTTS()
    runtime = VoiceTurnRuntime(
        service=service,
        controller=VoiceInteractionController(),
        recognizer=FakeRecognizer(),
        synthesizer=tts,
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
    )

    first = service.generations.start()
    runtime.publish(ResponseDelta(generation_id=first, sequence=1, text="first"))
    runtime.publish(ResponseCompleted(generation_id=first, sequence=2, text="first"))
    assert tts.first_started.wait(timeout=1)
    runtime._stop_tts()

    second = service.generations.start()
    runtime.publish(ResponseDelta(generation_id=second, sequence=3, text="second"))
    runtime.publish(ResponseCompleted(generation_id=second, sequence=4, text="second"))
    for _ in range(50):
        if output.played:
            break
        sleep(0.01)
    assert output.played
    assert [frame.pcm for frame in output.played[-1]] == [b"speech"]

    tts.release_first.set()
    for _ in range(50):
        if tts.calls >= 2:
            break
        sleep(0.01)
    runtime._stop_tts()
    runtime.close()
    service.close()


def test_close_blocks_late_controller_and_service_events(tmp_path: Path):
    service = make_service(tmp_path)
    output = FakeOutput()
    signals = []
    runtime = VoiceTurnRuntime(
        service=service,
        controller=VoiceInteractionController(),
        recognizer=FakeRecognizer(),
        synthesizer=FakeTTS(),
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
        emit=signals.append,
    )

    runtime.close()

    runtime.controller.emit(VoiceSignal("utterance_ready", {"reason": "late", "frames": 1}))
    generation = service.generations.start()
    runtime.publish(ResponseDelta(generation_id=generation, sequence=1, text="late response"))
    runtime.publish(ResponseCompleted(generation_id=generation, sequence=2, text="late response"))

    assert signals == []
    assert output.played == []
    assert output.stopped == 1
    service.close()


def test_close_is_idempotent_and_does_not_double_stop_output(tmp_path: Path):
    service = make_service(tmp_path)
    output = FakeOutput()
    runtime = VoiceTurnRuntime(
        service=service,
        controller=VoiceInteractionController(),
        recognizer=FakeRecognizer(),
        synthesizer=FakeTTS(),
        output=output,
        tokenizer=StreamingSentenceTokenizer(),
    )

    runtime.close()
    runtime.close()

    assert output.stopped == 1
    service.close()
