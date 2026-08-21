"""
Pluggable Ask / ChatGPT-CLI Provider Adapter for VirindAI runtime.
Implements VirindAI's CompletionProvider protocol.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Optional

from virinda.domain.models import ProviderRequest

# Ensure chatgpt-cli / ask is importable if present
_ASK_AVAILABLE = False
try:
    from ask.providers import BaseProvider, ProviderEvent, get_provider

    _ASK_AVAILABLE = True
except ImportError:
    cli_src = Path(__file__).resolve().parents[5] / "chatgpt-cli" / "src"
    if cli_src.exists() and str(cli_src) not in sys.path:
        sys.path.insert(0, str(cli_src))
    try:
        from ask.providers import BaseProvider, ProviderEvent, get_provider

        _ASK_AVAILABLE = True
    except ImportError:
        BaseProvider = object  # type: ignore
        ProviderEvent = object  # type: ignore
        get_provider = None  # type: ignore


class AskCompletionProvider:
    """
    In-process VirindAI CompletionProvider adapter delegating to chatgpt-cli (ask).
    Supports Groq, NVIDIA NIM, OpenRouter, and Browser backends with SSE token streaming.
    """

    def __init__(
        self,
        name: str = "ask",
        default_model: str = "meta/llama-3.3-70b-instruct",
        ask_provider: str = "auto",
        api_key: Optional[str] = None,
        headless: bool = True,
    ) -> None:
        self.name = name
        self.default_model = default_model
        self.ask_provider = ask_provider  # 'auto', 'nim', 'groq', 'openrouter', 'browser'
        self.api_key = api_key
        self.headless = headless

    def _extract_prompts(self, request: ProviderRequest) -> tuple[Optional[str], str]:
        """Separates system instructions from multi-turn conversation history."""
        system_chunks: list[str] = []
        conversation_turns: list[str] = []

        for msg in request.messages:
            role = (msg.role or "user").strip().lower()
            content = msg.content.strip()
            if not content:
                continue

            if role == "system":
                system_chunks.append(content)
            elif role == "user":
                conversation_turns.append(f"User: {content}")
            elif role == "assistant":
                conversation_turns.append(f"Assistant: {content}")
            else:
                conversation_turns.append(f"{role.capitalize()}: {content}")

        system_prompt = "\n\n".join(system_chunks) if system_chunks else None

        # Build prompt from conversation history
        if not conversation_turns:
            prompt = ""
        elif len(conversation_turns) == 1 and conversation_turns[0].startswith("User: "):
            prompt = conversation_turns[0][6:]
        else:
            prompt = "\n".join(conversation_turns)

        return system_prompt, prompt

    def stream(self, req: ProviderRequest) -> Iterator[str]:
        """Streams plain token chunks to VirindAI without UI formatting."""
        if not _ASK_AVAILABLE or get_provider is None:
            raise RuntimeError(
                "Ask completion provider is unavailable. Please install chatgpt-cli or configure VIRINDA_PROVIDER=echo or openai."
            )
        system_prompt, prompt = self._extract_prompts(req)
        model_name = (
            req.model if (req.model and req.model != "offline-demo") else self.default_model
        )
        target_provider = req.metadata.get("provider", self.ask_provider) or self.ask_provider

        candidate_providers = [target_provider]
        for fb in ("groq", "openrouter"):
            if fb not in candidate_providers:
                candidate_providers.append(fb)

        yielded_any = False
        last_exception = None

        for candidate in candidate_providers:
            if yielded_any:
                break
            try:
                candidate_model = model_name
                if candidate == "groq" and "/" not in candidate_model:
                    candidate_model = "groq/compound-mini"
                elif candidate == "openrouter" and candidate_model.startswith("groq/"):
                    candidate_model = "openrouter/free"

                backend: BaseProvider = get_provider(
                    provider_name=candidate,
                    model=candidate_model,
                    api_key=self.api_key,
                    headless=self.headless,
                )

                for event in backend.send_query(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    stream=True,
                    model=candidate_model,
                ):
                    if isinstance(event, ProviderEvent):
                        event_type, event_data = event.type, event.data
                    elif isinstance(event, (tuple, list)) and len(event) >= 2:
                        event_type, event_data = event[0], event[1]
                    else:
                        continue

                    if event_type == "token":
                        if event_data:
                            yielded_any = True
                            yield str(event_data)
                    elif event_type == "error":
                        if not yielded_any:
                            # Allow next candidate provider
                            raise RuntimeError(f"Ask provider '{candidate}' error: {event_data}")
                        else:
                            return
                    elif event_type == "complete" and not req.metadata.get("streamed"):
                        if not yielded_any and event_data:
                            yielded_any = True
                            yield str(event_data)

                if yielded_any:
                    return

            except (KeyboardInterrupt, GeneratorExit):
                return
            except Exception as exc:
                last_exception = exc
                if yielded_any:
                    return
                continue

        if not yielded_any and last_exception is not None:
            raise RuntimeError(
                f"VirindAI ask provider ({self.name}) failed across candidates: {last_exception}"
            ) from last_exception
