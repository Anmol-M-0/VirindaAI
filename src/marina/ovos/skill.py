from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from marina.interfaces.ipc import LocalRPCClient
from marina.ovos.gui import MarinaGUICommand, OVOSGuiBridge

try:
    from ovos_bus_client.message import Message
    from ovos_workshop.decorators import intent_handler
    from ovos_workshop.skills import OVOSSkill
except ImportError as exc:  # pragma: no cover - exercised only when optional extra is missing
    Message = Any  # type: ignore[assignment,misc]
    OVOSSkill = object  # type: ignore[misc,assignment]

    def intent_handler(*_args: Any, **_kwargs: Any):
        def decorator(func):
            return func
        return decorator

    _OVOS_IMPORT_ERROR = exc
else:
    _OVOS_IMPORT_ERROR = None


@dataclass(frozen=True, slots=True)
class MarinaOVOSConfig:
    """Small configuration surface owned by the Marina skill.

    Microphone, wake word, VAD, STT, TTS, audio routing, and message-bus ownership
    remain OVOS concerns and should be configured through ``ovos.conf``.
    """

    display_name: str = "Marina"


class MarinaSkill(OVOSSkill):
    """Thin OVOS skill that exposes Marina-specific controls and diagnostics.

    General conversation is intentionally left to the active OVOS Persona/solver.
    This skill observes canonical OVOS lifecycle events and forwards product-specific
    controls to the long-lived Marina daemon over local IPC.
    """
    """Thin OVOS skill for Marina-specific control and diagnostics.

    General conversational responses are intentionally delegated to the active OVOS
    Persona pipeline. This skill owns only Marina-specific commands and local state
    observation, avoiding a second competing voice loop.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if _OVOS_IMPORT_ERROR is not None:
            raise RuntimeError(
                "OVOS integration is unavailable; install `marina-ai[ovos]` "
                "or the OVOS runtime dependencies"
            ) from _OVOS_IMPORT_ERROR
        super().__init__(*args, **kwargs)
        self.config = MarinaOVOSConfig()
        self.gui = OVOSGuiBridge(self.bus)

    def initialize(self) -> None:
        # These events are provided by the OVOS listener/audio pipeline.
        self.add_event("recognizer_loop:utterance", self._on_utterance)
        self.add_event("speak", self._on_speak)
        self.add_event("ovos.listener.record.started", self._on_record_started)
        self.add_event("ovos.listener.record.ended", self._on_record_ended)
        self.add_event("ovos.audio.output.started", self._on_audio_started)
        self.add_event("ovos.audio.output.ended", self._on_audio_ended)
        self.gui.subscribe(self._on_gui_command)
        self._publish_gui_snapshot()


    def _publish_gui_snapshot(self) -> None:
        """Publish current Marina state to the OVOS GUI namespace."""
        result = self._rpc("status") or {}
        if not isinstance(result, dict):
            result = {"status": str(result)}
        self.gui.publish_state(result)

    def _on_gui_command(self, command: MarinaGUICommand) -> None:
        """Handle trusted local GUI commands over the OVOS MessageBus."""
        allowed = {
            "status", "context", "capabilities", "memory", "notifications",
            "routines", "routine_preview", "routine_run_now", "routine_disable",
            "routine_delete", "briefing", "set_context", "cancel",
        }
        request_id = str(command.data.get("request_id", ""))
        if command.command not in allowed:
            self.gui.publish_response(request_id, None, session_id=command.session_id, error="command not allowed")
            return
        params = dict(command.data.get("params", {}))
        try:
            result = self._rpc(command.command, **params)
            self.gui.publish_response(request_id, result, session_id=command.session_id)
            self._publish_gui_snapshot()
        except Exception as exc:
            self.gui.publish_response(request_id, None, session_id=command.session_id, error=str(exc))

    def _on_utterance(self, message: Message) -> None:
        # Keep this event hook intentionally lightweight. Durable Marina history is
        # written by an optional persistence bridge rather than blocking the voice bus.
        utterance = self._extract_utterance(message)
        if utterance:
            self._rpc("ovos_utterance", text=utterance, speaker=self._extract_speaker(message))
        self.log.debug("Marina heard utterance: %s", utterance)

    def _on_record_started(self, message: Message | None = None) -> None:
        self._rpc("ovos_listening", active=True)

    def _on_record_ended(self, message: Message | None = None) -> None:
        self._rpc("ovos_listening", active=False)

    def _on_audio_started(self, message: Message | None = None) -> None:
        self._rpc("ovos_speak", text="")

    def _on_audio_ended(self, message: Message | None = None) -> None:
        self._rpc("ovos_speech_complete")

    def _on_speak(self, message: Message) -> None:
        text = str(message.data.get("utterance", ""))
        if text:
            self._rpc("ovos_speak", text=text)
        self.log.debug("Marina speech event received: %s", text)

    @intent_handler("MarinaStatusIntent")
    def handle_status(self, message: Message | None = None) -> None:
        self.speak("Marina is online and running on OpenVoiceOS.")

    @intent_handler("MarinaStopIntent")
    def handle_stop(self, message: Message | None = None) -> None:
        # Use the standard OVOS stop event so audio, personas and skills all observe
        # the same cancellation semantics.
        self._rpc("cancel", reason="ovos_stop")
        self.bus.emit(Message("mycroft.stop"))

    @intent_handler("MarinaPrivateIntent")
    def handle_private(self, message: Message | None = None) -> None:
        self._rpc("set_context", mode="private")
        self.speak("Private mode enabled.")

    @intent_handler("MarinaNormalIntent")
    def handle_normal(self, message: Message | None = None) -> None:
        self._rpc("set_context", mode="normal")
        self.speak("Normal mode enabled.")

    @intent_handler("MarinaFocusIntent")
    def handle_focus(self, message: Message | None = None) -> None:
        self._rpc("set_context", mode="focus")
        self.speak("Focus mode enabled.")

    @intent_handler("MarinaQuietIntent")
    def handle_quiet(self, message: Message | None = None) -> None:
        self._rpc("set_context", mode="quiet")
        self.speak("Quiet mode enabled.")

    @intent_handler("MarinaBriefingIntent")
    def handle_briefing(self, message: Message | None = None) -> None:
        result = self._rpc("briefing")
        self.speak(str(result or "Nothing urgent to report."))

    @intent_handler("MarinaMeetingStartIntent")
    def handle_meeting_start(self, message: Message | None = None) -> None:
        self._rpc("meeting_start")
        self.speak("Meeting mode started.")

    @intent_handler("MarinaMeetingStopIntent")
    def handle_meeting_stop(self, message: Message | None = None) -> None:
        self._rpc("meeting_stop")
        self.speak("Meeting mode stopped.")

    def _rpc(self, method: str, **params: Any) -> Any:
        data_dir = Path(os.environ.get("MARINA_DATA_DIR", Path.home() / ".local/share/marina-ai"))
        socket_path = Path(os.environ.get("MARINA_SOCKET", data_dir / "marina.sock"))
        try:
            return LocalRPCClient(socket_path, timeout=3.0).call(method, **params)
        except Exception as exc:
            self.log.warning("Marina daemon RPC unavailable: %s", exc)
            return None

    @staticmethod
    def _extract_speaker(message: Message) -> str | None:
        data = message.data if hasattr(message, "data") else {}
        speaker = data.get("speaker") or data.get("speaker_id")
        return str(speaker) if speaker else None

    @staticmethod
    def _extract_utterance(message: Message) -> str:
        data = message.data if hasattr(message, "data") else {}
        utterances = data.get("utterances", [])
        if isinstance(utterances, list) and utterances:
            return str(utterances[0])
        return str(data.get("utterance", ""))


def validate_skill_layout(root: Path) -> None:
    """Validate the packaged OVOS skill assets without importing OVOS."""

    intent_names = [
        "MarinaStatusIntent", "MarinaStopIntent", "MarinaPrivateIntent", "MarinaNormalIntent",
        "MarinaFocusIntent", "MarinaQuietIntent", "MarinaBriefingIntent",
        "MarinaMeetingStartIntent", "MarinaMeetingStopIntent",
    ]
    required = [root / "skill.json", root / "main.py", *(root / "locale" / "en-us" / f"{name}.intent" for name in intent_names)]
    missing = [str(p.relative_to(root)) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("missing OVOS skill assets: " + ", ".join(missing))
    manifest = json.loads((root / "skill.json").read_text(encoding="utf-8"))
    if manifest.get("skill_id") != "skill-marin-ai.openvoiceos":
        raise ValueError("unexpected Marina skill_id")
