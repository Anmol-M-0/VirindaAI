import time
from uuid import UUID

from virinda.core.trace import LatencyMetrics, VoiceInteractionState, VoiceInteractionTrace


def test_trace_monotonic_timestamps_and_state_transitions():
    trace = VoiceInteractionTrace(session_id="test-session")
    assert isinstance(trace.interaction_id, UUID)
    assert trace.state == VoiceInteractionState.STARTED

    trace.mark_wake()
    assert trace.state == VoiceInteractionState.WAKE_DETECTED
    assert trace.wake_at_mono_ns is not None

    trace.mark_stt_start()
    assert trace.state == VoiceInteractionState.STT_ACTIVE
    assert trace.stt_start_at_mono_ns is not None

    time.sleep(0.01)
    trace.mark_stt_end("hello virinda")
    assert trace.transcript == "hello virinda"
    assert trace.stt_end_at_mono_ns is not None

    trace.mark_llm_start()
    assert trace.state == VoiceInteractionState.GENERATING

    time.sleep(0.01)
    trace.mark_llm_first_token()
    assert trace.llm_first_token_at_mono_ns is not None

    trace.mark_tts_first_sentence()
    time.sleep(0.01)
    trace.mark_tts_first_audio()
    assert trace.state == VoiceInteractionState.SPEAKING
    assert trace.tts_first_audio_at_mono_ns is not None

    trace.mark_completed()
    assert trace.state == VoiceInteractionState.COMPLETED
    assert trace.ended_at_mono_ns is not None

    metrics = trace.compute_metrics()
    assert isinstance(metrics, LatencyMetrics)
    assert metrics.stt_duration_ms is not None and metrics.stt_duration_ms > 0
    assert metrics.stt_to_llm_first_token_ms is not None and metrics.stt_to_llm_first_token_ms > 0
    assert (
        metrics.llm_first_token_to_tts_audio_ms is not None
        and metrics.llm_first_token_to_tts_audio_ms > 0
    )
    assert metrics.wake_to_first_audio_ms is not None and metrics.wake_to_first_audio_ms > 0
    assert metrics.total_interaction_ms is not None and metrics.total_interaction_ms > 0


def test_trace_barge_in_metrics():
    trace = VoiceInteractionTrace(session_id="test-session")
    trace.mark_wake()
    trace.mark_tts_first_audio()

    time.sleep(0.005)
    trace.mark_barge_in()
    assert trace.state == VoiceInteractionState.INTERRUPTED

    time.sleep(0.005)
    trace.mark_audio_stop()

    time.sleep(0.005)
    trace.mark_cancellation_complete()

    metrics = trace.compute_metrics()
    assert metrics.barge_in_to_audio_stop_ms is not None and metrics.barge_in_to_audio_stop_ms > 0
    assert (
        metrics.barge_in_to_cancellation_complete_ms is not None
        and metrics.barge_in_to_cancellation_complete_ms > 0
    )


def test_trace_idempotent_first_markers():
    trace = VoiceInteractionTrace()
    trace.mark_llm_first_token()
    t1 = trace.llm_first_token_at_mono_ns
    time.sleep(0.002)
    trace.mark_llm_first_token()
    assert trace.llm_first_token_at_mono_ns == t1
