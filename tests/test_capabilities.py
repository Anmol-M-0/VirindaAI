from marina.core.context import ContextMode, POLICIES
from marina.domain.capabilities import Capability, CapabilityRegistry, CapabilityRisk, ToolBroker, ToolDefinition


def test_context_policies_are_safe_defaults():
    assert POLICIES[ContextMode.NORMAL].persist_transcripts is True
    assert POLICIES[ContextMode.PRIVATE].persist_transcripts is False
    assert POLICIES[ContextMode.QUIET].follow_up_listening is False


def test_tool_broker_requires_explicit_approval_for_risky_tools():
    registry = CapabilityRegistry((Capability("browser_control", "browser", CapabilityRisk.EXTERNAL),))
    broker = ToolBroker(registry)
    broker.register(ToolDefinition("open_url", "browser_control", "open url", CapabilityRisk.EXTERNAL), lambda url: url)
    try:
        broker.execute("open_url", url="https://example.com")
    except PermissionError:
        pass
    else:
        raise AssertionError("risky tool executed without approval")
    assert broker.execute("open_url", approved=True, url="https://example.com") == "https://example.com"
