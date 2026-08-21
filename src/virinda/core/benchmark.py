from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from virinda.core.trace import VoiceTurnResult


@dataclass(frozen=True, slots=True)
class MetricStats:
    count: int
    min_ms: float
    max_ms: float
    avg_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "count": self.count,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "avg_ms": self.avg_ms,
            "p50_ms": self.p50_ms,
            "p90_ms": self.p90_ms,
            "p95_ms": self.p95_ms,
        }


def calculate_percentiles(values: Sequence[float]) -> MetricStats | None:
    valid = sorted(v for v in values if v is not None and not math.isnan(v))
    if not valid:
        return None
    n = len(valid)

    def _percentile(p: float) -> float:
        if n == 1:
            return round(valid[0], 2)
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return round(valid[int(k)], 2)
        d0 = valid[f] * (c - k)
        d1 = valid[c] * (k - f)
        return round(d0 + d1, 2)

    return MetricStats(
        count=n,
        min_ms=round(valid[0], 2),
        max_ms=round(valid[-1], 2),
        avg_ms=round(sum(valid) / n, 2),
        p50_ms=_percentile(0.50),
        p90_ms=_percentile(0.90),
        p95_ms=_percentile(0.95),
    )


@dataclass(frozen=True, slots=True)
class BenchmarkGateResult:
    name: str
    target_p50_ms: float
    actual_p50_ms: float | None
    target_p95_ms: float
    actual_p95_ms: float | None
    passed: bool


@dataclass(slots=True)
class VoiceBenchmarkReport:
    total_turns: int
    completed_turns: int
    interrupted_turns: int
    failed_turns: int

    stt_metrics: MetricStats | None = None
    llm_first_token_metrics: MetricStats | None = None
    tts_first_audio_metrics: MetricStats | None = None
    wake_to_first_audio_metrics: MetricStats | None = None
    barge_in_stop_metrics: MetricStats | None = None
    total_duration_metrics: MetricStats | None = None

    gates: list[BenchmarkGateResult] = field(default_factory=list)
    overall_passed: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": {
                "total_turns": self.total_turns,
                "completed_turns": self.completed_turns,
                "interrupted_turns": self.interrupted_turns,
                "failed_turns": self.failed_turns,
                "overall_passed": self.overall_passed,
            },
            "metrics": {
                "stt": self.stt_metrics.to_dict() if self.stt_metrics else None,
                "llm_first_token": (
                    self.llm_first_token_metrics.to_dict() if self.llm_first_token_metrics else None
                ),
                "tts_first_audio": (
                    self.tts_first_audio_metrics.to_dict() if self.tts_first_audio_metrics else None
                ),
                "wake_to_first_audio": (
                    self.wake_to_first_audio_metrics.to_dict()
                    if self.wake_to_first_audio_metrics
                    else None
                ),
                "barge_in_stop": (
                    self.barge_in_stop_metrics.to_dict() if self.barge_in_stop_metrics else None
                ),
                "total_duration": (
                    self.total_duration_metrics.to_dict() if self.total_duration_metrics else None
                ),
            },
            "gates": [
                {
                    "name": g.name,
                    "target_p50_ms": g.target_p50_ms,
                    "actual_p50_ms": g.actual_p50_ms,
                    "target_p95_ms": g.target_p95_ms,
                    "actual_p95_ms": g.actual_p95_ms,
                    "passed": g.passed,
                }
                for g in self.gates
            ],
        }


