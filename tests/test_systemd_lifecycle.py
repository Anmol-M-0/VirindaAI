from __future__ import annotations

import configparser
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]


def _parse_unit_file(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    # preserve case
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    return parser


def test_virindad_systemd_unit():
    unit_path = REPO_ROOT / "deploy" / "systemd" / "virindad.service"
    assert unit_path.exists()

    config = _parse_unit_file(unit_path)
    assert config.has_section("Unit")
    assert config.has_section("Service")
    assert config.has_section("Install")

    assert "Description" in config["Unit"]
    assert "ExecStart" in config["Service"]
    assert "virindad" in config["Service"]["ExecStart"]
    assert config["Service"]["Restart"] == "on-failure"
    assert config["Install"]["WantedBy"] == "default.target"


def test_virindai_config_systemd_unit():
    unit_path = REPO_ROOT / "config" / "systemd" / "virindai.service"
    assert unit_path.exists()

    config = _parse_unit_file(unit_path)
    assert config.has_section("Unit")
    assert config.has_section("Service")
    assert config.has_section("Install")

    assert "Description" in config["Unit"]
    assert "ExecStart" in config["Service"]
    assert config["Service"]["Restart"] == "on-failure"
    assert config["Install"]["WantedBy"] == "default.target"


def test_ovos_deploy_units():
    ovos_dir = REPO_ROOT / "deploy" / "ovos"
    expected_units = [
        "virinda-audio.service",
        "virinda-core.service",
        "virinda-listener.service",
        "virinda-messagebus.service",
    ]
    for unit_name in expected_units:
        path = ovos_dir / unit_name
        assert path.exists(), f"Missing unit {unit_name}"
        config = _parse_unit_file(path)
        assert config.has_section("Unit")
        assert config.has_section("Service")
        assert "ExecStart" in config["Service"]


def test_systemd_analyze_if_available():
    systemd_analyze = shutil.which("systemd-analyze")
    if not systemd_analyze:
        return

    unit_paths = [
        REPO_ROOT / "deploy" / "systemd" / "virindad.service",
        REPO_ROOT / "config" / "systemd" / "virindai.service",
    ]
    for unit in unit_paths:
        res = subprocess.run(
            [systemd_analyze, "verify", str(unit)],
            capture_output=True,
            text=True,
        )
        # Note: systemd-analyze verify may emit warnings on missing runtime units in build sandbox
        # We ensure it does not fatal error on syntax
        assert "Failed to parse" not in res.stderr
