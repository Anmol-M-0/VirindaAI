from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from virinda.application.runtime import build_service
from virinda.config.settings import Settings
from virinda.core.acceptance.models import TurnState
from virinda.core.voice_controller import VoiceController
from virinda.infrastructure.audio.player import LinuxAudioPlayer
from virinda.infrastructure.audio.recorder import LinuxAudioRecorder
from virinda.infrastructure.audio.speech import GroqWhisperSTT, NativeTTS
from virinda.infrastructure.audio.streaming_tts import StreamingTTSWorker


@pytest.fixture
def voice_service(tmp_path: Path):
    settings = Settings.from_env().with_data_dir(tmp_path)
    return build_service(settings)


def test_voice_controller_turn_lifecycle(voice_service, tmp_path: Path):
    mock_wav = tmp_path / "test_turn.wav"
    mock_wav.write_bytes(b"RIFF" + b"\x00" * 100)

    recorder = MagicMock(spec=LinuxAudioRecorder)
    recorder.start_recording.return_value = mock_wav
    recorder.stop_recording.return_value = mock_wav

    player = MagicMock(spec=LinuxAudioPlayer)
    tts = MagicMock(spec=NativeTTS)
    stt = MagicMock(spec=GroqWhisperSTT)
    stt.transcribe_file.return_value = "Hello assistant"

    controller = VoiceController(
        service=voice_service,
        recorder=recorder,
        player=player,
        tts=tts,
        stt=stt,
    )

    # Initial state
    assert controller.state == TurnState.CREATED

    # 1. Start listening
    wav_out = controller.start_listening()
    assert wav_out == mock_wav
    assert controller.state == TurnState.LISTENING
    recorder.start_recording.assert_called_once()

    # 2. Stop listening and process
    response = controller.stop_listening_and_process(stream_stdout=False, speak_output=True)
    assert response != ""
    assert controller.state == TurnState.COMPLETED

    stt.transcribe_file.assert_called_once_with(mock_wav)
    controller.close()


def test_voice_controller_barge_in(voice_service, tmp_path: Path):
    recorder = MagicMock(spec=LinuxAudioRecorder)
    player = MagicMock(spec=LinuxAudioPlayer)
    tts = MagicMock(spec=NativeTTS)
    stt = MagicMock(spec=GroqWhisperSTT)

    controller = VoiceController(
        service=voice_service,
        recorder=recorder,
        player=player,
        tts=tts,
        stt=stt,
    )

    controller.start_listening()
    assert controller.state == TurnState.LISTENING
    gen_before = controller.generation

    # Trigger hard barge-in
    controller.barge_in()

    tts.stop.assert_called()
    player.stop.assert_called()
    recorder.cancel_recording.assert_called_once()
    assert controller.state == TurnState.CANCELLED
    assert controller.generation == gen_before + 1
    controller.close()


def test_voice_controller_empty_speech(voice_service, tmp_path: Path):
    mock_wav = tmp_path / "empty.wav"
    mock_wav.write_bytes(b"RIFF" + b"\x00" * 100)

    recorder = MagicMock(spec=LinuxAudioRecorder)
    recorder.stop_recording.return_value = mock_wav

    player = MagicMock(spec=LinuxAudioPlayer)
    tts = MagicMock(spec=NativeTTS)
    stt = MagicMock(spec=GroqWhisperSTT)
    stt.transcribe_file.return_value = "   "  # whitespace / silence

    controller = VoiceController(
        service=voice_service,
        recorder=recorder,
        player=player,
        tts=tts,
        stt=stt,
    )

    controller.start_listening()
    res = controller.stop_listening_and_process(stream_stdout=False, speak_output=True)
    assert res == ""
    assert controller.state == TurnState.CREATED
    tts.speak.assert_not_called()
    controller.close()


def test_streaming_tts_worker_lifecycle():
    tts = MagicMock(spec=NativeTTS)
    worker = StreamingTTSWorker(tts=tts, queue_size=4)
    worker.set_generation(1)

    assert worker.feed(1, "First sentence.") is True
    assert worker.feed(1, "Second sentence.") is True
    assert worker.feed(2, "Stale sentence from generation 2.") is False

    worker.flush_and_wait(1, timeout=2.0)
    assert tts.speak.call_count >= 2
    worker.close()


def test_streaming_tts_worker_cancel():
    tts = MagicMock(spec=NativeTTS)
    worker = StreamingTTSWorker(tts=tts, queue_size=4)
    worker.set_generation(1)

    worker.feed(1, "Sentence to cancel.")
    worker.cancel(1)
    tts.stop.assert_called()
    worker.close()


def test_linux_audio_recorder_detection():
    recorder = LinuxAudioRecorder()
    assert recorder._backend in ("pw-record", "arecord", "sox", None)
    assert recorder.is_recording is False


def test_linux_audio_player_detection():
    player = LinuxAudioPlayer()
    assert player._backend in ("pw-play", "aplay", "paplay", None)
    assert player.is_playing is False


def test_native_tts_detection():
    tts = NativeTTS()
    assert tts._backend in ("spd-say", "espeak-ng", "espeak", None)
    assert tts.is_speaking is False
