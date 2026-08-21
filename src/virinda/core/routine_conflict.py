from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class RoutineConflict:
    routine_id: str
    routine_name: str
    due_at: float
    duration_seconds: float
    overlap_seconds: float
    reason: str


@dataclass(slots=True)
class RoutineConflictReport:
    has_conflict: bool
    candidate_due_at: float
    candidate_duration: float
    conflicts: list[RoutineConflict] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_conflict": self.has_conflict,
            "candidate_due_at": self.candidate_due_at,
            "candidate_duration": self.candidate_duration,
            "conflict_count": len(self.conflicts),
            "conflicts": [
                {
                    "routine_id": c.routine_id,
                    "routine_name": c.routine_name,
                    "due_at": c.due_at,
                    "duration_seconds": c.duration_seconds,
                    "overlap_seconds": round(c.overlap_seconds, 2),
                    "reason": c.reason,
                }
                for c in self.conflicts
            ],
        }


class RoutineConflictDetector:
    """Proactive schedule collision and overlap detection for user routines."""

    def __init__(self, default_duration_seconds: float = 60.0) -> None:
        self.default_duration_seconds = default_duration_seconds

    def check_conflicts(
        self,
        candidate_due_at: float,
        candidate_duration: Optional[float] = None,
        existing_routines: Optional[list[dict[str, Any]]] = None,
        exclude_routine_id: Optional[str] = None,
    ) -> RoutineConflictReport:
        dur = candidate_duration or self.default_duration_seconds
        c_start = candidate_due_at
        c_end = candidate_due_at + dur

        conflicts: list[RoutineConflict] = []
        routines = existing_routines or []

        for r in routines:
            r_id = r.get("id") or r.get("routine_id", "")
            if exclude_routine_id and r_id == exclude_routine_id:
                continue

            enabled = r.get("enabled", True)
            if not enabled:
                continue

            r_due = float(r.get("due_at", 0.0))
            if r_due <= 0:
                continue

            r_dur = float(r.get("duration_seconds", self.default_duration_seconds))
            r_start = r_due
            r_end = r_due + r_dur

            # Calculate interval overlap
            overlap_start = max(c_start, r_start)
            overlap_end = min(c_end, r_end)
            overlap = overlap_end - overlap_start

            if overlap > 0:
                conflicts.append(
                    RoutineConflict(
                        routine_id=r_id,
                        routine_name=r.get("name", "Unnamed Routine"),
                        due_at=r_due,
                        duration_seconds=r_dur,
                        overlap_seconds=overlap,
                        reason=f"Overlaps by {overlap:.1f}s with '{r.get('name', r_id)}'",
                    )
                )

        return RoutineConflictReport(
            has_conflict=len(conflicts) > 0,
            candidate_due_at=candidate_due_at,
            candidate_duration=dur,
            conflicts=conflicts,
        )
