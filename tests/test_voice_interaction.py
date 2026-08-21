from __future__ import annotations

from marina.core.voice import VoiceInteractionController
from marina.domain.audio import AudioFrame, AudioInteractionMode, AudioPolicy, VoiceActivity, WakeDetection


class FakeWake:
    def __init__(self):
        self.detection = None

    def process(self, frame):
        result, self.detection = self.detection, None
        return result


class FakeVad:
    def __init__(self):
        self.values = []

    def reset(self):
        pass

    def process(self, frame):
        return self.values.pop(0) if self.values else VoiceActivity(False)


def frame():
    return AudioFrame(b"\x00" * 640)


def test_wake_word_opens_listening_and_emits_utterance_after_silence():
    wake = FakeWake()
    vad = FakeVad()
    events = []
    controller = VoiceInteractionController(
        policy=AudioPolicy(end_silence_ms=100, min_speech_ms=40),
        wakeword=wake,
        vad=vad,
        emit=events.append,
    )
    controller.arm()
    wake.detection = WakeDetection("hey marina", 0.95)
    controller.on_audio(frame(), now=0.0)
    assert controller.stage.value == "listening"

    vad.values = [VoiceActivity(True), VoiceActivity(True), VoiceActivity(False)]
    controller.on_audio(frame(), now=0.05)
    controller.on_audio(frame(), now=0.10)
    controller.on_audio(frame(), now=0.25)
    assert controller.stage.value == "processing"
    assert any(event.name == "utterance_ready" for event in events)
    assert len(controller.utterance()) == 0


def test_push_to_talk_is_a_first_class_entry_mode():
    events = []
    controller = VoiceInteractionController(mode=AudioInteractionMode.WAKE_WORD) if False else VoiceInteractionController(emit=events.append)
    controller.set_mode(AudioInteractionMode.PUSH_TO_TALK)
    controller.arm()
    controller.push_to_talk_pressed()
    assert controller.stage.value == "listening"
    controller.on_audio(frame())
    controller.push_to_talk_released()
    assert controller.stage.value == "processing"


def test_speaking_can_be_interrupted_for_barge_in():
    events = []
    controller = VoiceInteractionController(emit=events.append)
    controller.arm()
    controller.speaking_started()
    controller.on_wake_while_speaking(WakeDetection("hey marina", 0.9))
    assert controller.stage.value == "listening"
    assert any(event.name == "barge_in" for event in events)


def test_follow_up_window_reenters_listening_on_speech():
    vad = FakeVad()
    controller = VoiceInteractionController(vad=vad)
    controller.arm()
    controller.speaking_started()
    controller.speaking_finished(allow_follow_up=True)
    assert controller.stage.value == "follow_up"
    vad.values = [VoiceActivity(True)]
    controller.on_audio(frame(), now=0.0)
    assert controller.stage.value == "listening"


def test_max_utterance_uses_the_audio_timeline():
    controller = VoiceInteractionController(
        policy=AudioPolicy(min_speech_ms=0, end_silence_ms=10_000, max_utterance_ms=100),
        vad=FakeVad(),
    )
    controller.arm()
    controller.trigger_listening("test", now=10.0)
    controller.on_audio(frame(), now=10.05)
    assert controller.stage.value == "listening"
    controller.on_audio(frame(), now=10.101)
    assert controller.stage.value == "processing"


def test_follow_up_speech_uses_the_same_audio_timeline():
    vad = FakeVad()
    controller = VoiceInteractionController(
        policy=AudioPolicy(follow_up_window_ms=1000),
        vad=vad,
    )
    controller.arm()
    controller.speaking_finished(allow_follow_up=True)
    vad.values = [VoiceActivity(True)]
    controller.on_audio(frame(), now=0.25)
    assert controller.stage.value == "listening"
