from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from virinda.application.runtime import build_service
from virinda.config.settings import Settings
from virinda.infrastructure.desktop.screen import ScreenGroundingProbe, ScreenshotResult
from virinda.infrastructure.vision.query import ScreenVisionQueryEngine
from virinda.ovos.hivemind import HiveMindBridge


@pytest.fixture
def service(tmp_path: Path):
    settings = Settings.from_env().with_data_dir(tmp_path)
    return build_service(settings)


def test_hivemind_device_registration_and_routing(service):
    mock_bus = MagicMock()
    bridge = HiveMindBridge(service, bus=mock_bus)

    dev = bridge.register_device("pi_kitchen", "Kitchen Speaker", site_id="kitchen")
    assert dev.device_id == "pi_kitchen"
    assert dev.name == "Kitchen Speaker"

    reply = bridge.handle_satellite_utterance("pi_kitchen", "hello assistant")
    assert reply is not None
    assert mock_bus.emit.call_count == 1

    speak_msg = mock_bus.emit.call_args[0][0]
    assert speak_msg.msg_type == "speak"
    assert speak_msg.data["device_id"] == "pi_kitchen"
    assert len(bridge.active_devices()) == 1


def test_screen_vision_query_engine(service, tmp_path: Path):
    fake_img = tmp_path / "fake_screen.png"
    fake_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)

    mock_probe = MagicMock(spec=ScreenGroundingProbe)
    mock_probe.is_available = True
    mock_probe.capture.return_value = ScreenshotResult(
        image_path=fake_img, backend="grim", timestamp=100.0
    )

    engine = ScreenVisionQueryEngine(service, screen_probe=mock_probe)
    res = engine.query_screen("What is on the screen?", cleanup=True)

    assert res["ok"] is True
    assert "answer" in res
    assert "desktop_context" in res
    assert res["latency_ms"] >= 0.0
    # Cleanup should have deleted fake_img
    assert not fake_img.exists()
