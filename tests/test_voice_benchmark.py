import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from marina.features import VoiceBenchmark, VoiceEventSample, latency_sample_from_events
from marina.infrastructure.persistence.sqlite import SQLiteConversationStore


def test_latency_sample_derives_available_stages_only():
    events = [
        VoiceEventSample("turn-1", "record.started", 10.0),
        VoiceEventSample("turn-1", "record.ended", 11.0),
        VoiceEventSample("turn-1", "stt.completed", 11.8),
        VoiceEventSample("turn-1", "audio.output.started", 13.0),
        VoiceEventSample("turn-1", "audio.output.ended", 14.0),
    ]
    sample = latency_sample_from_events(events)
    assert sample.wake_ms is None
    assert sample.end_of_speech_ms == 1000.0
    assert sample.stt_ms == pytest.approx(800.0)
    assert sample.llm_first_token_ms is None
    assert sample.tts_first_audio_ms is None
    assert sample.total_ms == 4000.0


def test_voice_benchmark_summary_reports_percentiles(tmp_path: Path):
    store = SQLiteConversationStore(tmp_path / "bench.sqlite3")
    benchmark = VoiceBenchmark(store.connection, store.lock)
    try:
        benchmark.record_events([
            VoiceEventSample("1", "record.started", 10.0),
            VoiceEventSample("1", "record.ended", 11.0),
            VoiceEventSample("1", "stt.completed", 11.5),
            VoiceEventSample("1", "audio.output.started", 12.0),
            VoiceEventSample("1", "audio.output.ended", 13.0),
        ])
        benchmark.record_events([
            VoiceEventSample("2", "record.started", 20.0),
            VoiceEventSample("2", "record.ended", 22.0),
            VoiceEventSample("2", "stt.completed", 23.0),
            VoiceEventSample("2", "audio.output.started", 25.0),
            VoiceEventSample("2", "audio.output.ended", 27.0),
        ])
        summary = benchmark.summary()
        assert summary["count"] == 2
        assert summary["total_ms"]["p50"] == 5000.0
        assert summary["stt_ms"]["p95"] > 500.0
    finally:
        store.close()


def test_voice_event_tools_have_help():
    root = Path(__file__).resolve().parents[1]
    for name in ("voice-event-capture.py", "voice-benchmark.py"):
        result = subprocess.run([sys.executable, str(root / "scripts" / name), "--help"], capture_output=True, text=True)
        assert result.returncode == 0
        assert "usage" in result.stdout.lower()


def test_voice_benchmark_can_fail_targets_when_insufficient_turns(tmp_path: Path):
    events = [
        {"turn_id": "1", "event": "record.started", "timestamp": 1.0},
        {"turn_id": "1", "event": "record.ended", "timestamp": 2.0},
        {"turn_id": "1", "event": "stt.completed", "timestamp": 3.5},
        {"turn_id": "1", "event": "audio.output.started", "timestamp": 4.0},
        {"turn_id": "1", "event": "audio.output.ended", "timestamp": 5.0},
    ]
    path = tmp_path / "voice.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in events) + "\n", encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "voice-benchmark.py"), str(path), "--fail-on-targets", "--min-turns", "2"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Acceptance: FAIL" in result.stdout


def test_voice_benchmark_can_emit_markdown_report(tmp_path: Path):
    path = tmp_path / "voice.jsonl"
    rows = []
    for i in range(30):
        start = float(i * 10)
        rows.extend([
            {"turn_id": str(i), "event": "wake.detected", "timestamp": start - 0.05},
            {"turn_id": str(i), "event": "record.started", "timestamp": start},
            {"turn_id": str(i), "event": "record.ended", "timestamp": start + 0.2},
            {"turn_id": str(i), "event": "stt.completed", "timestamp": start + 0.5},
            {"turn_id": str(i), "event": "llm.first_token", "timestamp": start + 1.0},
            {"turn_id": str(i), "event": "audio.output.started", "timestamp": start + 1.4},
            {"turn_id": str(i), "event": "audio.output.ended", "timestamp": start + 2.0},
        ])
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "voice-benchmark.py"), str(path), "--markdown", "--fail-on-targets"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "# Marina Voice Acceptance Report" in result.stdout
    assert "| total_ms |" in result.stdout


