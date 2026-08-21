from __future__ import annotations

import time
from dataclasses import dataclass

from virinda.core.routine_conflict import RoutineConflictDetector
from virinda.infrastructure.persistence.memory_ranker import CognitiveMemoryRanker


@dataclass
class DummyFact:
    id: str
    key: str
    value: str
    confidence: float = 1.0
    pinned: bool = False
    updated_at: float = 0.0


@dataclass
class DummyNote:
    id: str
    text: str
    created_at: float = 0.0


def test_cognitive_memory_ranking():
    ranker = CognitiveMemoryRanker()
    now = time.time()

    facts = [
        DummyFact(
            id="1",
            key="favorite_editor",
            value="neovim",
            confidence=1.0,
            pinned=True,
            updated_at=now,
        ),
        DummyFact(
            id="2",
            key="favorite_language",
            value="python",
            confidence=1.0,
            pinned=False,
            updated_at=now - 86400 * 60,
        ),
        DummyFact(
            id="3",
            key="pet_name",
            value="Shadow the cat",
            confidence=0.6,
            pinned=False,
            updated_at=now,
        ),
    ]
    notes = [
        DummyNote(
            id="n1", text="Discussed setting up neovim plugins yesterday", created_at=now - 3600
        ),
    ]

    # Query matching neovim
    ranked = ranker.rank("Which editor do I use in neovim?", facts, notes, limit=3)
    assert len(ranked) >= 2
    # Pinned fact for neovim should be #1
    assert ranked[0].key == "favorite_editor"
    assert ranked[0].pinned is True

    context_str = ranker.build_prompt_context(ranked)
    assert "<retrieved_memory>" in context_str
    assert "[PINNED FACT] favorite_editor: neovim" in context_str
    assert "</retrieved_memory>" in context_str


def test_routine_conflict_detector_no_conflict():
    detector = RoutineConflictDetector(default_duration_seconds=60.0)
    existing = [
        {
            "id": "r1",
            "name": "Morning Sync",
            "due_at": 1000.0,
            "duration_seconds": 30.0,
            "enabled": True,
        },
        {
            "id": "r2",
            "name": "Lunch Check",
            "due_at": 2000.0,
            "duration_seconds": 60.0,
            "enabled": True,
        },
    ]

    report = detector.check_conflicts(
        candidate_due_at=1100.0, candidate_duration=60.0, existing_routines=existing
    )
    assert report.has_conflict is False
    assert len(report.conflicts) == 0


def test_routine_conflict_detector_with_conflict():
    detector = RoutineConflictDetector(default_duration_seconds=60.0)
    existing = [
        {
            "id": "r1",
            "name": "Morning Sync",
            "due_at": 1000.0,
            "duration_seconds": 60.0,
            "enabled": True,
        },
        {
            "id": "r2",
            "name": "Disabled Job",
            "due_at": 1020.0,
            "duration_seconds": 60.0,
            "enabled": False,
        },
    ]

    # Candidate starts at 1030 (during Morning Sync 1000-1060)
    report = detector.check_conflicts(
        candidate_due_at=1030.0, candidate_duration=60.0, existing_routines=existing
    )
    assert report.has_conflict is True
    assert len(report.conflicts) == 1
    assert report.conflicts[0].routine_id == "r1"
    assert report.conflicts[0].overlap_seconds == 30.0
