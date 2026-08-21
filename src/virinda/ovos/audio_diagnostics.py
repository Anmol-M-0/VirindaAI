from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class AudioCommandResult:
    command: tuple[str, ...]
    available: bool
    returncode: int | None
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self) | {"command": list(self.command)}


def _run(command: Sequence[str], timeout: float = 3.0) -> AudioCommandResult:
    command = tuple(command)
    executable = shutil.which(command[0])
    if not executable:
        return AudioCommandResult(command, False, None, "", f"command not found: {command[0]}")
    try:
        result = subprocess.run(
            [executable, *command[1:]],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return AudioCommandResult(command, True, None, "", str(exc))
    return AudioCommandResult(command, True, result.returncode, result.stdout, result.stderr)


def inspect_linux_audio() -> dict[str, object]:
    """Inspect PipeWire/WirePlumber and ALSA without changing device state."""
    results = [
        _run(("wpctl", "status", "-n")),
        _run(("wpctl", "list", "sources")),
        _run(("wpctl", "list", "sinks")),
        _run(("arecord", "-l")),
        _run(("aplay", "-l")),
    ]
    pipewire = next((r for r in results if r.command[:1] == ("wpctl",)), None)
    return {
        "platform": "linux",
        "pipewire_available": bool(pipewire and pipewire.available and pipewire.returncode == 0),
        "checks": [r.to_dict() for r in results],
    }
