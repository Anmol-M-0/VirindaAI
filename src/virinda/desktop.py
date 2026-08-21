from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from virinda.features import OVERLAY_HTML


class OverlayServer:
    """Optional loopback developer/diagnostics UI.

    Production OVOS desktop interaction must use ``ovos-gui``/MessageBus; this
    server exists for debugging Virinda without an OVOS GUI client.
    """

    def __init__(self, service, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.service = service
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> tuple[str, int]:
        service = self.service

        class Handler(BaseHTTPRequestHandler):
            def _json(self, status: int, payload: Any) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path == "/":
                    body = OVERLAY_HTML.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/api/status":
                    self._json(200, service.health())
                    return
                if self.path == "/api/context":
                    self._json(200, service.context())
                    return
                if self.path == "/api/live-context":
                    self._json(200, service.live_session_context())
                    return
                if self.path == "/api/capabilities":
                    self._json(200, service.capability_snapshot())
                    return
                if self.path == "/api/memory":
                    self._json(200, service.memory_snapshot())
                    return
                if self.path == "/api/notifications":
                    self._json(200, service.notifications_snapshot())
                    return
                if self.path == "/api/routines":
                    self._json(200, service.routines_snapshot())
                    return
                if self.path == "/api/routine-runs":
                    self._json(200, service.routine_runs(None, 100))
                    return
                if self.path == "/api/routines":
                    self._json(200, service.routines_snapshot())
                    return
                if self.path == "/api/routine-runs":
                    from urllib.parse import parse_qs, urlparse

                    query = parse_qs(urlparse(self.path).query)
                    routine_id = query.get("routine_id", [None])[0]
                    self._json(200, service.routine_runs(routine_id, 100))
                    return
                self._json(404, {"error": "not found"})

            def do_POST(self) -> None:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length > 256_000:
                        self._json(413, {"error": "request too large"})
                        return
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    if self.path == "/api/context":
                        service.set_context_mode(payload.get("mode"))
                        self._json(200, service.context())
                        return
                    if self.path == "/api/ask":
                        self._json(200, {"result": service.ask(str(payload.get("text", "")))})
                        return
                    if self.path == "/api/cancel":
                        service.cancel(str(payload.get("reason", "user")))
                        self._json(200, {"ok": True})
                        return
                    if self.path == "/api/routine-save":
                        self._json(
                            200,
                            service.save_routine(
                                str(payload.get("name", "")),
                                str(payload.get("trigger", "")),
                                str(payload.get("action", "")),
                                retry_limit=int(payload.get("retry_limit", 0)),
                                retry_backoff_seconds=float(
                                    payload.get("retry_backoff_seconds", 2.0)
                                ),
                                require_approval=bool(payload.get("require_approval", False)),
                                allow_conflict=bool(payload.get("allow_conflict", False)),
                            ),
                        )
                        return
                    if self.path == "/api/routine-update":
                        changes = payload.get("changes", {})
                        if not isinstance(changes, dict):
                            self._json(400, {"error": "changes must be an object"})
                            return
                        self._json(
                            200, service.update_routine(str(payload.get("id", "")), **changes)
                        )
                        return
                    if self.path == "/api/routine-preview":
                        ctx = payload.get("trigger_context", {})
                        if not isinstance(ctx, dict):
                            self._json(400, {"error": "trigger_context must be an object"})
                            return
                        self._json(
                            200,
                            service.routine_preview(
                                str(payload.get("id", "")), trigger_context=ctx
                            ),
                        )
                        return
                    if self.path == "/api/routine-disable":
                        self._json(200, {"ok": service.disable_routine(str(payload.get("id", "")))})
                        return
                    if self.path == "/api/routine-delete":
                        self._json(200, {"ok": service.delete_routine(str(payload.get("id", "")))})
                        return
                    if self.path == "/api/routine-run":
                        self._json(200, service.run_due_routines())
                        return
                    if self.path == "/api/routine-run-now":
                        self._json(
                            200, {"status": service.run_routine_now(str(payload.get("id", "")))}
                        )
                        return
                    if self.path == "/api/routine-save":
                        self._json(
                            200,
                            service.save_routine(
                                str(payload.get("name", "")),
                                str(payload.get("trigger", "")),
                                str(payload.get("action", "")),
                                retry_limit=int(payload.get("retry_limit", 0)),
                                retry_backoff_seconds=float(
                                    payload.get("retry_backoff_seconds", 2.0)
                                ),
                                require_approval=bool(payload.get("require_approval", False)),
                                allow_conflict=bool(payload.get("allow_conflict", False)),
                            ),
                        )
                        return
                    if self.path == "/api/routine-update":
                        changes = payload.get("changes", {})
                        if not isinstance(changes, dict):
                            self._json(400, {"error": "changes must be an object"})
                            return
                        self._json(
                            200, service.update_routine(str(payload.get("id", "")), **changes)
                        )
                        return
                    if self.path == "/api/routine-preview":
                        ctx = payload.get("trigger_context", {})
                        if not isinstance(ctx, dict):
                            self._json(400, {"error": "trigger_context must be an object"})
                            return
                        self._json(
                            200,
                            service.routine_preview(
                                str(payload.get("id", "")), trigger_context=ctx
                            ),
                        )
                        return
                    if self.path == "/api/routine-disable":
                        self._json(200, {"ok": service.disable_routine(str(payload.get("id", "")))})
                        return
                    if self.path == "/api/routine-delete":
                        self._json(200, {"ok": service.delete_routine(str(payload.get("id", "")))})
                        return
                    if self.path == "/api/routine-run":
                        self._json(200, service.run_due_routines())
                        return
                    if self.path == "/api/routine-run-now":
                        self._json(
                            200, {"status": service.run_routine_now(str(payload.get("id", "")))}
                        )
                        return
                    if self.path == "/api/routine-approve":
                        self._json(
                            200,
                            {"status": service.approve_routine_run(str(payload.get("run_id", "")))},
                        )
                        return
                    self._json(404, {"error": "not found"})
                except Exception as exc:
                    self._json(400, {"error": str(exc)})

            def log_message(self, *_args: Any) -> None:
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="virinda-overlay", daemon=True
        )
        self._thread.start()
        return self.host, self._server.server_port

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
