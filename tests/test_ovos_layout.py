import json
from pathlib import Path

import marina
from marina.ovos.skill import validate_skill_layout


def test_ovos_skill_layout_is_valid():
    root = Path(__file__).parents[1] / "skills" / "skill-marin-ai"
    validate_skill_layout(root)
    manifest = json.loads((root / "skill.json").read_text(encoding="utf-8"))
    assert manifest["version"] == marina.__version__
    assert manifest["skill_id"] == "skill-marin-ai.openvoiceos"


def test_ovos_config_is_valid_json():
    root = Path(__file__).parents[1] / "config" / "ovos"
    for name in ("mycroft.conf.example.json", "marina-persona.json"):
        payload = json.loads((root / name).read_text(encoding="utf-8"))
        assert isinstance(payload, dict)


def test_ovos_config_has_local_stt_and_hybrid_listen():
    root = Path(__file__).parents[1]
    config = json.loads((root / "config/ovos/mycroft.conf.example.json").read_text(encoding="utf-8"))
    assert config["stt"]["module"] == "ovos-stt-plugin-whispercpp"
    assert config["stt"]["ovos-stt-plugin-whispercpp"]["model"] == "base.en"
    assert config["listener"]["hybrid_listen"] is True


def test_ovos_persona_uses_current_chat_engine_key():
    root = Path(__file__).parents[1]
    persona = json.loads((root / "config/ovos/marina-persona.json").read_text(encoding="utf-8"))
    assert persona["solvers"] == ["ovos-solver-openai-plugin"]
    assert "handlers" not in persona


def test_experimental_agent_profile_is_isolated():
    root = Path(__file__).parents[1]
    persona = json.loads((root / "config/ovos/experimental-agent/marina-persona.json").read_text(encoding="utf-8"))
    assert persona["solvers"] == ["ovos-chat-openai-plugin"]


def test_ovos_skill_dependency_matches_release():
    root = Path(__file__).parents[1]
    req = (root / "skills/skill-marin-ai/requirements.txt").read_text(encoding="utf-8").strip()
    assert req == f"marina-ai=={marina.__version__}"


def test_ovos_installer_installs_bundled_skill_and_profiles():
    root = Path(__file__).parents[1]
    installer = (root / "scripts/install-ovos.sh").read_text(encoding="utf-8")
    assert 'MARINA_OVOS_PROFILE' in installer
    assert 'SKILL_DIR=' in installer
    assert 'skill-marin-ai.openvoiceos' in installer
    assert 'if [[ "$PROFILE" == "local-voice" ]]' in installer


def test_installer_can_optionally_install_config_without_overwriting():
    root = Path(__file__).parents[1]
    installer = (root / "scripts/install-ovos.sh").read_text(encoding="utf-8")
    assert 'MARINA_INSTALL_CONFIG' in installer
    assert 'Refusing to overwrite existing OVOS config' in installer


def test_installer_provisions_systemd_units_by_default():
    root = Path(__file__).parents[1]
    installer = (root / "scripts/install-ovos.sh").read_text(encoding="utf-8")
    assert 'INSTALL_SERVICES="${MARINA_INSTALL_SERVICES:-1}"' in installer
    assert 'deploy/ovos/marina-*.service' in installer
    assert 'deploy/ovos/marina-*.target' in installer
    assert 'systemctl --user daemon-reload' in installer


def test_uninstaller_preserves_database_and_venv():
    root = Path(__file__).parents[1]
    script = (root / "scripts/uninstall-ovos.sh").read_text(encoding="utf-8")
    assert 'rm -rf "$SKILL_DIR/skill-marin-ai.openvoiceos"' in script
    assert 'rm -f "$PERSONA_DIR/Marina.json"' in script
    assert 'virtualenv and Marina database are intentionally preserved' in script
    assert 'REMOVE_CONFIG="${MARINA_REMOVE_CONFIG:-0}"' in script


def test_first_boot_delegates_to_installer_and_optional_autostart():
    root = Path(__file__).parents[1]
    script = (root / "scripts/first-boot-ovos.sh").read_text(encoding="utf-8")
    assert 'scripts/install-ovos.sh' in script
    assert 'MARINA_AUTO_START' in script
    assert 'marina-ovos-core.target' in script
    assert 'marina-voice.target' in script


def test_marina_voice_control_intents_are_packaged():
    root = Path(__file__).parents[1] / "skills" / "skill-marin-ai" / "locale" / "en-us"
    expected = {"MarinaPrivateIntent", "MarinaNormalIntent", "MarinaFocusIntent", "MarinaQuietIntent", "MarinaBriefingIntent", "MarinaMeetingStartIntent", "MarinaMeetingStopIntent"}
    assert all((root / f"{name}.intent").is_file() for name in expected)


def test_skill_bridges_canonical_ovos_audio_lifecycle():
    source = (Path(__file__).parents[1] / "src" / "marina" / "ovos" / "skill.py").read_text(encoding="utf-8")
    for topic in (
        "ovos.listener.record.started",
        "ovos.listener.record.ended",
        "ovos.audio.output.started",
        "ovos.audio.output.ended",
    ):
        assert topic in source
