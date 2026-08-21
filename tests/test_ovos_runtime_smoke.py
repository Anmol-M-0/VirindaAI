import subprocess
import sys
from pathlib import Path


def test_runtime_smoke_reports_missing_ovos_cleanly():
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/ovos-runtime-smoke.py"), "marina status"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in {0, 2}
    assert '"status":' in result.stdout

import json


def test_runtime_smoke_requires_services_reports_missing_systemd_cleanly():
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/ovos-runtime-smoke.py"),
            "marina status",
            "--require-services",
            "--services",
            "definitely-missing-marina.service",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in {2}
    payload = json.loads(result.stdout)
    assert payload["status"] in {"services_not_ready", "environment_missing", "service_probe_failed"}