def evaluate_benchmark(results: Sequence[VoiceTurnResult]) -> VoiceBenchmarkReport:
    total = len(results)
    completed = sum(1 for r in results if not r.interrupted and r.trace.error is None)
    interrupted = sum(1 for r in results if r.interrupted)
    failed = sum(1 for r in results if r.trace.error is not None)

    stt_vals = [r.metrics.stt_duration_ms for r in results if r.metrics.stt_duration_ms is not None]
    llm_vals = [
        r.metrics.stt_to_llm_first_token_ms
        for r in results
        if r.metrics.stt_to_llm_first_token_ms is not None
    ]
    tts_vals = [
        r.metrics.llm_first_token_to_tts_audio_ms
        for r in results
        if r.metrics.llm_first_token_to_tts_audio_ms is not None
    ]
    wake_to_audio_vals = [
        r.metrics.wake_to_first_audio_ms
        for r in results
        if r.metrics.wake_to_first_audio_ms is not None
    ]
    barge_in_vals = [
        r.metrics.barge_in_to_cancellation_complete_ms or r.metrics.barge_in_to_audio_stop_ms
        for r in results
        if r.interrupted
        and (
            r.metrics.barge_in_to_cancellation_complete_ms is not None
            or r.metrics.barge_in_to_audio_stop_ms is not None
        )
    ]
    total_dur_vals = [
        r.metrics.total_interaction_ms
        for r in results
        if r.metrics.total_interaction_ms is not None
    ]

    stt_stats = calculate_percentiles(stt_vals)
    llm_stats = calculate_percentiles(llm_vals)
    tts_stats = calculate_percentiles(tts_vals)
    wake_to_audio_stats = calculate_percentiles(wake_to_audio_vals)
    barge_in_stats = calculate_percentiles(barge_in_vals)
    total_dur_stats = calculate_percentiles(total_dur_vals)

    gates: list[BenchmarkGateResult] = []
    overall_passed = True

    # Gate 1: STT Latency (rc1: p50 <= 1500ms, p95 <= 3000ms)
    if stt_stats:
        pass_stt = stt_stats.p50_ms <= 1500.0 and stt_stats.p95_ms <= 3000.0
        gates.append(
            BenchmarkGateResult(
                name="STT Latency",
                target_p50_ms=1500.0,
                actual_p50_ms=stt_stats.p50_ms,
                target_p95_ms=3000.0,
                actual_p95_ms=stt_stats.p95_ms,
                passed=pass_stt,
            )
        )
        if not pass_stt:
            overall_passed = False

    # Gate 2: TTS First Audio (rc1: p50 <= 500ms, p95 <= 1000ms)
    if tts_stats:
        pass_tts = tts_stats.p50_ms <= 500.0 and tts_stats.p95_ms <= 1000.0
        gates.append(
            BenchmarkGateResult(
                name="TTS First Audio",
                target_p50_ms=500.0,
                actual_p50_ms=tts_stats.p50_ms,
                target_p95_ms=1000.0,
                actual_p95_ms=tts_stats.p95_ms,
                passed=pass_tts,
            )
        )
        if not pass_tts:
            overall_passed = False

    # Gate 3: Barge-in Stop (rc1: p50 <= 250ms, p95 <= 500ms)
    if barge_in_stats:
        pass_barge_in = barge_in_stats.p50_ms <= 250.0 and barge_in_stats.p95_ms <= 500.0
        gates.append(
            BenchmarkGateResult(
                name="Barge-in Stop Latency",
                target_p50_ms=250.0,
                actual_p50_ms=barge_in_stats.p50_ms,
                target_p95_ms=500.0,
                actual_p95_ms=barge_in_stats.p95_ms,
                passed=pass_barge_in,
            )
        )
        if not pass_barge_in:
            overall_passed = False

    if failed > 0:
        overall_passed = False

    return VoiceBenchmarkReport(
        total_turns=total,
        completed_turns=completed,
        interrupted_turns=interrupted,
        failed_turns=failed,
        stt_metrics=stt_stats,
        llm_first_token_metrics=llm_stats,
        tts_first_audio_metrics=tts_stats,
        wake_to_first_audio_metrics=wake_to_audio_stats,
        barge_in_stop_metrics=barge_in_stats,
        total_duration_metrics=total_dur_stats,
        gates=gates,
        overall_passed=overall_passed,
    )
