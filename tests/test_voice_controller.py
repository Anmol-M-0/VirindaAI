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
    tts.speak.assert_called()


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
