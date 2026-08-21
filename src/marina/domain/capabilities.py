from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Any


class CapabilityRisk(StrEnum):
    READ = "read"
    LOCAL_WRITE = "local_write"
    EXTERNAL = "external"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True, slots=True)
class Capability:
    """Machine-readable feature/tool capability advertised by Marina."""

    name: str
    description: str
    risk: CapabilityRisk = CapabilityRisk.READ
    enabled: bool = True


class CapabilityRegistry:
    """Thread-safe-enough immutable-by-convention capability registry.

    Registration happens during application startup; reads are lock-free and return
    stable copies so IPC/UI clients cannot mutate server state accidentally.
    """

    def __init__(self, capabilities: tuple[Capability, ...] = ()) -> None:
        self._items = {item.name: item for item in capabilities}

    def register(self, capability: Capability) -> None:
        if not capability.name.strip():
            raise ValueError("capability name cannot be empty")
        if capability.name in self._items:
            raise ValueError(f"capability already registered: {capability.name}")
        self._items[capability.name] = capability

    def has(self, name: str) -> bool:
        item = self._items.get(name)
        return bool(item and item.enabled)

    def get(self, name: str) -> Capability | None:
        return self._items.get(name)

    def list(self) -> tuple[Capability, ...]:
        return tuple(self._items[name] for name in sorted(self._items))


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    capability: str
    description: str
    risk: CapabilityRisk = CapabilityRisk.READ




@dataclass(frozen=True, slots=True)
class ApprovalToken:
    token: str
    tool: str
    expires_at: float


class ApprovalTokenStore:
    """In-memory, single-use approvals for consequential tools."""

    def __init__(self) -> None:
        self._tokens: dict[str, ApprovalToken] = {}
        self._lock = RLock()

    def issue(self, tool: str, ttl_seconds: float = 30.0) -> ApprovalToken:
        if ttl_seconds <= 0 or ttl_seconds > 300:
            raise ValueError("approval TTL must be between 0 and 300 seconds")
        token = ApprovalToken(secrets.token_urlsafe(24), tool, time.time() + ttl_seconds)
        with self._lock:
            self._tokens[token.token] = token
        return token

    def consume(self, token: str, tool: str) -> bool:
        with self._lock:
            item = self._tokens.pop(token, None)
        if item is None:
            return False
        return item.tool == tool and time.time() < item.expires_at

    def prune(self) -> None:
        now = time.time()
        with self._lock:
            for key, item in list(self._tokens.items()):
                if item.expires_at <= now:
                    self._tokens.pop(key, None)



class ToolBroker:
    """Permission boundary for future tools.

    A tool can only execute when its declared capability is enabled and the caller
    explicitly approves elevated-risk operations. This is intentionally tiny so
    future browser/system/desktop tools all use the same policy boundary.
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry
        self._tools: dict[str, tuple[ToolDefinition, Callable[..., Any]]] = {}

    def register(self, definition: ToolDefinition, handler: Callable[..., Any]) -> None:
        if definition.name in self._tools:
            raise ValueError(f"tool already registered: {definition.name}")
        self._tools[definition.name] = (definition, handler)

    def describe(self) -> tuple[ToolDefinition, ...]:
        return tuple(definition for definition, _ in sorted(self._tools.values(), key=lambda item: item[0].name))

    def execute(self, name: str, *, approved: bool = False, **kwargs: Any) -> Any:
        item = self._tools.get(name)
        if item is None:
            raise KeyError(name)
        definition, handler = item
        if not self.registry.has(definition.capability):
            raise PermissionError(f"capability disabled: {definition.capability}")
        if definition.risk in {CapabilityRisk.LOCAL_WRITE, CapabilityRisk.EXTERNAL, CapabilityRisk.DESTRUCTIVE} and not approved:
            raise PermissionError(f"explicit approval required for tool: {name}")
        return handler(**kwargs)
