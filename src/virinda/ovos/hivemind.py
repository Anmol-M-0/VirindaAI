from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from virinda.application.service import AssistantService

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


@dataclass(slots=True)
class SatelliteDevice:
    device_id: str
    name: str
    site_id: str = "default"
    capabilities: list[str] = field(default_factory=lambda: ["audio_in", "audio_out"])
    session_id: str = "default"
    last_seen: float = field(default_factory=time.time)
    authenticated: bool = True


class HiveMindBridge:
    """Satellite mesh relay bridge connecting remote HiveMind smart speakers to Virinda AssistantService."""

    def __init__(
        self,
        service: AssistantService,
        bus: Optional[Any] = None,
    ) -> None:
        self.service = service
        self.bus = bus
        self._devices: dict[str, SatelliteDevice] = {}
        self._lock = threading.RLock()

    def register_device(
        self,
        device_id: str,
        name: str,
        site_id: str = "default",
        capabilities: Optional[list[str]] = None,
    ) -> SatelliteDevice:
        with self._lock:
            dev = SatelliteDevice(
                device_id=device_id,
                name=name,
                site_id=site_id,
                capabilities=capabilities or ["audio_in", "audio_out"],
                session_id=f"satellite_{device_id}",
                last_seen=time.time(),
                authenticated=True,
            )
            self._devices[device_id] = dev
            return dev

    def handle_satellite_utterance(
        self,
        device_id: str,
        utterance: str,
        context: Optional[dict[str, Any]] = None,
    ) -> str:
        """Processes an utterance from a remote satellite device and routes back speech."""
        with self._lock:
            dev = self._devices.get(device_id)
            if not dev:
                # Auto-register unknown authenticated client
                dev = self.register_device(device_id, name=f"Satellite-{device_id[:6]}")
            dev.last_seen = time.time()

        turn_ctx = context or {}
        turn_ctx["satellite"] = {
            "device_id": dev.device_id,
            "site_id": dev.site_id,
            "session_id": dev.session_id,
        }

        # Process through Virinda AssistantService
        response = self.service.ask(utterance)

        # Emit speak event back targeted to the satellite session if bus is connected
        if self.bus and response:
            msg = Message(
                "speak",
                data={"utterance": response, "device_id": device_id},
                context={
                    "source": f"hivemind.{device_id}",
                    "session": {"session_id": dev.session_id},
                    "target": device_id,
                },
            )
            try:
                self.bus.emit(msg)
            except Exception as exc:
                logger.debug("Failed to emit satellite speak event: %s", exc)

        return response

    def handle_satellite_barge_in(self, device_id: str) -> None:
        """Processes a remote cancellation or barge-in event from a satellite device."""
        with self._lock:
            dev = self._devices.get(device_id)
            if dev:
                dev.last_seen = time.time()

        if self.bus:
            msg = Message(
                "mycroft.stop",
                data={"device_id": device_id},
                context={"source": f"hivemind.{device_id}", "target": device_id},
            )
            try:
                self.bus.emit(msg)
            except Exception as exc:
                logger.debug("Failed to emit satellite stop event: %s", exc)

    def active_devices(self) -> list[SatelliteDevice]:
        with self._lock:
            now = time.time()
            return [d for d in self._devices.values() if (now - d.last_seen) < 300.0]
