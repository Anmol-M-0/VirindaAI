from __future__ import annotations

from virinda.application.service import AssistantService
from virinda.config.settings import Settings
from virinda.core.events import InMemoryEventBus
from virinda.domain.audio import AudioInteractionMode, AudioPolicy
from virinda.domain.contracts import CompletionProvider
from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore
from virinda.infrastructure.providers.ask_adapter import AskCompletionProvider
from virinda.infrastructure.providers.echo import EchoProvider
from virinda.infrastructure.providers.openai_compatible import OpenAICompatibleProvider
from virinda.infrastructure.providers.router import StaticProviderRouter


def build_service(settings: Settings | None = None) -> AssistantService:
    settings = settings or Settings.from_env()
    settings.validate()
    bus = InMemoryEventBus()
    store = SQLiteConversationStore(settings.data_dir / "virinda.sqlite3")
    providers: dict[str, CompletionProvider] = {
        "echo": EchoProvider(),
        "ask": AskCompletionProvider(
            name="ask", default_model=settings.model or "meta/llama-3.3-70b-instruct"
        ),
        "nim": AskCompletionProvider(
            name="nim", default_model="meta/llama-3.3-70b-instruct", ask_provider="nim"
        ),
        "groq": AskCompletionProvider(
            name="groq", default_model="groq/compound-mini", ask_provider="groq"
        ),
        "openrouter": AskCompletionProvider(
            name="openrouter", default_model="openrouter/free", ask_provider="openrouter"
        ),
    }
    if settings.openai_base_url and settings.openai_api_key:
        providers["openai"] = OpenAICompatibleProvider(
            name="openai",
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            default_model=settings.openai_model or settings.model,
        )
    router = StaticProviderRouter(providers, default=settings.provider)
    # Keep policy construction here so desktop/audio adapters can consume one normalized runtime config.
    _ = AudioPolicy(
        wake_word=settings.wake_word,
        wake_threshold=settings.wake_threshold,
        end_silence_ms=settings.end_silence_ms,
        follow_up_window_ms=settings.follow_up_window_ms,
    )
    _ = AudioInteractionMode(settings.audio_mode)
    service = AssistantService(
        router=router,
        store=store,
        event_bus=bus,
        default_provider=settings.provider,
        default_model=settings.model,
    )
    return service
