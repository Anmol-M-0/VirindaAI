#!/usr/bin/env python3
"""Compute Virinda voice latency metrics and optionally enforce P0 acceptance targets."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

TARGETS_MS = {
    "wake_ms": 150.0,
    "end_of_speech_ms": 1000.0,
    "stt_ms": 1000.0,
    "llm_first_token_ms": 1500.0,
    "tts_first_audio_ms": 1000.0,
    "total_ms": 5000.0,
}


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * p
    lo = int(index)
    hi = min(lo + 1, len(values) - 1)
    frac = index - lo
    return values[lo] + (values[hi] - values[lo]) * frac


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSONL from voice-event-capture.py")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--markdown", action="store_true", help="print a Markdown acceptance report"
    )
    parser.add_argument(
        "--min-turns", type=int, default=30, help="minimum turns for an acceptance run"
    )
    parser.add_argument(
        "--fail-on-targets",
        action="store_true",
        help="exit non-zero when measured p95 targets fail",
    )
    parser.add_argument(
        "--allow-incomplete", action="store_true", help="allow missing latency stages"
    )
    args = parser.parse_args()
    try:
        from virinda.features import VoiceEventSample, latency_sample_from_events
    except ImportError:
        # Keep repository scripts runnable directly from a source checkout.
        # Installed environments still use the normal package import path.
        src = Path(__file__).resolve().parents[1] / "src"
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))
        try:
            from virinda.features import VoiceEventSample, latency_sample_from_events
        except ImportError:
            print("Virinda package is unavailable; install virinda-ai", file=sys.stderr)
            return 2

    turns: dict[str, list[VoiceEventSample]] = defaultdict(list)
    with args.input.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
                turn_id = row.get("turn_id")
                event = str(row["event"])
                timestamp = float(row["timestamp"])
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                raise SystemExit(f"invalid event JSON on line {line_number}: {exc}") from exc
            if turn_id:
                turns[str(turn_id)].append(VoiceEventSample(str(turn_id), event, timestamp))

    samples = [latency_sample_from_events(events) for events in turns.values() if events]
    metrics = (
        "wake_ms",
        "end_of_speech_ms",
        "stt_ms",
        "llm_first_token_ms",
        "tts_first_audio_ms",
        "total_ms",
    )
    result: dict[str, object] = {
        "turns": len(samples),
        "metrics": {},
        "targets_ms": TARGETS_MS.copy(),
    }
    failures: list[str] = []
    if len(samples) < args.min_turns:
        failures.append(f"only {len(samples)} turns captured; need at least {args.min_turns}")

    for metric in metrics:
        values = [
            float(getattr(sample, metric))
            for sample in samples
            if getattr(sample, metric) is not None
        ]
        stats = {
            "count": len(values),
            "p50": percentile(values, 0.50),
            "p95": percentile(values, 0.95),
        }
        result["metrics"][metric] = stats
        if args.fail_on_targets and metric in TARGETS_MS:
            target = TARGETS_MS[metric]
            if stats["count"] == 0 and not args.allow_incomplete:
                failures.append(f"{metric}: no measurements captured")
            elif stats["p95"] is not None and stats["p95"] > target:
                failures.append(f"{metric}: p95={stats['p95']:.1f}ms > target={target:.1f}ms")

    result["pass"] = not failures
    result["failures"] = failures

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif args.markdown:
        print("# Virinda Voice Acceptance Report\n")
        print(f"- Turns: **{result['turns']}**")
        print(f"- Result: **{'PASS' if not failures else 'FAIL'}**\n")
        print("| Metric | Count | P50 (ms) | P95 (ms) | Target (ms) |")
        print("|---|---:|---:|---:|---:|")
        for metric, stats in result["metrics"].items():
            target = TARGETS_MS.get(metric)
            p50 = "—" if stats["p50"] is None else f"{stats['p50']:.1f}"
            p95 = "—" if stats["p95"] is None else f"{stats['p95']:.1f}"
            target_text = "—" if target is None else f"{target:.1f}"
            print(f"| {metric} | {stats['count']} | {p50} | {p95} | {target_text} |")
        if failures:
            print("\n## Failures")
            for failure in failures:
                print(f"- {failure}")
    else:
        print(f"Turns: {result['turns']}")
        for metric, stats in result["metrics"].items():
            print(
                f"{metric:24} count={stats['count']:>3} p50={stats['p50']}ms p95={stats['p95']}ms"
            )
        if failures:
            print("Acceptance: FAIL")
            for failure in failures:
                print(f"  - {failure}")
        elif args.fail_on_targets:
            print("Acceptance: PASS")

    return 1 if failures and args.fail_on_targets else 0


if __name__ == "__main__":
    raise SystemExit(main())
