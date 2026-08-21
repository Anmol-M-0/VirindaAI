from __future__ import annotations

import json
import os
import socket
import socketserver
import stat
import threading
from pathlib import Path
from queue import Queue
from typing import Any

from marina.application.service import AssistantService


class IPCProtocolError(ValueError):
    """Raised when a local RPC request is malformed or unsupported."""


class _UnixRPCHandler(socketserver.StreamRequestHandler):
    server: "LocalRPCServer"

    def handle(self) -> None:
        for raw_line in self.rfile:
            if len(raw_line) > self.server.max_request_bytes:
                self._send(None, False, error="request too large")
                return
            try:
                request = json.loads(raw_line.decode("utf-8"))
                if isinstance(request, dict) and request.get("method") == "ask_stream":
                    self.server.stream_ask(request, self.wfile)
                    continue
                response = self.server.dispatch(request)
            except (IPCProtocolError, ValueError) as exc:
                response = {"id": None, "ok": False, "error": str(exc)}
            except Exception as exc:  # defensive boundary: never crash the socket worker
                response = {"id": None, "ok": False, "error": f"internal error: {exc}"}
            self.wfile.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

    def _send(self, request_id: Any, ok: bool, *, error: str | None = None) -> None:
        payload: dict[str, Any] = {"id": request_id, "ok": ok}
        if error:
            payload["error"] = error
        self.wfile.write((json.dumps(payload) + "\n").encode("utf-8"))
        self.wfile.flush()


class _ThreadingUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


