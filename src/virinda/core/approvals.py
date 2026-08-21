from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(slots=True)
class ApprovalRequest:
    token: str
    action_name: str
    action_hash: str
    risk_class: str
    description: str
    session_id: str
    created_at: float
    expires_at: float
    consumed: bool = False
    approved: bool = False

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class ApprovalManager:
    """Thread-safe, backend-authoritative single-use ephemeral approval manager."""

    def __init__(self, default_ttl_seconds: float = 30.0) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self._requests: dict[str, ApprovalRequest] = {}
        self._lock = threading.Lock()

    def _hash_action(self, action_name: str, payload: dict[str, Any]) -> str:
        data = f"{action_name}:{json.dumps(payload, sort_keys=True)}"
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def create_request(
        self,
        action_name: str,
        payload: dict[str, Any],
        risk_class: str = "destructive",
        description: str = "",
        session_id: str = "default",
        ttl_seconds: Optional[float] = None,
    ) -> ApprovalRequest:
        now = time.time()
        ttl = ttl_seconds or self.default_ttl_seconds
        token = secrets.token_hex(16)
        action_hash = self._hash_action(action_name, payload)

        req = ApprovalRequest(
            token=token,
            action_name=action_name,
            action_hash=action_hash,
            risk_class=risk_class,
            description=description or f"Execute {action_name}",
            session_id=session_id,
            created_at=now,
            expires_at=now + ttl,
            consumed=False,
            approved=False,
        )

        with self._lock:
            # Purge expired requests if table grows
            if len(self._requests) > 64:
                self._purge_expired_locked()
            self._requests[token] = req

        return req

    def approve_and_consume(
        self,
        token: str,
        action_name: str,
        payload: dict[str, Any],
    ) -> bool:
        """Atomically validates, approves, and consumes the token for the exact matching action.

        Returns True ONLY on the first valid attempt. All subsequent or concurrent calls return False.
        """
        now = time.time()
        expected_hash = self._hash_action(action_name, payload)

        with self._lock:
            req = self._requests.get(token)
            if not req:
                return False

            if req.consumed or req.is_expired:
                return False

            if req.action_name != action_name or req.action_hash != expected_hash:
                return False

            # Mark as consumed atomically
            req.consumed = True
            req.approved = True
            return True

    def reject(self, token: str) -> bool:
        with self._lock:
            req = self._requests.get(token)
            if not req or req.consumed:
                return False
            req.consumed = True
            req.approved = False
            return True

    def get_request(self, token: str) -> Optional[ApprovalRequest]:
        with self._lock:
            req = self._requests.get(token)
            if req and not req.is_expired:
                return req
            return None

    def _purge_expired_locked(self) -> None:
        now = time.time()
        expired = [tok for tok, r in self._requests.items() if r.expires_at < now or r.consumed]
        for tok in expired:
            self._requests.pop(tok, None)
