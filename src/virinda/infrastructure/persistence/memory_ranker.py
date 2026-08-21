from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

TOKEN_SPLIT_REGEX = re.compile(r"\W+")
HALF_LIFE_SECONDS = 30 * 86400.0  # 30 days
LAMBDA_DECAY = math.log(2.0) / HALF_LIFE_SECONDS


@dataclass(slots=True)
class RankedMemory:
    item_type: str  # "fact" | "note"
    id: str
    key: Optional[str]
    content: str
    confidence: float
    pinned: bool
    score: float
    created_at: float


class CognitiveMemoryRanker:
    """Hybrid lexical + confidence + recency + pinned boost memory ranking engine."""

    def __init__(
        self,
        weight_lexical: float = 0.40,
        weight_confidence: float = 0.30,
        weight_recency: float = 0.15,
        weight_pinned: float = 0.15,
    ) -> None:
        self.weight_lexical = weight_lexical
        self.weight_confidence = weight_confidence
        self.weight_recency = weight_recency
        self.weight_pinned = weight_pinned

    def tokenize(self, text: str) -> set[str]:
        return {tok.lower() for tok in TOKEN_SPLIT_REGEX.split(text) if len(tok) > 1}

    def score(
        self,
        query_tokens: set[str],
        content: str,
        *,
        confidence: float = 1.0,
        created_at: float = 0.0,
        pinned: bool = False,
    ) -> float:
        if not query_tokens:
            return 0.0

        content_tokens = self.tokenize(content)
        if not content_tokens:
            return 0.0

        # 1. Lexical overlap ratio (Jaccard-like coverage of query)
        overlap = len(query_tokens & content_tokens) / float(len(query_tokens))
        if overlap == 0.0:
            # If pinned, give minimal base score so it surfaces if relevant
            if not pinned:
                return 0.0

        # 2. Recency exponential decay
        now = time.time()
        age_seconds = max(0.0, now - created_at) if created_at > 0 else 0.0
        recency = math.exp(-LAMBDA_DECAY * age_seconds)

        # 3. Pinned boost (1.0 if pinned, else 0.0)
        pinned_val = 1.0 if pinned else 0.0

        total_score = (
            (self.weight_lexical * overlap)
            + (self.weight_confidence * min(1.0, max(0.0, confidence)))
            + (self.weight_recency * recency)
            + (self.weight_pinned * pinned_val)
        )
        return total_score

    def rank(
        self,
        query: str,
        facts: list[Any],
        notes: list[Any],
        limit: int = 6,
    ) -> list[RankedMemory]:
        q_tokens = self.tokenize(query)
        if not q_tokens:
            return []

        ranked: list[RankedMemory] = []

        # Score facts
        for f in facts:
            f_key = getattr(f, "key", "")
            f_val = getattr(f, "value", "")
            f_content = f"{f_key}: {f_val}"
            f_conf = getattr(f, "confidence", 1.0)
            f_pinned = getattr(f, "pinned", False)
            f_created = getattr(f, "updated_at", getattr(f, "created_at", 0.0))

            s = self.score(
                q_tokens,
                f_content,
                confidence=f_conf,
                created_at=f_created,
                pinned=f_pinned,
            )
            if s > 0.0:
                ranked.append(
                    RankedMemory(
                        item_type="fact",
                        id=getattr(f, "id", f_key),
                        key=f_key,
                        content=f_content,
                        confidence=f_conf,
                        pinned=f_pinned,
                        score=s,
                        created_at=f_created,
                    )
                )

        # Score notes
        for n in notes:
            n_text = getattr(n, "text", "")
            n_id = getattr(n, "id", "")
            n_created = getattr(n, "created_at", 0.0)
            s = self.score(
                q_tokens,
                n_text,
                confidence=0.8,
                created_at=n_created,
                pinned=False,
            )
            if s > 0.0:
                ranked.append(
                    RankedMemory(
                        item_type="note",
                        id=n_id,
                        key=None,
                        content=n_text,
                        confidence=0.8,
                        pinned=False,
                        score=s,
                        created_at=n_created,
                    )
                )

        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:limit]

    def build_prompt_context(self, ranked: list[RankedMemory]) -> str:
        """Format ranked memories into safe, isolated context block."""
        if not ranked:
            return ""

        lines = ["<retrieved_memory>"]
        for r in ranked:
            tag = "PINNED FACT" if r.pinned else r.item_type.upper()
            lines.append(f"• [{tag}] {r.content}")
        lines.append("</retrieved_memory>")
        return "\n".join(lines)
