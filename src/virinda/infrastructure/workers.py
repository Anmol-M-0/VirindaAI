from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from virinda.application.service import AssistantService
from virinda.infrastructure.audio.speech import GroqWhisperSTT
from virinda.infrastructure.jobs import JobEnvelope

logger = logging.getLogger(__name__)


class ReviewJobHandler:
    """Async background worker for automated AI code reviews."""

    def __init__(self, service: AssistantService) -> None:
        self.service = service

    def handle(self, job: JobEnvelope) -> dict[str, Any]:
        payload = job.payload
        file_path = payload.get("file_path")
        code_diff = payload.get("diff")
        output_path = payload.get("output_path")

        content_to_review = ""
        if file_path:
            p = Path(file_path).expanduser().resolve()
            if p.exists():
                content_to_review = f"### File: {p.name}\n```\n{p.read_text(encoding='utf-8', errors='replace')[:12000]}\n```"
        elif code_diff:
            content_to_review = f"### Diff:\n```diff\n{code_diff[:12000]}\n```"
        else:
            content_to_review = payload.get("prompt", "General code review.")

        prompt = f"Please provide a thorough code and architecture review for the following:\n\n{content_to_review}"
        response = self.service.ask(prompt)

        if output_path and response:
            out = Path(output_path).expanduser().resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(response, encoding="utf-8")

        return {
            "status": "completed",
            "job_id": job.id,
            "review_length": len(response),
            "output_path": output_path,
        }


class IndexJobHandler:
    """Async background worker for indexing documents and knowledge items into memory notes."""

    def __init__(self, service: AssistantService) -> None:
        self.service = service

    def handle(self, job: JobEnvelope) -> dict[str, Any]:
        payload = job.payload
        text = payload.get("text", "")
        file_path = payload.get("file_path")
        indexed_count = 0

        if file_path:
            p = Path(file_path).expanduser().resolve()
            if p.exists():
                text = p.read_text(encoding="utf-8", errors="replace")

        if text:
            # Chunk by paragraphs
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            for para in paragraphs[:20]:  # bound per job
                try:
                    self.service.memory_add_note(para, source="document_indexer")
                    indexed_count += 1
                except Exception as exc:
                    logger.debug("Failed to index note: %s", exc)

        return {
            "status": "completed",
            "job_id": job.id,
            "indexed_count": indexed_count,
        }


class AudioTranscriptionJobHandler:
    """Async background worker for batch audio file transcriptions."""

    def __init__(self, service: AssistantService, stt: Optional[GroqWhisperSTT] = None) -> None:
        self.service = service
        self.stt = stt or GroqWhisperSTT()

    def handle(self, job: JobEnvelope) -> dict[str, Any]:
        payload = job.payload
        audio_path = payload.get("audio_path")
        output_path = payload.get("output_path")

        if not audio_path:
            raise ValueError("audio_path is required for transcription job")

        p = Path(audio_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Audio file does not exist: {p}")

        transcript = self.stt.transcribe_file(p)

        if output_path and transcript:
            out = Path(output_path).expanduser().resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(transcript, encoding="utf-8")

        return {
            "status": "completed",
            "job_id": job.id,
            "transcript": transcript,
            "output_path": output_path,
        }
