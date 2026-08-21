from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from queue import Empty, Full, Queue
from typing import Optional

from virinda.infrastructure.audio.speech import NativeTTS

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TTSItem:
    generation: int
    sequence: int
    text: str


class StreamingTTSWorker:
    """Bounded, background streaming TTS pipeline with monotonic generation invalidation.

    Synthesizes and speaks sentences concurrently while the LLM continues generating tokens.
    """

    def __init__(self, tts: Optional[NativeTTS] = None, queue_size: int = 4) -> None:
        self._tts = tts or NativeTTS()
        self._queue: Queue[Optional[TTSItem]] = Queue(maxsize=queue_size)
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._pending_count = 0
        self._sequence_counter = 0
        self._active_generation = 0
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="Virinda-StreamingTTS"
        )
        self._worker_thread.start()

    def set_generation(self, generation: int) -> None:
        with self._lock:
            if generation != self._active_generation:
                self._active_generation = generation
                self._cancel_locked()

    def feed(self, generation: int, text: str) -> bool:
        """Feed a completed sentence to the TTS queue. Discards if generation is stale."""
        clean_text = text.strip()
        if not clean_text:
            return False

        with self._lock:
            if generation != self._active_generation:
                return False
            self._sequence_counter += 1
            item = TTSItem(generation=generation, sequence=self._sequence_counter, text=clean_text)
            self._pending_count += 1

        try:
            self._queue.put(item, timeout=5.0)
            return True
        except Full:
            logger.warning("Streaming TTS queue full; dropping sentence '%s'", clean_text)
            with self._lock:
                self._pending_count = max(0, self._pending_count - 1)
                self._cond.notify_all()
            return False

    def flush_and_wait(self, generation: int, timeout: float = 15.0) -> bool:
        """Wait until all queued sentences for this generation have finished playing."""
        with self._lock:
            if generation != self._active_generation:
                return True
            end_time = threading.Event().wait  # placeholder for timing
            import time

            deadline = time.monotonic() + timeout
            while self._pending_count > 0 and self._active_generation == generation:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    logger.warning(
                        "Streaming TTS flush timed out with %d pending items", self._pending_count
                    )
                    return False
                self._cond.wait(timeout=remaining)
            return True

    def cancel(self, generation: Optional[int] = None) -> None:
        """Cancel active playback and purge queued sentences."""
        with self._lock:
            if generation is None or generation == self._active_generation:
                self._cancel_locked()

    def _cancel_locked(self) -> None:
        """Internal cancel holding self._lock."""
        # Purge items from queue
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except Empty:
                break
        self._pending_count = 0
        self._tts.stop()
        self._cond.notify_all()

    def _worker_loop(self) -> None:
        while self._running:
            try:
                item = self._queue.get(timeout=0.2)
            except Empty:
                continue

            if item is None or not self._running:
                break

            try:
                with self._lock:
                    if item.generation != self._active_generation:
                        continue

                # Speak sentence
                self._tts.speak(item.text, block=True)

            except Exception as exc:
                logger.exception("Error speaking TTS item '%s': %s", item.text, exc)
            finally:
                self._queue.task_done()
                with self._lock:
                    self._pending_count = max(0, self._pending_count - 1)
                    self._cond.notify_all()

    def close(self) -> None:
        self._running = False
        self.cancel()
        try:
            self._queue.put_nowait(None)
        except Full:
            pass
        self._worker_thread.join(timeout=1.0)
