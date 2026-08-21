from pathlib import Path
from urllib.request import Request, urlopen
import json

from marina.application.service import AssistantService
from marina.desktop import OverlayServer
from marina.core.events import InMemoryEventBus
from marina.infrastructure.persistence.sqlite import SQLiteConversationStore
from marina.infrastructure.providers.echo import EchoProvider
from marina.infrastructure.providers.router import StaticProviderRouter


def build_service(tmp_path: Path):
    return AssistantService(
        router=StaticProviderRouter({"echo": EchoProvider()}, default="echo"),
        store=SQLiteConversationStore(tmp_path / "overlay.sqlite3"),
        event_bus=InMemoryEventBus(),
    )


def post(base, path, payload):
    req = Request(base + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=3) as r:
        return json.loads(r.read())


def get(base, path):
    with urlopen(base + path, timeout=3) as r:
        return json.loads(r.read())


def test_overlay_serves_routine_editor_and_lifecycle_api(tmp_path):
    service = build_service(tmp_path)
    overlay = OverlayServer(service, port=0)
    host, port = overlay.start()
    base = f"http://{host}:{port}"
    try:
        with urlopen(base + "/", timeout=3) as r:
            html = r.read().decode()
        assert "Routine editor" in html
        assert "Preview" in html

        created = post(base, "/api/routine-save", {
            "name": "Morning",
            "trigger": "event:morning",
            "action": "notify:Marina|Good morning",
        })
        routine_id = created["id"]
        routines = get(base, "/api/routines")
        assert routines[0]["id"] == routine_id

        preview = post(base, "/api/routine-preview", {"id": routine_id})
        assert preview["routine"]["name"] == "Morning"
        assert preview["will_execute"] is True

        disabled = post(base, "/api/routine-disable", {"id": routine_id})
        assert disabled["ok"] is True
        deleted = post(base, "/api/routine-delete", {"id": routine_id})
        assert deleted["ok"] is True
    finally:
        overlay.stop()
        service.close()


def test_overlay_run_now_executes_selected_routine(tmp_path):
    service = build_service(tmp_path)
    overlay = OverlayServer(service, port=0)
    host, port = overlay.start()
    base = f"http://{host}:{port}"
    try:
        created = post(base, "/api/routine-save", {
            "name": "Immediate",
            "trigger": "event:manual",
            "action": "notify:Marina|Run now",
        })
        result = post(base, "/api/routine-run-now", {"id": created["id"]})
        assert result["status"] == "succeeded"
        assert service.notification_summary() == "Marina: Run now"
    finally:
        overlay.stop()
        service.close()
