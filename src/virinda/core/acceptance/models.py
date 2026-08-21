from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic_ns
from uuid import UUID

from virinda.core.trace import LatencyMetrics, VoiceInteractionTrace


class TurnState(StrEnum):
    CREATED = "created"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTING = "interrupting"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


# Valid state machine transitions
LEGAL_TRANSITIONS: dict[TurnState, set[TurnState]] = {
    TurnState.CREATED: {
        TurnState.LISTENING,
        TurnState.TRANSCRIBING,
        TurnState.THINKING,
        TurnState.CANCELLED,
        TurnState.FAILED,
    },
    TurnState.LISTENING: {
        TurnState.THINKING,
        TurnState.TRANSCRIBING,
        TurnState.CREATED,
        TurnState.INTERRUPTING,
        TurnState.CANCELLED,
        TurnState.FAILED,
    },
    TurnState.THINKING: {
        TurnState.TRANSCRIBING,
        TurnState.SPEAKING,
        TurnState.INTERRUPTING,
        TurnState.CANCELLED,
        TurnState.FAILED,
    },
    TurnState.TRANSCRIBING: {
        TurnState.THINKING,
        TurnState.SPEAKING,
        TurnState.LISTENING,
        TurnState.CREATED,
        TurnState.INTERRUPTING,
        TurnState.CANCELLED,
        TurnState.FAILED,
    },
    TurnState.SPEAKING: {
        TurnState.COMPLETED,
        TurnState.LISTENING,
        TurnState.CREATED,
        TurnState.TRANSCRIBING,
        TurnState.INTERRUPTING,
        TurnState.CANCELLED,
        TurnState.FAILED,
    },
    TurnState.INTERRUPTING: {
        TurnState.CANCELLED,
        TurnState.LISTENING,
        TurnState.CREATED,
        TurnState.FAILED,
    },
    TurnState.COMPLETED: {TurnState.LISTENING, TurnState.CREATED, TurnState.TRANSCRIBING},
    TurnState.CANCELLED: {TurnState.LISTENING, TurnState.CREATED, TurnState.TRANSCRIBING},
    TurnState.FAILED: {TurnState.LISTENING, TurnState.CREATED, TurnState.TRANSCRIBING},
}


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    timestamp_ns: int = field(default_factory=monotonic_ns)
    rss_bytes: int = 0
    vms_bytes: int = 0
    thread_count: int = 0
    fd_count: int = 0
    thread_names: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp_ns": self.timestamp_ns,
            "rss_bytes": self.rss_bytes,
            "vms_bytes": self.vms_bytes,
            "thread_count": self.thread_count,
            "fd_count": self.fd_count,
            "thread_names": list(self.thread_names),
        }


@dataclass(frozen=True, slots=True)
class AssertionResult:
    name: str
    passed: bool
    expected: object
    actual: object
    details: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "expected": str(self.expected),
            "actual": str(self.actual),
            "details": self.details,
        }


@dataclass(slots=True)
class TurnAcceptanceRecord:
    index: int
    utterance: str
    response: str
    correlation_id: UUID
    interrupted: bool
    latency: LatencyMetrics
    passed: bool = True
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "utterance": self.utterance,
            "response": self.response,
            "correlation_id": str(self.correlation_id),
            "interrupted": self.interrupted,
            "latency": self.latency.to_dict(),
            "passed": self.passed,
            "notes": self.notes,
        }


@dataclass(slots=True)
class AcceptanceResult:
    scenario: str
    started_at_ns: int = field(default_factory=monotonic_ns)
    finished_at_ns: int = 0
    passed: bool = True
    assertions: list[AssertionResult] = field(default_factory=list)
    traces: list[VoiceInteractionTrace] = field(default_factory=list)
    records: list[TurnAcceptanceRecord] = field(default_factory=list)
    resources_before: ResourceSnapshot | None = None
    resources_after: ResourceSnapshot | None = None
    failures: list[str] = field(default_factory=list)

    def add_assertion(
        self, name: str, passed: bool, expected: object, actual: object, details: str | None = None
    ) -> None:
        self.assertions.append(AssertionResult(name, passed, expected, actual, details))
        if not passed:
            self.passed = False
            self.failures.append(f"{name}: expected {expected}, got {actual} ({details or ''})")

    def finalize(self) -> None:
        if self.finished_at_ns == 0:
            self.finished_at_ns = monotonic_ns()

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario": self.scenario,
            "started_at_ns": self.started_at_ns,
            "finished_at_ns": self.finished_at_ns,
            "duration_ms": round((self.finished_at_ns - self.started_at_ns) / 1_000_000.0, 2)
            if self.finished_at_ns
            else 0.0,
            "passed": self.passed,
            "total_assertions": len(self.assertions),
            "failed_assertions": len(self.failures),
            "assertions": [a.to_dict() for a in self.assertions],
            "records": [r.to_dict() for r in self.records],
            "resources_before": self.resources_before.to_dict() if self.resources_before else None,
            "resources_after": self.resources_after.to_dict() if self.resources_after else None,
            "failures": self.failures,
        }