def test_voice_preflight_help() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "scripts" / "voice-preflight.py"), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "preflight" in result.stdout.lower()


def test_voice_event_capture_keeps_output_completion_on_interrupted_turn() -> None:
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "voice-event-capture.py"))
    correlate_event = module["correlate_event"]

    old_turn, current, output = correlate_event(
        "record.started", current_turn=None, output_turn=None, new_turn_id="old"
    )
    assert (old_turn, current, output) == ("old", "old", None)

    event_turn, current, output = correlate_event(
        "audio.output.started", current_turn=current, output_turn=output
    )
    assert event_turn == "old"
    assert output == "old"

    new_turn, current, output = correlate_event(
        "record.started", current_turn=current, output_turn=output, new_turn_id="new"
    )
    assert new_turn == "new"
    assert current == "new"
    assert output == "old"

    event_turn, current, output = correlate_event(
        "audio.output.ended", current_turn=current, output_turn=output
    )
    assert event_turn == "old"
    assert current == "new"
    assert output is None


def test_voice_event_capture_preserves_wake_turn_across_barge_in_record() -> None:
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "voice-event-capture.py"))
    correlate_event = module["correlate_event"]

    _, current, output = correlate_event(
        "record.started", current_turn=None, output_turn=None, new_turn_id="old"
    )
    _, current, output = correlate_event(
        "audio.output.started", current_turn=current, output_turn=output
    )
    event_turn, current, output = correlate_event(
        "wake.detected", current_turn=current, output_turn=output, new_turn_id="wake-turn"
    )
    assert (event_turn, current, output) == ("wake-turn", "wake-turn", "old")

    event_turn, current, output = correlate_event(
        "record.started", current_turn=current, output_turn=output, new_turn_id="wrong-new-turn"
    )
    assert (event_turn, current, output) == ("wake-turn", "wake-turn", "old")


def test_voice_event_capture_ignores_duplicate_wake_for_active_turn() -> None:
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "voice-event-capture.py"))
    correlate_event = module["correlate_event"]

    _, current, output = correlate_event(
        "wake.detected", current_turn=None, output_turn=None, new_turn_id="turn-1"
    )
    event_turn, current, output = correlate_event(
        "wake.detected", current_turn=current, output_turn=output, new_turn_id="turn-2"
    )
    assert (event_turn, current, output) == ("turn-1", "turn-1", None)


def test_voice_event_capture_correlates_wake_before_record_started() -> None:
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "voice-event-capture.py"))
    correlate_event = module["correlate_event"]

    event_turn, current, output = correlate_event(
        "wake.detected", current_turn=None, output_turn=None, new_turn_id="turn-1"
    )
    assert (event_turn, current, output) == ("turn-1", "turn-1", None)

    event_turn, current, output = correlate_event(
        "record.started", current_turn=current, output_turn=output, new_turn_id="ignored"
    )
    assert (event_turn, current, output) == ("turn-1", "turn-1", None)


def test_voice_benchmark_measures_wake_to_record_start(tmp_path: Path) -> None:
    path = tmp_path / "voice.jsonl"
    rows = []
    for i in range(30):
        start = float(i * 10)
        rows.extend([
            {"turn_id": str(i), "event": "wake.detected", "timestamp": start},
            {"turn_id": str(i), "event": "record.started", "timestamp": start + 0.05},
            {"turn_id": str(i), "event": "record.ended", "timestamp": start + 0.3},
            {"turn_id": str(i), "event": "stt.completed", "timestamp": start + 0.6},
            {"turn_id": str(i), "event": "llm.first_token", "timestamp": start + 1.0},
            {"turn_id": str(i), "event": "audio.output.started", "timestamp": start + 1.4},
            {"turn_id": str(i), "event": "audio.output.ended", "timestamp": start + 2.0},
        ])
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "voice-benchmark.py"), str(path), "--json", "--fail-on-targets"],
        capture_output=True, text=True, check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["metrics"]["wake_ms"]["count"] == 30
    assert payload["metrics"]["wake_ms"]["p95"] == pytest.approx(50.0)
    assert payload["pass"] is True
