from pathlib import Path


def _unit(name: str) -> str:
    return (Path(__file__).parents[1] / "deploy/ovos" / name).read_text(encoding="utf-8")


def test_core_target_owns_bus_and_core():
    text = _unit("virinda-ovos-core.target")
    assert "Requires=virinda-messagebus.service virinda-core.service" in text
    assert "After=virinda-messagebus.service virinda-core.service" in text


def test_voice_target_builds_on_core_and_adds_audio_path():
    text = _unit("virinda-voice.target")
    assert (
        "Requires=virinda-ovos-core.target virinda-listener.service virinda-audio.service" in text
    )
    assert "After=virinda-ovos-core.target virinda-listener.service virinda-audio.service" in text


def test_runtime_smoke_has_core_and_voice_presets():
    text = (Path(__file__).parents[1] / "scripts/ovos-runtime-smoke.py").read_text(encoding="utf-8")
    assert '"core": ["virinda-messagebus.service", "virinda-core.service"]' in text
    assert '"virinda-listener.service"' in text
    assert '"virinda-audio.service"' in text


def test_service_units_are_templated_for_custom_venv() -> None:
    from pathlib import Path

    root = Path(__file__).parents[1]
    service_files = list((root / "deploy" / "ovos").glob("virinda-*.service"))
    assert service_files
    for service in service_files:
        text = service.read_text()
        assert "@VIRINDA_VENV@/bin/" in text
        assert "%h/.venv/bin/" not in text
