from virinda.core.benchmark import calculate_percentiles, evaluate_benchmark
from virinda.core.trace import (
    LatencyMetrics,
    VoiceInteractionTrace,
    VoiceTurnResult,
)


def test_percentile_calculation():
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    stats = calculate_percentiles(values)
    assert stats is not None
    assert stats.count == 10
    assert stats.min_ms == 10.0
    assert stats.max_ms == 100.0
    assert stats.avg_ms == 55.0
    assert stats.p50_ms == 55.0
    assert stats.p90_ms == 91.0


def test_evaluate_benchmark_gates_pass():
    results = []
    for i in range(10):
        trace = VoiceInteractionTrace()
        trace.mark_completed()
        metrics = LatencyMetrics(
            stt_duration_ms=100.0 + i * 5,
            stt_to_llm_first_token_ms=50.0,
            llm_first_token_to_tts_audio_ms=80.0,
            wake_to_first_audio_ms=230.0,
            total_interaction_ms=300.0,
        )
        results.append(
            VoiceTurnResult(
                trace=trace,
                metrics=metrics,
                transcript="test",
                response="response",
                interrupted=False,
            )
        )

    report = evaluate_benchmark(results)
    assert report.total_turns == 10
    assert report.completed_turns == 10
    assert report.overall_passed is True
    assert len(report.gates) >= 2
    assert all(g.passed for g in report.gates)


def test_evaluate_benchmark_gates_fail_on_slow_stt():
    results = []
    for _ in range(5):
        trace = VoiceInteractionTrace()
        trace.mark_completed()
        metrics = LatencyMetrics(
            stt_duration_ms=4500.0,  # Fails rc1 limit of 1500ms p50
            llm_first_token_to_tts_audio_ms=100.0,
        )
        results.append(
            VoiceTurnResult(
                trace=trace,
                metrics=metrics,
                transcript="test",
                response="response",
                interrupted=False,
            )
        )

    report = evaluate_benchmark(results)
    assert report.overall_passed is False
    stt_gate = next(g for g in report.gates if g.name == "STT Latency")
    assert stt_gate.passed is False
