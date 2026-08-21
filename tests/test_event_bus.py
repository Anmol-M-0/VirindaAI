from virinda.core.events import InMemoryEventBus
from virinda.domain.events import LifecycleChanged


class BrokenSink:
    def publish(self, event):
        raise RuntimeError("client disconnected")


def test_event_bus_isolates_broken_subscribers():
    bus = InMemoryEventBus(max_events=2)
    sink = BrokenSink()
    bus.subscribe(sink)
    bus.subscribe(sink)
    bus.publish(LifecycleChanged(generation_id=1, sequence=1, state="idle"))
    assert bus.subscriber_errors == 1
    assert len(bus.drain()) == 1
    bus.unsubscribe(sink)
    bus.publish(LifecycleChanged(generation_id=1, sequence=2, state="idle"))
    assert bus.subscriber_errors == 1
