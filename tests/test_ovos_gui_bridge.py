from marina.ovos import gui


class FakeMessage:
    def __init__(self, msg_type, data=None, context=None):
        self.msg_type = msg_type
        self.data = data or {}
        self.context = context or {}


class FakeBus:
    def __init__(self):
        self.handlers = {}
        self.emitted = []

    def on(self, topic, handler):
        self.handlers[topic] = handler

    def emit(self, message):
        self.emitted.append(message)


def test_gui_bridge_publishes_ovos_gui_values(monkeypatch):
    monkeypatch.setattr(gui, "Message", FakeMessage)
    bus = FakeBus()
    bridge = gui.OVOSGuiBridge(bus)
    bridge.publish_state({"status": "online", "listening": True})

    assert [m.msg_type for m in bus.emitted] == ["gui.value.set", "gui.value.set"]
    assert bus.emitted[0].data == {"key": "marina.status", "value": "online"}
    assert bus.emitted[0].context["session"]["session_id"] == "default"


def test_gui_bridge_parses_commands_from_bus(monkeypatch):
    monkeypatch.setattr(gui, "Message", FakeMessage)
    bus = FakeBus()
    bridge = gui.OVOSGuiBridge(bus)
    seen = []
    bridge.subscribe(seen.append)

    bus.handlers["marina.gui.command"](
        FakeMessage(
            "marina.gui.command",
            {"command": "routine_preview", "data": {"request_id": "r1", "params": {"id": "abc"}}},
            {"session": {"session_id": "s1"}},
        )
    )

    assert seen[0].command == "routine_preview"
    assert seen[0].data["request_id"] == "r1"
    assert seen[0].session_id == "s1"


def test_gui_bridge_publishes_request_response(monkeypatch):
    monkeypatch.setattr(gui, "Message", FakeMessage)
    bus = FakeBus()
    bridge = gui.OVOSGuiBridge(bus)
    bridge.publish_response("r2", {"ok": True}, session_id="s2")
    msg = bus.emitted[0]
    assert msg.msg_type == "marina.gui.response"
    assert msg.data == {"request_id": "r2", "ok": True, "result": {"ok": True}}
    assert msg.context["session"]["session_id"] == "s2"
