from __future__ import annotations

import time
from unittest.mock import MagicMock

from virinda.core.approvals import ApprovalManager
from virinda.core.proactive import ProactiveEngine, ProactiveTriggerType
from virinda.core.speaker_id import SpeakerVerificationEngine
from virinda.ovos.phal import PHALController


def test_proactive_suppressed_when_voice_busy():
    engine = ProactiveEngine(idle_threshold_seconds=10.0, cooldown_seconds=5.0)
    engine.add_candidate(
        "cand1", ProactiveTriggerType.CALENDAR, priority=9, content="Meeting starting now."
    )

    # Voice loop is busy -> Must return None
    result = engine.evaluate_proactive_briefing(
        is_voice_busy=True, last_user_activity_at=time.time()
    )
    assert result is None


def test_proactive_idle_and_notification_delivery():
    engine = ProactiveEngine(idle_threshold_seconds=10.0, cooldown_seconds=5.0)
    now = time.time()

    # User has been idle for 20s with 3 unread notifications
    result = engine.evaluate_proactive_briefing(
        is_voice_busy=False,
        last_user_activity_at=now - 20.0,
        notification_count=3,
    )
    assert result is not None
    assert result.trigger_type == ProactiveTriggerType.NOTIFICATION
    assert "3 unread notifications" in result.content


def test_phal_controller_brightness_and_volume():
    mock_bus = MagicMock()
    phal = PHALController(mock_bus)

    assert phal.set_brightness(75) is True
    assert phal.set_volume(50) is True
    assert mock_bus.emit.call_count == 2


def test_phal_controller_power_action_requires_approval():
    mock_bus = MagicMock()
    approval_mgr = ApprovalManager(default_ttl_seconds=10.0)
    phal = PHALController(mock_bus, approval_manager=approval_mgr)

    # 1. Without token -> Rejected
    assert phal.request_power_action("shutdown") is False

    # 2. With valid approval token -> Succeeded
    req = approval_mgr.create_request(
        "power_action", {"action": "shutdown"}, risk_class="destructive"
    )
    assert phal.request_power_action("shutdown", approval_token=req.token) is True

    # 3. Token replay attempt -> Rejected
    assert phal.request_power_action("shutdown", approval_token=req.token) is False


def test_speaker_verification_cosine_matching():
    engine = SpeakerVerificationEngine(match_threshold=0.8)

    alice_vec = [1.0, 0.0, 0.5, 0.0]
    bob_vec = [0.0, 1.0, 0.0, 0.8]

    engine.enroll_speaker("spk_alice", "Alice", alice_vec)
    engine.enroll_speaker("spk_bob", "Bob", bob_vec)

    # Test sample matching Alice
    sample_alice = [0.95, 0.05, 0.48, 0.0]
    hint_alice = engine.verify(sample_alice)
    assert hint_alice.is_match is True
    assert hint_alice.name == "Alice"
    assert hint_alice.confidence >= 0.9

    # Test unknown sample
    sample_unknown = [0.0, 0.0, 0.0, 1.0]
    hint_unknown = engine.verify(sample_unknown)
    assert hint_unknown.is_match is False
    assert hint_unknown.speaker_id == "unknown"
