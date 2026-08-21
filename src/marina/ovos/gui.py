from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:
    from ovos_bus_client.message import Message
except ImportError:  # pragma: no cover
    Message = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class MarinaGUICommand:
    """A GUI command accepted over the local OVOS MessageBus."""

    command: str
    data: dict[str, Any]
    session_id: str = "default"


class OVOSGuiBridge:
    """Translate Marina UI state/actions to the OVOS GUI/message-bus boundary.

    Production desktop UI traffic must flow through OVOS `ovos-gui` and the
    MessageBus. The bridge deliberately does not know about HTTP, sockets, or a
    particular Qt/GTK implementation.
    """

    STATE_TOPIC = "gui.value.set"
    COMMAND_TOPIC = "marina.gui.command"
    RESPONSE_TOPIC = "marina.gui.response"

    def __init__(self, bus: Any, *, source: str = "skill-marin-ai.openvoiceos") -> None:
        self.bus = bus
        self.source = source

    def publish_value(self, key: str, value: Any, *, session_id: str = "default") -> None:
        self._emit(
            self.STATE_TOPIC,
            {"key": f"marina.{key}", "value": value},
            session_id=session_id,
        )

    def publish_state(self, state: dict[str, Any], *, session_id: str = "default") -> None:
        for key, value in state.items():
            self.publish_value(key, value, session_id=session_id)

    def publish_response(
        self,
        request_id: str,
        result: Any,
        *,
        session_id: str = "default",
        error: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {"request_id": request_id, "ok": error is None}
        if error is None:
            payload["result"] = result
        else:
            payload["error"] = error
        self._emit(self.RESPONSE_TOPIC, payload, session_id=session_id)

    def subscribe(self, handler: Callable[[MarinaGUICommand], None]) -> None:
        def on_message(message: Any) -> None:
            data = getattr(message, "data", {}) or {}
            context = getattr(message, "context", {}) or {}
            if not isinstance(data, dict):
                return
            command = str(data.get("command", "")).strip()
            if not command:
                return
            payload = data.get("data", {})
            if not isinstance(payload, dict):
                return
            session = context.get("session", {}) if isinstance(context, dict) else {}
            session_id = str(session.get("session_id", "default")) if isinstance(session, dict) else "default"
            handler(MarinaGUICommand(command, payload, session_id))

        self.bus.on(self.COMMAND_TOPIC, on_message)

    def _emit(self, topic: str, data: dict[str, Any], *, session_id: str) -> None:
        if Message is None:  # pragma: no cover
            raise RuntimeError("ovos-bus-client is required for the OVOS GUI bridge")
        self.bus.emit(
            Message(
                topic,
                data=data,
                context={
                    "source": self.source,
                    "session": {"session_id": session_id},
                },
            )
        )
