from __future__ import annotations

import hashlib
import logging
import math
import time
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    """Protocol for vector embedding generators."""

    def embed(self, text: str) -> list[float]: ...

    @property
    def is_semantic(self) -> bool: ...


class DeterministicLexicalEmbeddingProvider:
    """Zero-dependency hash-based pseudo-embedding provider for testing/fallback."""

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    @property
    def is_semantic(self) -> bool:
        return False

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            return [0.0] * self.dimensions
        vec = [0.0] * self.dimensions
        words = text.lower().split()
        for w in words:
            h = int(hashlib.md5(w.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimensions
            vec[idx] += 1.0
        # Normalize
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


class FastEmbedProvider:
    """Local offline ONNX embedding provider via FastEmbed (if installed)."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model_name
        self._model: Any = None
        self._initialized = False
        self._cache: dict[str, list[float]] = {}

    @property
    def is_semantic(self) -> bool:
        return True

    def _lazy_init(self) -> bool:
        if self._initialized:
            return self._model is not None
        self._initialized = True
        try:
            from fastembed import TextEmbedding  # type: ignore[import-untyped]

            self._model = TextEmbedding(model_name=self.model_name)
            logger.info("Initialized local FastEmbed semantic model: %s", self.model_name)
            return True
        except Exception as exc:
            logger.debug("FastEmbed unavailable; degrading to lexical fallback: %s", exc)
            self._model = None
            return False

    def embed(self, text: str) -> list[float]:
        if not text.strip():
            return []
        cache_key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self._lazy_init() or self._model is None:
            raise RuntimeError("FastEmbed model unavailable")

        embeddings = list(self._model.embed([text]))
        if not embeddings:
            return []
        vec = [float(v) for v in embeddings[0]]
        # Bounded cache
        if len(self._cache) > 512:
            self._cache.clear()
        self._cache[cache_key] = vec
        return vec


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


class HybridMemoryRetriever:
    """Blends BM25 lexical overlap and semantic embedding similarity."""

    def __init__(
        self,
        embedder: Optional[EmbeddingProvider] = None,
        weight_lexical: float = 0.40,
        weight_semantic: float = 0.30,
        weight_confidence: float = 0.15,
        weight_recency: float = 0.15,
    ) -> None:
        self.embedder = embedder or DeterminicalFallbackEmbeddingProvider()
        self.weight_lexical = weight_lexical
        self.weight_semantic = weight_semantic
        self.weight_confidence = weight_confidence
        self.weight_recency = weight_recency

    def rank(
        self,
        query: str,
        items: list[dict[str, Any]],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if not query.strip() or not items:
            return []

        query_tokens = {tok.lower() for tok in query.split() if len(tok) > 1}
        query_vec: Optional[list[float]] = None
        try:
            if self.embedder and self.embedder.is_semantic:
                query_vec = self.embedder.embed(query)
        except Exception:
            query_vec = None  # Fail open to BM25 only

        scored: list[tuple[float, dict[str, Any]]] = []
        now = time.time()

        for item in items:
            text = str(item.get("text") or item.get("content") or item.get("value") or "")
            item_tokens = {tok.lower() for tok in text.split() if len(tok) > 1}
            overlap = len(query_tokens & item_tokens) / max(1.0, len(query_tokens))

            sem_score = 0.0
            if query_vec and "embedding" in item and item["embedding"]:
                sem_score = cosine_similarity(query_vec, item["embedding"])

            conf = float(item.get("confidence", 1.0))
            created_at = float(item.get("created_at", now))
            age_days = max(0.0, (now - created_at) / 86400.0)
            recency = math.exp(-0.0231 * age_days)  # ~30 day half-life

            total_score = (
                (self.weight_lexical * overlap)
                + (self.weight_semantic * sem_score)
                + (self.weight_confidence * conf)
                + (self.weight_recency * recency)
            )

            scored.append((total_score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[:limit]]


# Deterministic alias
DeterminicalFallbackEmbeddingProvider = DeterministicLexicalEmbeddingProvider
