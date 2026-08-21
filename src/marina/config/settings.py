from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable runtime configuration assembled from environment variables.

    Settings intentionally contains only application/compatibility-runtime values.
    Production OVOS listener, wake-word, VAD, STT, TTS, and audio routing are
    configured through OVOS rather than duplicated here.
    """
    data_dir: Path
    provider: str
    model: str
    openai_base_url: str | None
    openai_api_key: str | None
    openai_model: str | None
    audio_mode: str
    wake_word: str
    wake_threshold: float
    end_silence_ms: int
    follow_up_window_ms: int
    job_broker: str
    nats_url: str | None
    nats_creds: str | None
    nats_stream: str
    nats_subject_prefix: str
    nats_durable: str
    nats_ack_wait_seconds: float
    nats_max_deliver: int
    nats_max_ack_pending: int

    def with_data_dir(self, data_dir: Path) -> "Settings":
        return Settings(
            data_dir=Path(data_dir).expanduser().resolve(),
            provider=self.provider,
            model=self.model,
            openai_base_url=self.openai_base_url,
            openai_api_key=self.openai_api_key,
            openai_model=self.openai_model,
            audio_mode=self.audio_mode,
            wake_word=self.wake_word,
            wake_threshold=self.wake_threshold,
            end_silence_ms=self.end_silence_ms,
            follow_up_window_ms=self.follow_up_window_ms,
            job_broker=self.job_broker,
            nats_url=self.nats_url,
            nats_creds=self.nats_creds,
            nats_stream=self.nats_stream,
            nats_subject_prefix=self.nats_subject_prefix,
            nats_durable=self.nats_durable,
            nats_ack_wait_seconds=self.nats_ack_wait_seconds,
            nats_max_deliver=self.nats_max_deliver,
            nats_max_ack_pending=self.nats_max_ack_pending,
        )

    def validate(self) -> None:
        if not self.provider.strip():
            raise ValueError("MARINA_PROVIDER cannot be empty")
        if not self.model.strip():
            raise ValueError("MARINA_MODEL cannot be empty")
        if self.audio_mode not in {"wake_word", "push_to_talk", "toggle_listen", "follow_up"}:
            raise ValueError("MARINA_AUDIO_MODE must be wake_word, push_to_talk, toggle_listen, or follow_up")
        if not 0.0 <= self.wake_threshold <= 1.0:
            raise ValueError("MARINA_WAKE_THRESHOLD must be between 0 and 1")
        if self.end_silence_ms < 100:
            raise ValueError("MARINA_END_SILENCE_MS must be at least 100")
        if self.follow_up_window_ms < 0:
            raise ValueError("MARINA_FOLLOW_UP_WINDOW_MS cannot be negative")
        if self.job_broker not in {"inprocess", "nats"}:
            raise ValueError("MARINA_JOB_BROKER must be inprocess or nats")
        if self.job_broker == "nats" and not self.nats_url:
            raise ValueError("MARINA_NATS_URL is required when MARINA_JOB_BROKER=nats")
        if self.nats_ack_wait_seconds < 5:
            raise ValueError("MARINA_NATS_ACK_WAIT_SECONDS must be at least 5")
        if self.nats_max_deliver < 1:
            raise ValueError("MARINA_NATS_MAX_DELIVER must be at least 1")
        if self.nats_max_ack_pending < 1:
            raise ValueError("MARINA_NATS_MAX_ACK_PENDING must be at least 1")
        if self.provider == "openai":
            if not self.openai_base_url:
                raise ValueError("MARINA_OPENAI_BASE_URL is required for the openai provider")
            if not self.openai_api_key:
                raise ValueError("MARINA_OPENAI_API_KEY is required for the openai provider")

    @classmethod
    def from_env(cls) -> "Settings":
        override = os.getenv("MARINA_DATA_DIR")
        data_dir = Path(override).expanduser().resolve() if override else Path.home() / ".local" / "share" / "marina-ai"
        return cls(
            data_dir=data_dir,
            provider=os.getenv("MARINA_PROVIDER", "echo"),
            model=os.getenv("MARINA_MODEL", "offline-demo"),
            openai_base_url=os.getenv("MARINA_OPENAI_BASE_URL"),
            openai_api_key=os.getenv("MARINA_OPENAI_API_KEY"),
            openai_model=os.getenv("MARINA_OPENAI_MODEL"),
            audio_mode=os.getenv("MARINA_AUDIO_MODE", "wake_word"),
            wake_word=os.getenv("MARINA_WAKE_WORD", "hey marina"),
            wake_threshold=float(os.getenv("MARINA_WAKE_THRESHOLD", "0.5")),
            end_silence_ms=int(os.getenv("MARINA_END_SILENCE_MS", "750")),
            follow_up_window_ms=int(os.getenv("MARINA_FOLLOW_UP_WINDOW_MS", "8000")),
            job_broker=os.getenv("MARINA_JOB_BROKER", "inprocess"),
            nats_url=os.getenv("MARINA_NATS_URL"),
            nats_creds=os.getenv("MARINA_NATS_CREDS"),
            nats_stream=os.getenv("MARINA_NATS_STREAM", "marina_jobs"),
            nats_subject_prefix=os.getenv("MARINA_NATS_SUBJECT_PREFIX", "marina.jobs"),
            nats_durable=os.getenv("MARINA_NATS_DURABLE", "marina-workers"),
            nats_ack_wait_seconds=float(os.getenv("MARINA_NATS_ACK_WAIT_SECONDS", "120")),
            nats_max_deliver=int(os.getenv("MARINA_NATS_MAX_DELIVER", "5")),
            nats_max_ack_pending=int(os.getenv("MARINA_NATS_MAX_ACK_PENDING", "32")),
        )