class LocalRPCServer:
    """Small newline-delimited JSON RPC server on a local Unix domain socket.

    The protocol is intentionally boring: one request per line and one response per line.
    The socket is local-only and created with mode 0600, making it suitable as the stable
    control boundary for a GTK/overlay client without adding a network framework.
    """

    max_request_bytes = 256 * 1024

    def __init__(self, service: AssistantService, socket_path: Path) -> None:
        self.service = service
        self.socket_path = Path(socket_path).expanduser().resolve()
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._server: _ThreadingUnixServer | None = None
        self._started = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            if self.socket_path.exists():
                if not self._is_socket(self.socket_path):
                    raise RuntimeError(f"IPC path exists and is not a socket: {self.socket_path}")
                self.socket_path.unlink()
            previous_umask = os.umask(0o077)
            try:
                self._server = _ThreadingUnixServer(str(self.socket_path), _UnixRPCHandler)
                self._server.max_request_bytes = self.max_request_bytes
                self._server.dispatch = self.dispatch
                self._server.stream_ask = self.stream_ask
            finally:
                os.umask(previous_umask)
            os.chmod(self.socket_path, 0o600)
            self._started = True

    def serve_forever(self) -> None:
        if not self._started or self._server is None:
            self.start()
        assert self._server is not None
        self._server.serve_forever(poll_interval=0.2)

    def shutdown(self) -> None:
        with self._lock:
            server = self._server
        if server is not None:
            server.shutdown()
            server.server_close()
        with self._lock:
            self._server = None
            self._started = False
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass

    def dispatch(self, request: Any) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise IPCProtocolError("request must be a JSON object")
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})
        if not isinstance(method, str) or not method:
            raise IPCProtocolError("method is required")
        if not isinstance(params, dict):
            raise IPCProtocolError("params must be an object")

        result = self._call(method, params)
        return {"id": request_id, "ok": True, "result": result}

    def stream_ask(self, request: Any, writer) -> None:
        if not isinstance(request, dict):
            raise IPCProtocolError("request must be a JSON object")
        request_id = request.get("id")
        params = request.get("params", {})
        if not isinstance(params, dict):
            raise IPCProtocolError("params must be an object")
        text = _required_str(params, "text")
        provider = _optional_str(params, "provider")
        model = _optional_str(params, "model")
        queue: Queue[Any] = Queue()
        sentinel = object()

        class Sink:
            def publish(self, event) -> None:
                try:
                    queue.put_nowait(event)
                except Exception:
                    pass

        sink = Sink()
        self.service.events.subscribe(sink)
        result: dict[str, Any] = {}

        def run() -> None:
            try:
                result["value"] = self.service.ask(text, provider=provider, model=model)
            except Exception as exc:
                result["error"] = str(exc)
            finally:
                queue.put(sentinel)

        worker = threading.Thread(target=run, name="marina-rpc-stream", daemon=True)
        worker.start()
        try:
            while True:
                item = queue.get()
                if item is sentinel:
                    break
                payload = {"id": request_id, "ok": True, "type": "event", "event": {
                    "type": type(item).__name__, **item.to_payload()
                }}
                writer.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
                writer.flush()
            worker.join(timeout=1)
            if "error" in result:
                final = {"id": request_id, "ok": False, "type": "complete", "error": result["error"]}
            else:
                final = {"id": request_id, "ok": True, "type": "complete", "result": result.get("value", "")}
            writer.write((json.dumps(final, ensure_ascii=False) + "\n").encode("utf-8"))
            writer.flush()
        finally:
            self.service.events.unsubscribe(sink)

    def _call(self, method: str, params: dict[str, Any]) -> Any:
        if method == "status":
            return self.service.health()
        if method == "providers":
            return list(self.service.router.available())
        if method == "set_provider":
            return self.service.select_provider(_required_str(params, "provider"), _optional_str(params, "model"))
        if method == "capabilities":
            return self.service.capability_snapshot()
        if method == "context":
            return self.service.context()
        if method == "live_context":
            return self.service.live_session_context()
        if method == "ovos_utterance":
            return self.service.observe_ovos_utterance(
                _required_str(params, "text"),
                speaker=_optional_str(params, "speaker"),
                persist=bool(params.get("persist", False)),
            )
        if method == "ovos_speak":
            return self.service.observe_ovos_speak(_required_str(params, "text"))
        if method == "ovos_listening":
            return self.service.observe_ovos_listening(bool(params.get("active", False)))
        if method == "ovos_speech_complete":
            return self.service.observe_ovos_speech_complete()
        if method == "set_context":
            self.service.set_context_mode(_required_str(params, "mode"))
            return self.service.context()
        if method == "ask":
            return self.service.ask(
                _required_str(params, "text"),
                provider=_optional_str(params, "provider"),
                model=_optional_str(params, "model"),
            )
        if method == "cancel":
            self.service.cancel(_optional_str(params, "reason") or "user")
            return None
        if method == "clear":
            self.service.clear()
            return None
        if method == "history":
            return [
                {"role": message.role, "content": message.content, "created_at": message.created_at}
                for message in self.service.store.load_messages(self.service.snapshot().session_id)
            ]
        if method == "events":
            limit = int(params.get("limit", 100))
            return [
                {"type": type(event).__name__, **event.to_payload()}
                for event in self.service.store.load_events(self.service.snapshot().session_id, limit)
            ]
        if method == "sessions":
            return self.service.store.list_sessions()
        if method == "backup":
            return str(self.service.store.backup(Path(_required_str(params, "destination"))))
        if method == "profile":
            return self.service.profile_snapshot()
        if method == "profile_update":
            changes = params.get("changes", {})
            if not isinstance(changes, dict):
                raise IPCProtocolError("changes must be an object")
            return self.service.update_profile(**changes)
        if method == "profile_clear":
            self.service.clear_profile(); return None
        if method == "memory":
            return self.service.memory_snapshot()
        if method == "memory_search":
            return self.service.memory_search(_required_str(params, "query"), int(params.get("limit", 10)))
        if method == "memory_fact":
            return self.service.memory_fact(_required_str(params, "key"), _required_str(params, "value"), confidence=float(params.get("confidence", 1.0)), sensitivity=str(params.get("sensitivity", "normal")))
        if method == "memory_note":
            return self.service.memory_add_note(_required_str(params, "text"), source=str(params.get("source", "conversation")), sensitivity=str(params.get("sensitivity", "normal")))
        if method == "memory_clear":
            self.service.memory_clear(); return None
        if method == "alerts":
            return self.service.alerts_snapshot()
        if method == "schedule_alert":
            return self.service.schedule_alert(_required_str(params, "kind"), _required_str(params, "title"), float(params["due_at"]), float(params["recurring_seconds"]) if params.get("recurring_seconds") is not None else None)
        if method == "cancel_alert":
            return self.service.cancel_alert(_required_str(params, "id"))
        if method == "notifications":
            return self.service.notifications_snapshot(bool(params.get("unread_only", False)))
        if method == "notification_read":
            return self.service.mark_notification_read(_required_str(params, "id"))
        if method == "routines":
            return self.service.routines_snapshot()
        if method == "routine_save":
            return self.service.save_routine(
                _required_str(params, "name"),
                _required_str(params, "trigger"),
                _required_str(params, "action"),
                retry_limit=int(params.get("retry_limit", 0)),
                retry_backoff_seconds=float(params.get("retry_backoff_seconds", 2.0)),
                require_approval=bool(params.get("require_approval", False)),
                allow_conflict=bool(params.get("allow_conflict", False)),
            )
        if method == "routine_update":
            changes = params.get("changes", {})
            if not isinstance(changes, dict): raise IPCProtocolError("changes must be an object")
            return self.service.update_routine(_required_str(params, "id"), **changes)
        if method == "routine_disable":
            return self.service.disable_routine(_required_str(params, "id"))
        if method == "routine_schedule":
            return self.service.schedule_routine(_required_str(params, "name"), float(params["due_at"]), _required_str(params, "action"))
        if method == "routine_run_due":
            return self.service.run_due_routines(float(params["now"]) if "now" in params else None)
        if method == "routine_run_now":
            return self.service.run_routine_now(_required_str(params, "id"))
        if method == "routine_event":
            payload = params.get("payload", {})
            if not isinstance(payload, dict): raise IPCProtocolError("payload must be an object")
            return self.service.run_routine_event(_required_str(params, "event"), payload)
        if method == "routine_preview":
            payload = params.get("trigger_context", {})
            if not isinstance(payload, dict):
                raise IPCProtocolError("trigger_context must be an object")
            return self.service.routine_preview(_required_str(params, "id"), trigger_context=payload)
        if method == "routine_runs":
            return self.service.routine_runs(_optional_str(params, "routine_id"), int(params.get("limit", 100)))
        if method == "automation_health":
            return self.service.automation_health(float(params.get("stale_after_seconds", 900.0)))
        if method == "automation_reconcile":
            return self.service.reconcile_automation(stale_after_seconds=float(params.get("stale_after_seconds", 900.0)), requeue=bool(params.get("requeue", False)))
        if method == "routine_approve":
            return self.service.approve_routine_run(_required_str(params, "run_id"))
        if method == "routine_delete":
            return self.service.delete_routine(_required_str(params, "id"))
        if method == "voice_profiles":
            return self.service.voice_profiles_snapshot()
        if method == "tool_approval":
            return self.service.request_tool_approval(_required_str(params, "name"), float(params.get("ttl_seconds", 30.0)))
        if method == "tool_execute":
            kwargs = params.get("kwargs", {})
            if not isinstance(kwargs, dict): raise IPCProtocolError("kwargs must be an object")
            return self.service.tool_execute(_required_str(params, "name"), approved=bool(params.get("approved", False)), approval_token=_optional_str(params, "approval_token"), **kwargs)
        if method == "tool_audit":
            return self.service.tool_audit_snapshot(int(params.get("limit", 100)))
        if method == "features":
            return self.service.feature_health()
        if method == "briefing":
            return self.service.briefing()
        if method == "desktop_signals":
            return self.service.desktop_signals()
        if method == "audio_devices":
            return self.service.audio_devices(_optional_str(params, "preferred"))
        if method == "meetings":
            return self.service.meetings_snapshot()
        if method == "meeting_start":
            return self.service.start_meeting()
        if method == "meeting_append":
            self.service.append_meeting_transcript(_required_str(params, "text")); return None
        if method == "meeting_stop":
            return self.service.stop_meeting()
        if method == "proactive":
            from marina.features import ContextSignals
            signals = params.get("signals", {})
            if not isinstance(signals, dict): raise IPCProtocolError("signals must be an object")
            return self.service.proactive_evaluate(ContextSignals(**signals))
        if method == "benchmark_summary":
            return self.service.voice_benchmarks.summary()
        raise IPCProtocolError(f"unknown method: {method}")

    @staticmethod
    def _is_socket(path: Path) -> bool:
        try:
            return stat.S_ISSOCK(path.stat().st_mode)
        except FileNotFoundError:
            return False


