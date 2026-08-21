from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from virinda.application.service import AssistantService

logger = logging.getLogger(__name__)

try:
    from ovos_bus_client.client import MessageBusClient
    from ovos_bus_client.message import Message
except ImportError as exc:
    MessageBusClient = None  # type: ignore[assignment,misc]

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

    _OVOS_BUS_IMPORT_ERROR = exc
else:
    _OVOS_BUS_IMPORT_ERROR = None


class OVOSBridgeError(RuntimeError):
    """Raised when the OVOS MessageBus bridge fails to connect or execute."""


class OVOSMessageBusBridge:
    """Production OpenVoiceOS MessageBus adapter connecting Virinda's AssistantService

    to the ambient audio lifecycle (ovos-dinkum-listener -> bus -> AssistantService -> ovos-audio).
    """

    def __init__(
        self,
        service: AssistantService,
        host: str = "127.0.0.1",
        port: int = 8181,
        route: str = "/core",
        bus_client: Optional[Any] = None,
    ) -> None:
        self.service = service
        self.host = host
        self.port = port
        self.route = route
        self._client = bus_client
        self._connected = False
        self._lock = threading.RLock()

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def connect(self) -> None:
        """Establish WebSocket connection to the OVOS MessageBus daemon."""
        if _OVOS_BUS_IMPORT_ERROR is not None and self._client is None:
            raise OVOSBridgeError(
                "OVOS MessageBus client library is not installed. Install `ovos-bus-client`."
            ) from _OVOS_BUS_IMPORT_ERROR

        if self._client is None:
            self._client = MessageBusClient(host=self.host, port=self.port, route=self.route)

        try:
            self._client.on("recognizer_loop:utterance", self._handle_utterance)
            self._client.on("mycroft.stop", self._handle_stop)
            self._client.run_in_thread()
            with self._lock:
                self._connected = True
            logger.info(
                "Connected to OVOS MessageBus at ws://%s:%s%s", self.host, self.port, self.route
            )
        except Exception as exc:
            with self._lock:
                self._connected = False
            raise OVOSBridgeError(
                f"Failed to connect to OVOS MessageBus at {self.host}:{self.port}: {exc}"
            ) from exc

    def _handle_utterance(self, message: Any) -> None:
        """Handle incoming speech transcript from ovos-dinkum-listener."""
        data = getattr(message, "data", {}) if message else {}
        utterances = data.get("utterances", [])
        if not utterances:
            return

        text = utterances[0].strip()
        if not text:
            return

        logger.info("Received OVOS speech utterance: '%s'", text)
        context = getattr(message, "context", {})

        # Process in background thread to avoid blocking MessageBus loop
        threading.Thread(
            target=self._process_turn_async,
            args=(text, context),
            daemon=True,
            name="Virinda-OVOS-Turn",
        ).start()

    def _process_turn_async(self, text: str, context: dict[str, Any]) -> None:
        try:
            response = self.service.ask(text)
            if response:
                self.speak(response, context=context)
        except Exception as exc:
            logger.exception("Error processing OVOS utterance '%s': %s", text, exc)
            self.speak("Sorry, I encountered an internal error.", context=context)

    def _handle_stop(self, message: Any) -> None:
        """Handle mycroft.stop intent for immediate barge-in."""
        logger.info("Received OVOS stop event (barge-in)")
        self.service.cancel(reason="ovos_stop")

    def speak(self, text: str, context: Optional[dict[str, Any]] = None) -> None:
        """Publish TTS speak event to ovos-audio."""
        if not self._client:
            return

        payload = {"utterance": text, "expect_response": False}
        msg = Message("speak", payload, context=context or {})
        try:
            self._client.emit(msg)
        except Exception as exc:
            logger.error("Failed to emit speak event to OVOS bus: %s", exc)

    def close(self) -> None:
        """Disconnect and close the MessageBus client."""
        with self._lock:
            if self._client and self._connected:
                try:
                    self._client.close()
                except Exception:
                    pass
                self._connected = False
