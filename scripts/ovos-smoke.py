#!/usr/bin/env python3
"""Run a hardware-free smoke test against an installed OVOS + Marina environment."""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "config/ovos/compatibility.json"


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("stable", "local-voice"),
        default="stable",
        help="environment contract to verify (default: stable)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse()
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    expected = dict(matrix["stable_channel"]["required"])
    if args.profile == "local-voice":
        expected.update(matrix["audio_addons"]["stable_plugin_pins"])
        expected.update(matrix["audio_addons"]["extra_pins"])

    checks = []
    for package, spec in expected.items():
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError:
            checks.append({"package": package, "status": "missing", "expected": spec})
            continue
        checks.append({"package": package, "status": "installed", "version": installed, "expected": spec})

    missing = [c for c in checks if c["status"] == "missing"]
    report = {
        "ok": not missing,
        "profile": args.profile,
        "python": sys.version.split()[0],
        "checks": checks,
        "note": (
            "This verifies the installed distribution surface only. Run the OVOS boot harness "
            "on a provisioned Linux host for message-bus/core/listener/audio runtime validation."
        ),
    }
    print(json.dumps(report, indent=2))
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