class LocalRPCClient:
    """One-shot client for the local JSON-line IPC protocol."""

    def __init__(self, socket_path: Path, timeout: float = 30.0) -> None:
        self.socket_path = Path(socket_path).expanduser().resolve()
        self.timeout = timeout

    def stream(self, text: str, *, provider: str | None = None, model: str | None = None):
        request = {"id": 1, "method": "ask_stream", "params": {"text": text}}
        if provider is not None:
            request["params"]["provider"] = provider
        if model is not None:
            request["params"]["model"] = model
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout)
            sock.connect(str(self.socket_path))
            sock.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
            with sock.makefile("rb") as stream:
                for raw_line in stream:
                    if not raw_line:
                        break
                    response = json.loads(raw_line.decode("utf-8"))
                    if not response.get("ok"):
                        raise RuntimeError(response.get("error", "IPC streaming request failed"))
                    if response.get("type") == "event":
                        yield response["event"]
                    elif response.get("type") == "complete":
                        return response.get("result", "")
        raise RuntimeError("IPC server closed before stream completed")

    def call(self, method: str, **params: Any) -> Any:
        request = {"id": 1, "method": method, "params": params}
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout)
            sock.connect(str(self.socket_path))
            sock.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
            line = sock.makefile("rb").readline()
        if not line:
            raise RuntimeError("IPC server closed without a response")
        response = json.loads(line.decode("utf-8"))
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "IPC request failed"))
        return response.get("result")


def default_socket_path(data_dir: Path) -> Path:
    return Path(data_dir).expanduser().resolve() / "marina.sock"


def _required_str(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IPCProtocolError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_str(params: dict[str, Any], key: str) -> str | None:
    value = params.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise IPCProtocolError(f"{key} must be a string")
    return value.strip() or None
