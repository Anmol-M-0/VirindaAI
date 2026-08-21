from __future__ import annotations

import re
from collections.abc import Iterable

_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n{2,}")


class StreamingSentenceTokenizer:
    """Small, stateful sentence buffer; never emits partial sentences by default."""

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, chunk: str) -> Iterable[str]:
        self._buffer += chunk
        while True:
            match = _BOUNDARY.search(self._buffer)
            if not match:
                break
            sentence = self._buffer[: match.end()].strip()
            self._buffer = self._buffer[match.end() :]
            if sentence:
                yield sentence

    def flush(self) -> Iterable[str]:
        text = self._buffer.strip()
        self._buffer = ""
        if text:
            yield text
