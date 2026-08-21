from __future__ import annotations

import concurrent.futures
import time
from unittest.mock import MagicMock

from virinda.core.approvals import ApprovalManager
from virinda.infrastructure.desktop.probes import (
    DesktopContextSnapshot,
    detect_desktop_context,
)
from virinda.ovos.gui_streaming import StreamPublisher


def test_approval_manager_single_use_atomicity():
    mgr = ApprovalManager(default_ttl_seconds=10.0)
    req = mgr.create_request("delete_file", {"path": "/tmp/test.txt"}, risk_class="destructive")

    # Concurrent consumption simulation across 50 threads
    def try_approve():
        return mgr.approve_and_consume(req.token, "delete_file", {"path": "/tmp/test.txt"})

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        futures = [ex.submit(try_approve) for _ in range(50)]
        results = [f.result() for f in futures]

    assert results.count(True) == 1
    assert results.count(False) == 49


def test_approval_manager_action_substitution_denial():
    mgr = ApprovalManager(default_ttl_seconds=10.0)
    req = mgr.create_request("delete_file", {"path": "/tmp/safe.txt"}, risk_class="destructive")

    # Attempt to consume with altered payload
    denied = mgr.approve_and_consume(req.token, "delete_file", {"path": "/etc/passwd"})
    assert denied is False

    # Attempt with different action name
    denied2 = mgr.approve_and_consume(req.token, "format_disk", {"path": "/tmp/safe.txt"})
    assert denied2 is False


def test_approval_manager_expiry():
    mgr = ApprovalManager(default_ttl_seconds=0.05)
    req = mgr.create_request("open_url", {"url": "https://example.com"}, ttl_seconds=0.05)

    time.sleep(0.08)
    assert req.is_expired is True
    consumed = mgr.approve_and_consume(req.token, "open_url", {"url": "https://example.com"})
    assert consumed is False


def test_desktop_context_detection():
    snapshot = detect_desktop_context()
    assert isinstance(snapshot, DesktopContextSnapshot)
    assert snapshot.active_app is not None
    assert snapshot.compositor is not None
    assert snapshot.timestamp > 0.0


def test_stream_publisher_events():
    mock_bus = MagicMock()
    publisher = StreamPublisher(mock_bus)

    publisher.publish_delta("Hello ", session_id="s1")
    publisher.publish_delta("world!", session_id="s1")
    publisher.publish_tool_status("search", "executing", details={"q": "weather"})
    publisher.publish_approval_request(
        "tok123", "exec_cmd", "destructive", "Run bash", time.time() + 30.0
    )

    assert mock_bus.emit.call_count == 4
    delta_msg = mock_bus.emit.call_args_list[0][0][0]
    assert delta_msg.data["seq"] == 1
    assert delta_msg.data["delta"] == "Hello "
