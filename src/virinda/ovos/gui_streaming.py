from __future__ import annotations

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from ovos_bus_client.message import Message
except ImportError:

    class Message:  # type: ignore[no-redef]
        def __init__(
            self,
            msg_type: str,
            data: Optional[dict[str, Any]] = None,
            context: Optional[dict[str, Any]] = None,
        ) -> None:
            self.msg_type = msg_type
            self.data = data or {}
            self.context = context or {}


class StreamPublisher:
    """Publishes sequenced token deltas and tool execution progress to the OVOS GUI bus."""

    def __init__(self, bus: Any, source: str = "skill-virinda-ai.openvoiceos") -> None:
        self.bus = bus
        self.source = source
        self._sequence_counter = 0
        self._lock = threading.RLock()

    def publish_delta(self, delta: str, session_id: str = "default") -> None:
        if not delta or not self.bus:
            return
        with self._lock:
            self._sequence_counter += 1
            seq = self._sequence_counter

        msg = Message(
            "virinda.streaming.delta",
            data={"seq": seq, "delta": delta, "session_id": session_id},
            context={"source": self.source, "session": {"session_id": session_id}},
        )
        try:
            self.bus.emit(msg)
        except Exception as exc:
            logger.debug("Failed to emit streaming delta to bus: %s", exc)

    def publish_tool_status(
        self,
        tool_name: str,
        status: str,
        details: Optional[dict[str, Any]] = None,
        session_id: str = "default",
    ) -> None:
        if not self.bus:
            return
        payload = {
            "tool": tool_name,
            "status": status,
            "details": details or {},
            "session_id": session_id,
        }
        msg = Message(
            "virinda.tool.status",
            data=payload,
            context={"source": self.source, "session": {"session_id": session_id}},
        )
        try:
            self.bus.emit(msg)
        except Exception as exc:
            logger.debug("Failed to emit tool status to bus: %s", exc)

    def publish_approval_request(
        self,
        token: str,
        action_name: str,
        risk_class: str,
        description: str,
        expires_at: float,
        session_id: str = "default",
    ) -> None:
        if not self.bus:
            return
        payload = {
            "token": token,
            "action_name": action_name,
            "risk_class": risk_class,
            "description": description,
            "expires_at": expires_at,
            "session_id": session_id,
        }
        msg = Message(
            "virinda.gui.approval_request",
            data=payload,
            context={"source": self.source, "session": {"session_id": session_id}},
        )
        try:
            self.bus.emit(msg)
        except Exception as exc:
            logger.debug("Failed to emit approval request to bus: %s", exc)
