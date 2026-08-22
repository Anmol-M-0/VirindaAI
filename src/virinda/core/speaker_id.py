from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SpeakerProfile:
    speaker_id: str
    name: str
    enrolled_at: float = field(default_factory=time.time)
    embedding: list[float] = field(default_factory=list)


@dataclass(slots=True)
class SpeakerHint:
    speaker_id: str
    name: str
    confidence: float
    is_match: bool
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker_id": self.speaker_id,
            "name": self.name,
            "confidence": round(self.confidence, 4),
            "is_match": self.is_match,
            "timestamp": self.timestamp,
        }


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


class SpeakerVerificationEngine:
    """Speaker verification engine providing identity confidence hints to AssistantService."""

    def __init__(self, match_threshold: float = 0.75) -> None:
        self.match_threshold = match_threshold
        self._profiles: dict[str, SpeakerProfile] = {}

    def enroll_speaker(self, speaker_id: str, name: str, embedding: list[float]) -> SpeakerProfile:
        if not speaker_id.strip() or not name.strip():
            raise ValueError("speaker_id and name are required")
        if not embedding:
            raise ValueError("embedding vector cannot be empty")
        profile = SpeakerProfile(speaker_id=speaker_id, name=name, embedding=embedding)
        self._profiles[speaker_id] = profile
        return profile

    def verify(self, sample_embedding: list[float]) -> SpeakerHint:
        if not sample_embedding or not self._profiles:
            return SpeakerHint(
                speaker_id="unknown", name="Unknown Speaker", confidence=0.0, is_match=False
            )

        best_id = "unknown"
        best_name = "Unknown Speaker"
        best_score = 0.0

        for p in self._profiles.values():
            sim = _cosine_similarity(sample_embedding, p.embedding)
            if sim > best_score:
                best_score = sim
                best_id = p.speaker_id
                best_name = p.name

        is_match = best_score >= self.match_threshold
        return SpeakerHint(
            speaker_id=best_id if is_match else "unknown",
            name=best_name if is_match else "Unknown Speaker",
            confidence=best_score,
            is_match=is_match,
        )
