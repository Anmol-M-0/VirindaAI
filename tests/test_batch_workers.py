from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from virinda.application.runtime import build_service
from virinda.config.settings import Settings
from virinda.infrastructure.audio.speech import GroqWhisperSTT
from virinda.infrastructure.desktop.screen import ScreenGroundingProbe
from virinda.infrastructure.jobs import JobEnvelope
from virinda.infrastructure.workers import (
    AudioTranscriptionJobHandler,
    IndexJobHandler,
    ReviewJobHandler,
)


@pytest.fixture
def service(tmp_path: Path):
    settings = Settings.from_env().with_data_dir(tmp_path)
    return build_service(settings)


def test_review_job_handler(service, tmp_path: Path):
    out_file = tmp_path / "review.md"
    handler = ReviewJobHandler(service)

    job = JobEnvelope(
        subject="virinda.jobs.review.execute",
        payload={"prompt": "def add(a, b): return a + b", "output_path": str(out_file)},
    )

    res = handler.handle(job)
    assert res["status"] == "completed"
    assert res["job_id"] == job.id
    assert out_file.exists()


def test_index_job_handler(service, tmp_path: Path):
    doc_file = tmp_path / "doc.txt"
    doc_file.write_text("First paragraph.\n\nSecond paragraph.\n\nThird paragraph.")

    handler = IndexJobHandler(service)
    job = JobEnvelope(
        subject="virinda.jobs.index.execute",
        payload={"file_path": str(doc_file)},
    )

    res = handler.handle(job)
    assert res["status"] == "completed"
    assert res["indexed_count"] == 3


def test_audio_transcription_job_handler(service, tmp_path: Path):
    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"RIFF" + b"\x00" * 100)
    out_file = tmp_path / "transcript.txt"

    mock_stt = MagicMock(spec=GroqWhisperSTT)
    mock_stt.transcribe_file.return_value = "Transcribed speech text."

    handler = AudioTranscriptionJobHandler(service, stt=mock_stt)
    job = JobEnvelope(
        subject="virinda.jobs.audio.transcribe",
        payload={"audio_path": str(audio_file), "output_path": str(out_file)},
    )

    res = handler.handle(job)
    assert res["status"] == "completed"
    assert res["transcript"] == "Transcribed speech text."
    assert out_file.read_text() == "Transcribed speech text."


def test_screen_grounding_probe_detection():
    probe = ScreenGroundingProbe()
    assert probe._backend in ("grim", "scrot", "import", None)
