from __future__ import annotations

from collections import deque
from threading import Lock

from marina.domain.events import AssistantEvent, EventSink


class InMemoryEventBus(EventSink):
    """Thread-safe bounded event bus for local clients and tests."""

    def __init__(self, max_events: int = 2048) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self._queue: deque[AssistantEvent] = deque(maxlen=max_events)
        self._subscribers: list[EventSink] = []
        self._lock = Lock()
        self.dropped = 0
        self.subscriber_errors = 0

    def subscribe(self, sink: EventSink) -> None:
        with self._lock:
            if sink not in self._subscribers:
                self._subscribers.append(sink)

    def unsubscribe(self, sink: EventSink) -> None:
        with self._lock:
            try:
                self._subscribers.remove(sink)
            except ValueError:
                return

    def publish(self, event: AssistantEvent) -> None:
        with self._lock:
            if len(self._queue) == self._queue.maxlen:
                self.dropped += 1
            self._queue.append(event)
            subscribers = tuple(self._subscribers)
        for sink in subscribers:
            try:
                sink.publish(event)
            except Exception:
                # Presentation clients are untrusted consumers: their failure must
                # not abort the application operation that produced the event.
                with self._lock:
                    self.subscriber_errors += 1

    def drain(self) -> list[AssistantEvent]:
        with self._lock:
            events = list(self._queue)
            self._queue.clear()
        return events
