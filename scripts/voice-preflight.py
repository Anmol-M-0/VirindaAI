#!/usr/bin/env python3
"""Preflight a Linux host before Marina P0 voice acceptance.

This command is read-only. It inspects the local OVOS installation and PipeWire/ALSA
surface without changing audio routing or saving recordings.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import subprocess
import sys


def run(command: list[str], timeout: float = 3.0) -> dict[str, object]:
    exe = shutil.which(command[0])
    if not exe:
        return {
            "command": command,
            "available": False,
            "returncode": None,
            "stdout": "",
            "stderr": f"not found: {command[0]}",
        }
    try:
        p = subprocess.run(
            [exe, *command[1:]], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command": command,
            "available": True,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "command": command,
        "available": True,
        "returncode": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
    }


def module_version(name: str) -> dict[str, object]:
    spec = importlib.util.find_spec(name)
    return {"module": name, "installed": spec is not None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    report: dict[str, object] = {
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "checks": {
            "linux": platform.system().lower() == "linux",
            "ovos_bus_client": module_version("ovos_bus_client"),
            "ovos_core": module_version("ovos_core"),
            "ovos_dinkum_listener": module_version("ovos_dinkum_listener"),
            "wpctl": run(["wpctl", "status", "-n"]),
            "pipewire_sources": run(["wpctl", "list", "audio", "sources"]),
            "pipewire_sinks": run(["wpctl", "list", "audio", "sinks"]),
            "alsa_capture": run(["arecord", "-l"]),
            "alsa_playback": run(["aplay", "-l"]),
        },
    }

    checks = report["checks"]
    failures: list[str] = []
    if not checks["linux"]:
        failures.append("host is not Linux")
    for module in ("ovos_bus_client", "ovos_core", "ovos_dinkum_listener"):
        if not checks[module]["installed"]:
            failures.append(f"missing Python module: {module}")
    for command_name in (
        "wpctl",
        "pipewire_sources",
        "pipewire_sinks",
        "alsa_capture",
        "alsa_playback",
    ):
        result = checks[command_name]
        if not result["available"] or result["returncode"] != 0:
            failures.append(f"audio check unavailable/failed: {command_name}")

    report["ready"] = not failures
    report["failures"] = failures

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Linux voice preflight: {'READY' if not failures else 'NOT READY'}")
        for failure in failures:
            print(f"  - {failure}")
        if not failures:
            print("OVOS bus/core/listener and PipeWire/ALSA inspection surfaces are available.")

    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
