from __future__ import annotations

from pathlib import Path

import pytest

from virinda.infrastructure.audio.speech import (
    GroqWhisperSTT,
    LocalWhisperSTT,
    NativeTTS,
    SpeechError,
    SpeechToText,
)


def test_speech_to_text_default_is_local(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("VIRINDA_STT_CLOUD_FALLBACK", raising=False)

    stt = SpeechToText()
    assert stt.cloud_fallback is False
    assert stt.active_engine_name in ("whisper.cpp (local)", "vosk (local)", "none (unconfigured)")


def test_speech_to_text_mock_mode(tmp_path: Path):
    dummy_wav = tmp_path / "test.wav"
    dummy_wav.write_bytes(b"RIFF" + b"\x00" * 4000)

    stt = SpeechToText(mock_mode=True)
    assert stt.active_engine_name == "mock"
    result = stt.transcribe_file(dummy_wav)
    assert len(result) > 0


def test_local_whisper_stt_discovery():
    whisper_stt = LocalWhisperSTT()
    # Scans for whisper-cli or main
    assert isinstance(whisper_stt.is_available, bool)


def test_native_tts_backend_discovery():
    tts = NativeTTS()
    assert tts.is_available is True or tts._backend is None
    if tts._backend:
        assert tts._backend in ("piper", "spd-say", "espeak-ng", "espeak", "mimic3")


def test_groq_stt_requires_valid_key(tmp_path: Path):
    groq = GroqWhisperSTT(api_key=None)
    assert groq.is_available is False

    dummy_wav = tmp_path / "empty.wav"
    dummy_wav.write_bytes(b"RIFF")
    with pytest.raises(SpeechError, match="Groq API key not configured"):
        groq.transcribe_file(dummy_wav)
