from __future__ import annotations

import pytest

from virinda.core.approvals import ApprovalManager
from virinda.core.persona import PersonaManager, PersonaProfile
from virinda.core.tool_broker import ToolBroker


def test_persona_manager_switching():
    mgr = PersonaManager()
    assert mgr.active_persona.name == "default"

    # Switch to concise
    concise = mgr.set_persona("concise")
    assert concise.name == "concise"
    assert concise.concise is True
    assert concise.speech_rate_multiplier == 1.1

    # Switch to unknown
    with pytest.raises(ValueError, match="Unknown persona 'alien'"):
        mgr.set_persona("alien")

    # Register custom persona
    custom = PersonaProfile(
        name="pirate",
        description="Talks like a pirate",
        system_prompt_modifier="Ahoy matey!",
        speech_rate_multiplier=0.9,
    )
    mgr.register_persona(custom)
    mgr.set_persona("pirate")
    assert mgr.active_persona.name == "pirate"


def test_tool_broker_read_only_execution():
    broker = ToolBroker()
    broker.register_tool(
        name="add_numbers",
        description="Adds two numbers",
        risk_class="read_only",
        handler=lambda params: params["a"] + params["b"],
    )

    res = broker.execute_tool("add_numbers", {"a": 5, "b": 10})
    assert res.ok is True
    assert res.output == 15
    assert res.requires_approval is False


def test_tool_broker_destructive_approval_gating():
    approval_mgr = ApprovalManager(default_ttl_seconds=10.0)
    broker = ToolBroker(approval_manager=approval_mgr)

    deleted_paths = []
    broker.register_tool(
        name="delete_dir",
        description="Deletes a directory",
        risk_class="destructive",
        handler=lambda params: deleted_paths.append(params["path"]),
    )

    # 1. Attempt execution without token -> Intercepted
    res = broker.execute_tool("delete_dir", {"path": "/tmp/test"})
    assert res.ok is False
    assert res.requires_approval is True
    assert res.approval_request is not None
    assert len(deleted_paths) == 0

    token = res.approval_request.token

    # 2. Execute with valid token -> Succeeded
    res2 = broker.execute_tool("delete_dir", {"path": "/tmp/test"}, approval_token=token)
    assert res2.ok is True
    assert len(deleted_paths) == 1
    assert deleted_paths[0] == "/tmp/test"

    # 3. Replay token -> Denied
    res3 = broker.execute_tool("delete_dir", {"path": "/tmp/test"}, approval_token=token)
    assert res3.ok is False
    assert res3.requires_approval is True
