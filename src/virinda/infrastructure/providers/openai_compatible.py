from __future__ import annotations

import json
from collections.abc import Iterator
from urllib import error as urlerror
from urllib import request as urlrequest

from virinda.domain.models import ProviderRequest


class OpenAICompatibleProvider:
    """Stdlib-only OpenAI-compatible chat-completions adapter with SSE streaming."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        default_model: str,
        timeout: float = 90.0,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout

    def stream(self, req: ProviderRequest) -> Iterator[str]:
        payload = json.dumps(
            {
                "model": req.model or self.default_model,
                "messages": [{"role": m.role, "content": m.content} for m in req.messages],
                "stream": True,
            }
        ).encode("utf-8")
        http_req = urlrequest.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "User-Agent": "virinda-ai/0.7",
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(http_req, timeout=self.timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                if "text/event-stream" in content_type:
                    yield from self._stream_sse(response)
                else:
                    body = json.loads(response.read().decode("utf-8"))
                    content = self._extract_content(body)
                    if content:
                        yield content
        except urlerror.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"provider HTTP {exc.code}: {details[:500]}") from exc
        except urlerror.URLError as exc:
            raise RuntimeError(f"provider connection failed: {exc.reason}") from exc

    @classmethod
    def _stream_sse(cls, response) -> Iterator[str]:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                return
            try:
                body = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise RuntimeError("provider returned malformed SSE JSON") from exc
            delta = cls._extract_delta(body)
            if delta:
                yield delta

    @staticmethod
    def _extract_delta(body: dict) -> str:
        try:
            value = body["choices"][0]["delta"].get("content", "")
        except (KeyError, IndexError, AttributeError, TypeError):
            return ""
        if value is None:
            return ""
        if not isinstance(value, str):
            raise RuntimeError("provider streaming content was not text")
        return value

    @staticmethod
    def _extract_content(body: dict) -> str:
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("provider returned an invalid chat-completions response") from exc
        if not isinstance(content, str):
            raise RuntimeError("provider response content was not text")
        return content
