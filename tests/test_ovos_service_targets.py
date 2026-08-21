from pathlib import Path


def _unit(name: str) -> str:
    return (Path(__file__).parents[1] / "deploy/ovos" / name).read_text(encoding="utf-8")


def test_core_target_owns_bus_and_core():
    text = _unit("marina-ovos-core.target")
    assert "Requires=marina-messagebus.service marina-core.service" in text
    assert "After=marina-messagebus.service marina-core.service" in text


def test_voice_target_builds_on_core_and_adds_audio_path():
    text = _unit("marina-voice.target")
    assert "Requires=marina-ovos-core.target marina-listener.service marina-audio.service" in text
    assert "After=marina-ovos-core.target marina-listener.service marina-audio.service" in text


def test_runtime_smoke_has_core_and_voice_presets():
    text = (Path(__file__).parents[1] / "scripts/ovos-runtime-smoke.py").read_text(encoding="utf-8")
    assert '"core": ["marina-messagebus.service", "marina-core.service"]' in text
    assert '"marina-listener.service"' in text
    assert '"marina-audio.service"' in text


def test_service_units_are_templated_for_custom_venv() -> None:
    from pathlib import Path

    root = Path(__file__).parents[1]
    service_files = list((root / "deploy" / "ovos").glob("marina-*.service"))
    assert service_files
    for service in service_files:
        text = service.read_text()
        assert "@MARINA_VENV@/bin/" in text
        assert "%h/.venv/bin/" not in text
