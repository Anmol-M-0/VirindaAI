from __future__ import annotations

import pytest

from virinda.infrastructure.persistence.embeddings import (
    DeterministicLexicalEmbeddingProvider,
    FastEmbedProvider,
    HybridMemoryRetriever,
    cosine_similarity,
)


def test_deterministic_lexical_embeddings():
    provider = DeterministicLexicalEmbeddingProvider(dimensions=64)
    assert provider.is_semantic is False

    vec1 = provider.embed("neovim editor configuration")
    vec2 = provider.embed("neovim editor configuration")
    vec3 = provider.embed("python programming language")

    assert len(vec1) == 64
    assert vec1 == vec2
    sim_same = cosine_similarity(vec1, vec2)
    sim_diff = cosine_similarity(vec1, vec3)

    assert sim_same == pytest.approx(1.0, abs=1e-4)
    assert sim_diff < 0.9


def test_hybrid_memory_retriever_ranking():
    provider = DeterministicLexicalEmbeddingProvider(dimensions=32)
    retriever = HybridMemoryRetriever(embedder=provider)

    items = [
        {
            "id": "1",
            "text": "My favorite editor is neovim.",
            "confidence": 1.0,
            "created_at": 1000.0,
        },
        {
            "id": "2",
            "text": "I like writing python scripts.",
            "confidence": 0.8,
            "created_at": 1000.0,
        },
        {
            "id": "3",
            "text": "The weather in Seattle is rainy.",
            "confidence": 0.5,
            "created_at": 1000.0,
        },
    ]

    results = retriever.rank("Which editor do I use in neovim?", items, limit=2)
    assert len(results) >= 1
    assert results[0]["id"] == "1"


def test_fastembed_graceful_degradation():
    fastembed = FastEmbedProvider(model_name="nonexistent_test_model")
    # FastEmbed may not be installed or model may fail to load
    # Must fail open (not crash)
    is_ready = fastembed._lazy_init()
    assert isinstance(is_ready, bool)
