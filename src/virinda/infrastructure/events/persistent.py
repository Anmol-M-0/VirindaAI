from __future__ import annotations

from virinda.domain.events import AssistantEvent, EventSink


class PersistentEventSink(EventSink):
    """Persist semantic events while also forwarding them to the live event bus."""

    def __init__(self, *, session_id_supplier, store, downstream: EventSink) -> None:
        self._session_id_supplier = session_id_supplier
        self._store = store
        self._downstream = downstream

    def publish(self, event: AssistantEvent) -> None:
        self._store.append_event(self._session_id_supplier(), event)
        self._downstream.publish(event)
