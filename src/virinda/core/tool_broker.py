from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from virinda.core.approvals import ApprovalManager, ApprovalRequest

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    risk_class: str  # "read_only" | "local_write" | "destructive"
    handler: Callable[[dict[str, Any]], Any]


@dataclass(slots=True)
class ToolExecutionResult:
    tool_name: str
    ok: bool
    output: Any = None
    error: Optional[str] = None
    requires_approval: bool = False
    approval_request: Optional[ApprovalRequest] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "ok": self.ok,
            "output": self.output,
            "error": self.error,
            "requires_approval": self.requires_approval,
            "token": self.approval_request.token if self.approval_request else None,
        }


class ToolBroker:
    """In-process tool and function dispatch broker with risk-based approval gating."""

    def __init__(self, approval_manager: Optional[ApprovalManager] = None) -> None:
        self.approval_manager = approval_manager or ApprovalManager()
        self._tools: dict[str, ToolDefinition] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        risk_class: str,
        handler: Callable[[dict[str, Any]], Any],
    ) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            risk_class=risk_class,
            handler=handler,
        )

    def execute_tool(
        self,
        name: str,
        params: dict[str, Any],
        *,
        approval_token: Optional[str] = None,
        session_id: str = "default",
    ) -> ToolExecutionResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolExecutionResult(
                tool_name=name,
                ok=False,
                error=f"Unknown tool '{name}'. Available: {list(self._tools.keys())}",
            )

        # Intercept destructive actions
        if tool.risk_class == "destructive":
            if not approval_token:
                req = self.approval_manager.create_request(
                    action_name=name,
                    payload=params,
                    risk_class=tool.risk_class,
                    description=f"Execute destructive action '{name}'",
                    session_id=session_id,
                )
                return ToolExecutionResult(
                    tool_name=name,
                    ok=False,
                    requires_approval=True,
                    approval_request=req,
                    error=f"Action '{name}' requires user confirmation. Token: {req.token}",
                )

            # Consume token
            valid = self.approval_manager.approve_and_consume(
                token=approval_token,
                action_name=name,
                payload=params,
            )
            if not valid:
                return ToolExecutionResult(
                    tool_name=name,
                    ok=False,
                    requires_approval=True,
                    error="Invalid, expired, or mismatched approval token.",
                )

        try:
            output = tool.handler(params)
            return ToolExecutionResult(
                tool_name=name,
                ok=True,
                output=output,
            )
        except Exception as exc:
            logger.exception("Tool '%s' execution failed: %s", name, exc)
            return ToolExecutionResult(
                tool_name=name,
                ok=False,
                error=str(exc),
            )

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "risk_class": t.risk_class,
            }
            for t in self._tools.values()
        ]
