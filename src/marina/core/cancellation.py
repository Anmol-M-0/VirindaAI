from __future__ import annotations

from threading import Lock


class GenerationController:
    """Monotonic generation source used to make late worker results harmless."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._generation = 0

    @property
    def current(self) -> int:
        with self._lock:
            return self._generation

    def start(self) -> int:
        with self._lock:
            self._generation += 1
            return self._generation

    def invalidate(self) -> int:
        with self._lock:
            self._generation += 1
            return self._generation

    def is_current(self, generation_id: int) -> bool:
        with self._lock:
            return generation_id == self._generation
