from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from virinda.ovos.audio_diagnostics import inspect_linux_audio


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: str
    detail: str
    required: bool = True

    @property
    def ok(self) -> bool:
        return self.status in {"ok", "skip"}


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: tuple[Check, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok or not check.required for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "checks": [asdict(c) for c in self.checks]}


def _module_check(name: str, import_name: str, *, required: bool = True) -> Check:
    installed = importlib.util.find_spec(import_name) is not None
    if installed:
        return Check(name, "ok", f"Python module {import_name} is installed", required)
    return Check(
        name, "fail" if required else "skip", f"Python module {import_name} is missing", required
    )


def _file_check(name: str, path: Path, *, required: bool = True) -> Check:
    if path.is_file():
        return Check(name, "ok", str(path), required)
    return Check(name, "fail" if required else "skip", f"missing: {path}", required)


def _persona_check(path: Path) -> Check:
    if not path.is_file():
        return Check("persona", "fail", f"missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check("persona", "fail", f"invalid JSON: {exc}")
    solvers = payload.get("solvers", [])
    # The production profile intentionally follows the current OVOS stable
    # channel, where Persona 0.6.x + OpenAI plugin 2.0.x still uses the
    # legacy solver entry point. The newer chat agent is checked separately.
    if "ovos-solver-openai-plugin" not in solvers:
        return Check("persona", "fail", "stable persona must reference ovos-solver-openai-plugin")
    plugin_config = payload.get("ovos-solver-openai-plugin", {})
    for key in ("api_url", "model"):
        if not plugin_config.get(key):
            return Check("persona", "fail", f"missing ovos-solver-openai-plugin.{key}")
    return Check("persona", "ok", f"valid stable persona: {path}")


def _experimental_persona_check(path: Path) -> Check:
    if not path.is_file():
        return Check("experimental-agent-persona", "skip", f"missing: {path}", required=False)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check("experimental-agent-persona", "fail", f"invalid JSON: {exc}", required=False)
    solvers = payload.get("solvers", [])
    if solvers != ["ovos-chat-openai-plugin"]:
        return Check(
            "experimental-agent-persona",
            "fail",
            "experimental profile must reference ovos-chat-openai-plugin",
            required=False,
        )
    return Check(
        "experimental-agent-persona",
        "ok",
        f"valid experimental agent persona: {path}",
        required=False,
    )


def _wake_model_check(config_path: Path) -> Check:
    model = os.environ.get("VIRINDA_WAKE_MODEL", "")
    if model:
        return _file_check("wake-model", Path(model))
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        models = payload["hotwords"]["hey_virinda"]["models"]
        configured = models[0] if models else ""
    except (OSError, KeyError, TypeError, json.JSONDecodeError, IndexError):
        configured = ""
    if not configured or configured.startswith("/") is False or "ABSOLUTE" in configured:
        return Check("wake-model", "fail", "set a real hey_virinda model path in OVOS config")
    return _file_check("wake-model", Path(configured))


def _command_check(name: str, command: str, *, required: bool = False) -> Check:
    path = shutil.which(command)
    if path:
        return Check(name, "ok", f"{command}: {path}", required)
    return Check(name, "fail" if required else "skip", f"command not found: {command}", required)


def _user_service_check(name: str, unit: str, *, required: bool = False) -> Check:
    systemctl = shutil.which("systemctl")
    if not systemctl:
        return Check(name, "skip", "systemctl is not installed", required)
    try:
        result = subprocess.run(
            [systemctl, "--user", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(name, "skip", f"unable to query {unit}: {exc}", required)
    state = result.stdout.strip() or result.stderr.strip() or "unknown"
    if result.returncode == 0 and state == "active":
        return Check(name, "ok", f"{unit} is active", required)
    return Check(name, "fail" if required else "skip", f"{unit}: {state}", required)


def _nats_check(*, required: bool = False) -> Check:
    """Check the optional NATS Python client without attempting network I/O."""
    installed = importlib.util.find_spec("nats") is not None
    if installed:
        return Check("nats-py", "ok", "nats-py client is installed", required)
    return Check(
        "nats-py",
        "fail" if required else "skip",
        "nats-py is missing; install the job-backbone extra",
        required,
    )


def run_doctor(
    root: Path, *, check_services: bool = False, check_audio: bool = False, check_nats: bool = False
) -> DoctorReport:
    root = root.resolve()
    config_dir = root / "config" / "ovos"
    config_path = config_dir / "mycroft.conf.example.json"
    configured = {}
    try:
        configured = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        configured = {}
    stt_module = configured.get("stt", {}).get("module", "")
    tts_module = configured.get("tts", {}).get("module", "")
    checks: list[Check] = [
        _module_check("ovos-core", "ovos_core"),
        _module_check("dinkum-listener", "ovos_dinkum_listener"),
        _module_check("openwakeword-plugin", "ovos_ww_plugin_openwakeword", required=False),
        _module_check("silero-vad", "ovos_vad_plugin_silero", required=False),
        _module_check("persona-service", "ovos_persona"),
        _module_check("openai-plugin", "ovos_openai_plugin"),
        _module_check("audio", "ovos_audio"),
        _module_check(
            "whispercpp-stt",
            "ovos_stt_plugin_whispercpp",
            required=stt_module == "ovos-stt-plugin-whispercpp",
        ),
        _module_check(
            "vosk-stt", "ovos_stt_plugin_vosk", required=stt_module == "ovos-stt-plugin-vosk"
        ),
        _module_check("phoonnx-tts", "phoonnx", required=tts_module == "ovos-tts-plugin-phoonnx"),
        _file_check("OVOS config template", config_path),
        _persona_check(config_dir / "virinda-persona.json"),
        _experimental_persona_check(config_dir / "experimental-agent/virinda-persona.json"),
    ]
    if config_path.is_file():
        checks.append(_wake_model_check(config_path))
    else:
        checks.append(Check("wake-model", "fail", "OVOS config template is missing"))

    checks.extend(
        [
            _command_check("ovos-core command", "ovos-core"),
            _command_check("ovos-listener command", "ovos-dinkum-listener"),
            _command_check("ovos-audio command", "ovos-audio"),
            _command_check("ovos-messagebus command", "ovos-messagebus"),
        ]
    )
    if check_nats:
        nats_url = os.environ.get("VIRINDA_NATS_URL", "")
        checks.append(_nats_check(required=bool(os.environ.get("VIRINDA_JOB_BROKER") == "nats")))
        if nats_url:
            checks.append(Check("nats-url", "ok", nats_url, required=False))
        else:
            checks.append(Check("nats-url", "skip", "VIRINDA_NATS_URL is not set", required=False))
    if check_audio:
        audio = inspect_linux_audio()
        checks.append(
            Check(
                "pipewire",
                "ok" if audio["pipewire_available"] else "skip",
                "PipeWire/WirePlumber is reachable"
                if audio["pipewire_available"]
                else "PipeWire unavailable; install/start PipeWire for desktop audio",
                required=False,
            )
        )
    if check_services:
        checks.extend(
            [
                _user_service_check("messagebus-service", "virinda-messagebus.service"),
                _user_service_check("core-service", "virinda-core.service"),
                _user_service_check("listener-service", "virinda-listener.service"),
                _user_service_check("audio-service", "virinda-audio.service"),
            ]
        )
    return DoctorReport(tuple(checks))


def render_report(report: DoctorReport) -> str:
    lines = [f"Virinda OVOS doctor: {'PASS' if report.ok else 'FAIL'}"]
    for check in report.checks:
        lines.append(f"[{check.status.upper():4}] {check.name}: {check.detail}")
    return "\n".join(lines)
