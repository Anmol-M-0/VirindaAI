from __future__ import annotations

import logging
from typing import Any, Optional

from virinda.core.approvals import ApprovalManager

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


class PHALController:
    """Hardware peripheral controller for OpenVoiceOS PHAL (Platform Hardware Abstraction Layer)."""

    def __init__(
        self,
        bus: Any,
        approval_manager: Optional[ApprovalManager] = None,
        source: str = "skill-virinda-ai.openvoiceos",
    ) -> None:
        self.bus = bus
        self.approval_manager = approval_manager or ApprovalManager()
        self.source = source

    def set_brightness(self, level: int) -> bool:
        """Sets display brightness (0-100%)."""
        level = max(0, min(100, level))
        msg = Message(
            "phal.brightness.set", data={"brightness": level}, context={"source": self.source}
        )
        return self._emit_safe(msg)

    def set_volume(self, level: int) -> bool:
        """Sets system audio volume (0-100%)."""
        level = max(0, min(100, level))
        msg = Message("phal.volume.set", data={"volume": level}, context={"source": self.source})
        return self._emit_safe(msg)

    def request_power_action(
        self,
        action: str,  # "shutdown" | "reboot" | "suspend"
        approval_token: Optional[str] = None,
    ) -> bool:
        """Executes privileged power action; requires single-use approval token."""
        if action not in ("shutdown", "reboot", "suspend"):
            raise ValueError(f"Unsupported power action: {action}")

        # Privileged action validation
        if not approval_token:
            logger.warning("Power action %s rejected: missing approval token.", action)
            return False

        valid = self.approval_manager.approve_and_consume(
            token=approval_token,
            action_name="power_action",
            payload={"action": action},
        )
        if not valid:
            logger.warning("Power action %s rejected: invalid or expired approval token.", action)
            return False

        topic = f"phal.power.{action}"
        msg = Message(topic, data={"action": action}, context={"source": self.source})
        return self._emit_safe(msg)

    def _emit_safe(self, msg: Message) -> bool:
        if not self.bus:
            logger.debug("PHAL bus not connected; skipping message: %s", msg.msg_type)
            return False
        try:
            self.bus.emit(msg)
            return True
        except Exception as exc:
            logger.debug("Failed to emit PHAL message %s: %s", msg.msg_type, exc)
            return False
