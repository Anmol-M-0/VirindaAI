from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ProactiveTriggerType(str, Enum):
    IDLE = "idle"
    NOTIFICATION = "notification"
    CALENDAR = "calendar"
    BRIEFING = "briefing"


@dataclass(slots=True)
class ProactiveCandidate:
    id: str
    trigger_type: ProactiveTriggerType
    priority: int  # 1 (low) to 10 (high)
    content: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0

    @property
    def is_expired(self) -> bool:
        return self.expires_at > 0 and time.time() > self.expires_at


class ProactiveEngine:
    """Non-blocking proactive desktop briefing and alert scheduler."""

    def __init__(
        self,
        idle_threshold_seconds: float = 300.0,
        cooldown_seconds: float = 600.0,
    ) -> None:
        self.idle_threshold_seconds = idle_threshold_seconds
        self.cooldown_seconds = cooldown_seconds
        self._last_proactive_delivered_at: float = 0.0
        self._candidates: list[ProactiveCandidate] = []
        self._lock = threading.RLock()

    def add_candidate(
        self,
        candidate_id: str,
        trigger_type: ProactiveTriggerType,
        priority: int,
        content: str,
        ttl_seconds: float = 3600.0,
    ) -> ProactiveCandidate:
        now = time.time()
        cand = ProactiveCandidate(
            id=candidate_id,
            trigger_type=trigger_type,
            priority=priority,
            content=content,
            created_at=now,
            expires_at=now + ttl_seconds,
        )
        with self._lock:
            # Purge expired
            self._candidates = [c for c in self._candidates if not c.is_expired]
            self._candidates.append(cand)
            # Sort by priority descending
            self._candidates.sort(key=lambda c: c.priority, reverse=True)
        return cand

    def evaluate_proactive_briefing(
        self,
        is_voice_busy: bool,
        last_user_activity_at: float,
        notification_count: int = 0,
    ) -> Optional[ProactiveCandidate]:
        """Evaluates whether a proactive briefing or candidate should be delivered."""
        now = time.time()

        # Invariant 1: Never interrupt active voice interaction
        if is_voice_busy:
            return None

        # Invariant 2: Respect global cooldown
        if (now - self._last_proactive_delivered_at) < self.cooldown_seconds:
            return None

        with self._lock:
            # Filter non-expired
            self._candidates = [c for c in self._candidates if not c.is_expired]

            # Priority 1: Check pending calendar/urgent candidates
            for cand in self._candidates:
                if cand.priority >= 8:
                    self._candidates.remove(cand)
                    self._last_proactive_delivered_at = now
                    return cand

            # Priority 2: Check idle threshold with notifications
            idle_duration = now - last_user_activity_at
            if idle_duration >= self.idle_threshold_seconds:
                if notification_count > 0:
                    cand = ProactiveCandidate(
                        id=f"idle_notif_{int(now)}",
                        trigger_type=ProactiveTriggerType.NOTIFICATION,
                        priority=5,
                        content=f"You have {notification_count} unread notifications.",
                        created_at=now,
                        expires_at=now + 300.0,
                    )
                    self._last_proactive_delivered_at = now
                    return cand

                # Check normal queue
                if self._candidates:
                    cand = self._candidates.pop(0)
                    self._last_proactive_delivered_at = now
                    return cand

        return None
