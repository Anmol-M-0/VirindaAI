from __future__ import annotations

from marina.domain.models import ProviderRequest


class EchoProvider:
    name = "echo"

    def stream(self, request: ProviderRequest):
        text = request.messages[-1].content if request.messages else ""
        yield f"Marina received: {text}"
