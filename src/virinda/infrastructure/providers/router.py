from __future__ import annotations

from virinda.domain.models import ProviderRequest


class ProviderNotConfiguredError(RuntimeError):
    pass


class StaticProviderRouter:
    def __init__(self, providers, default: str) -> None:
        self._providers = dict(providers)
        self._default = default
        if default not in self._providers:
            raise ProviderNotConfiguredError(f"default provider not configured: {default}")

    def select(self, request: ProviderRequest):
        name = str(request.metadata.get("provider", self._default))
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderNotConfiguredError(f"provider not configured: {name}") from exc

    def register(self, provider) -> None:
        self._providers[provider.name] = provider

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))
