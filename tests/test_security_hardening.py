from pathlib import Path

import pytest

from marina.features import _validate_public_url, fetch_url
from marina.domain.capabilities import Capability, CapabilityRegistry, CapabilityRisk, ToolBroker, ToolDefinition


def test_private_and_loopback_urls_are_rejected():
    for url in ("http://127.0.0.1:8080", "http://localhost", "http://169.254.169.254/latest/meta-data"):
        with pytest.raises(ValueError):
            _validate_public_url(url)


def test_url_credentials_are_rejected():
    with pytest.raises(ValueError):
        _validate_public_url("https://user:pass@example.com/")


def test_local_write_requires_explicit_approval():
    registry = CapabilityRegistry((Capability("fs", "filesystem"),))
    broker = ToolBroker(registry)
    broker.register(ToolDefinition("fs.write", "fs", "write", CapabilityRisk.LOCAL_WRITE), lambda: "ok")
    with pytest.raises(PermissionError):
        broker.execute("fs.write", approved=False)
    assert broker.execute("fs.write", approved=True) == "ok"


def test_fetch_url_rejects_invalid_size():
    with pytest.raises(ValueError):
        fetch_url("https://example.com", 0)
    with pytest.raises(ValueError):
        fetch_url("https://example.com", 4_000_001)

from marina.features import SatelliteEnvelope


def test_tool_approval_token_is_single_use_and_expires():
    from marina.application.service import AssistantService
    from marina.core.events import InMemoryEventBus
    from marina.infrastructure.persistence.sqlite import SQLiteConversationStore
    from marina.infrastructure.providers.echo import EchoProvider
    from marina.infrastructure.providers.router import StaticProviderRouter
    tmp = Path('/tmp/marina-approval-test')
    tmp.mkdir(parents=True, exist_ok=True)
    store = SQLiteConversationStore(tmp / 'm.db')
    s = AssistantService(router=StaticProviderRouter({'echo': EchoProvider()}, 'echo'), store=store, event_bus=InMemoryEventBus())
    try:
        issued = s.request_tool_approval('filesystem.write', ttl_seconds=30)
        token = issued['token']
        result = s.tool_execute('filesystem.write', approval_token=token, path=str(Path('/tmp/marina-approval-test/approved.txt')), content='ok')
        assert result is None
        with pytest.raises(PermissionError):
            s.tool_execute('filesystem.write', approval_token=token, path=str(Path('/tmp/marina-approval-test/approved2.txt')), content='bad')
    finally:
        s.close()


def test_satellite_envelope_rejects_stale_messages():
    import time
    envelope = SatelliteEnvelope('test', {}, timestamp=time.time() - 60)
    with pytest.raises(ValueError):
        envelope.validate(max_age_seconds=30)


def test_approval_token_is_reported_as_approved_in_audit(tmp_path):
    from marina.application.service import AssistantService
    from marina.core.events import InMemoryEventBus
    from marina.infrastructure.persistence.sqlite import SQLiteConversationStore
    from marina.infrastructure.providers.echo import EchoProvider
    from marina.infrastructure.providers.router import StaticProviderRouter

    store = SQLiteConversationStore(tmp_path / "m.db")
    service = AssistantService(router=StaticProviderRouter({"echo": EchoProvider()}, "echo"), store=store, event_bus=InMemoryEventBus())
    try:
        issued = service.request_tool_approval("filesystem.write")
        service.tool_execute("filesystem.write", approval_token=issued["token"], path=str(tmp_path / "approved.txt"), content="ok")
        audit = service.tool_audit_snapshot(1)[0]
        assert audit["approved"] is True
        assert audit["success"] is True
    finally:
        service.close()
