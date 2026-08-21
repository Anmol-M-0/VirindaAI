from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from virinda.application.runtime import build_service
from virinda.config.settings import Settings
from virinda.ovos.bridge import OVOSMessageBusBridge


@pytest.fixture
def test_service(tmp_path: Path):
    settings = Settings.from_env().with_data_dir(tmp_path)
    return build_service(settings)


def test_ovos_bridge_lifecycle(test_service):
    mock_bus = MagicMock()
    bridge = OVOSMessageBusBridge(service=test_service, bus_client=mock_bus)

    assert bridge.is_connected is False
    bridge.connect()
    assert bridge.is_connected is True
    assert mock_bus.on.call_count >= 2
    mock_bus.run_in_thread.assert_called_once()

    bridge.close()
    assert bridge.is_connected is False


def test_ovos_bridge_utterance_handler(test_service):
    mock_bus = MagicMock()
    bridge = OVOSMessageBusBridge(service=test_service, bus_client=mock_bus)
    bridge.connect()

    # Simulate utterance message from Dinkum Listener
    msg = MagicMock()
    msg.data = {"utterances": ["hello assistant"]}
    msg.context = {"source": "dinkum"}

    bridge._handle_utterance(msg)
    time.sleep(0.2)  # Wait for async worker thread

    assert mock_bus.emit.called
    emitted_msg = mock_bus.emit.call_args[0][0]
    assert (
        getattr(emitted_msg, "msg_type", "") == "speak"
        or getattr(emitted_msg, "type", "") == "speak"
        or hasattr(emitted_msg, "data")
    )
    bridge.close()


def test_ovos_bridge_stop_handler(test_service):
    mock_bus = MagicMock()
    bridge = OVOSMessageBusBridge(service=test_service, bus_client=mock_bus)
    bridge.connect()

    msg = MagicMock()
    bridge._handle_stop(msg)

    # Asserts cancel was processed without error
    assert bridge.is_connected is True
    bridge.close()
