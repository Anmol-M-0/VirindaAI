from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Any, Protocol
from uuid import uuid4

from virinda.infrastructure.jobs import JobBroker, JobEnvelope

# ---------- Memory ----------


@dataclass(frozen=True, slots=True)
class MemoryFact:
    id: str
    key: str
    value: str
    source: str = "user"
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    sensitivity: str = "normal"


@dataclass(frozen=True, slots=True)
class MemoryNote:
    id: str
    text: str
    source: str = "conversation"
    created_at: float = field(default_factory=time.time)
    sensitivity: str = "normal"
    embedding: tuple[float, ...] | None = None


class MemoryStore:
    """Durable local facts and notes with deterministic local ranking.

    The store is application-owned state. It does not own OVOS conversation state and
    respects the caller's privacy policy before new durable records are created.
    """

    """Durable, inspectable, deletable local memory on the existing SQLite DB."""

    def __init__(
        self, conn: sqlite3.Connection, lock: RLock, embedder: EmbeddingProvider | None = None
    ) -> None:
        self.conn = conn
        self.lock = lock
        self.embedder = embedder or HashEmbeddingProvider()
        with self.lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_facts (
                    id TEXT PRIMARY KEY,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    sensitivity TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_notes (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    sensitivity TEXT NOT NULL,
                    embedding_json TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_notes_created ON memory_notes(created_at DESC);
                """
            )
            try:
                self.conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS memory_notes_fts USING fts5(id UNINDEXED, text, content='memory_notes', content_rowid='rowid')"
                )
            except sqlite3.OperationalError:
                pass
            self.conn.commit()

    def upsert_fact(
        self,
        key: str,
        value: str,
        *,
        source: str = "user",
        confidence: float = 1.0,
        sensitivity: str = "normal",
    ) -> MemoryFact:
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ValueError("memory fact key and value are required")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        now = time.time()
        fact_id = uuid4().hex
        with self.lock:
            self.conn.execute(
                """INSERT INTO memory_facts(id,key,value,source,confidence,sensitivity,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value,source=excluded.source,
                   confidence=excluded.confidence,sensitivity=excluded.sensitivity,updated_at=excluded.updated_at""",
                (fact_id, key, value, source, confidence, sensitivity, now, now),
            )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT id,key,value,source,confidence,sensitivity,created_at,updated_at FROM memory_facts WHERE key=?",
                (key,),
            ).fetchone()
        return MemoryFact(*row)

    def add_note(
        self, text: str, *, source: str = "conversation", sensitivity: str = "normal"
    ) -> MemoryNote:
        text = text.strip()
        if not text:
            raise ValueError("memory note cannot be empty")
        note = MemoryNote(
            uuid4().hex, text, source, sensitivity=sensitivity, embedding=self.embedder.embed(text)
        )
        with self.lock:
            self.conn.execute(
                "INSERT INTO memory_notes(id,text,source,sensitivity,embedding_json,created_at) VALUES(?,?,?,?,?,?)",
                (
                    note.id,
                    note.text,
                    note.source,
                    note.sensitivity,
                    json.dumps(note.embedding),
                    note.created_at,
                ),
            )
            self.conn.commit()
        return note

    def facts(self) -> list[MemoryFact]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id,key,value,source,confidence,sensitivity,created_at,updated_at FROM memory_facts ORDER BY key"
            ).fetchall()
        return [MemoryFact(*row) for row in rows]

    def notes(self, limit: int = 100) -> list[MemoryNote]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id,text,source,sensitivity,embedding_json,created_at FROM memory_notes ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            MemoryNote(
                row[0],
                row[1],
                row[2],
                row[5],
                row[3],
                None if row[4] is None else tuple(json.loads(row[4])),
            )
            for row in rows
        ]

    def search(self, query: str, limit: int = 10) -> dict[str, list[Any]]:
        query = query.strip()
        if not query:
            return {"facts": [], "notes": []}
        qvec = self.embedder.embed(query)
        tokens = [token for token in re.findall(r"[\w]+", query.lower()) if len(token) >= 3][:12]
        clauses = " OR ".join(["key LIKE ?", "value LIKE ?"] * len(tokens))
        params: list[str | int] = []
        for token in tokens:
            like = f"%{token}%"
            params.extend([like, like])
        with self.lock:
            if clauses:
                facts_rows = self.conn.execute(
                    f"SELECT id,key,value,source,confidence,sensitivity,created_at,updated_at FROM memory_facts WHERE {clauses} ORDER BY confidence DESC LIMIT ?",
                    (*params, limit),
                ).fetchall()
            else:
                facts_rows = []
            note_rows = self.conn.execute(
                "SELECT id,text,source,sensitivity,embedding_json,created_at FROM memory_notes ORDER BY created_at DESC LIMIT 500"
            ).fetchall()
        scored = []
        for row in note_rows:
            embedding = tuple(json.loads(row[4])) if row[4] else self.embedder.embed(row[1])
            lexical = 1.0 if query.lower() in row[1].lower() else 0.0
            scored.append((0.7 * cosine_similarity(qvec, embedding) + 0.3 * lexical, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        return {
            "facts": [asdict(MemoryFact(*row)) for row in facts_rows],
            "notes": [
                dict(
                    **asdict(
                        MemoryNote(
                            row[0],
                            row[1],
                            row[2],
                            row[5],
                            row[3],
                            tuple(json.loads(row[4])) if row[4] else None,
                        )
                    ),
                    score=score,
                )
                for score, row in scored[:limit]
            ],
        }

    def delete_fact(self, key: str) -> bool:
        with self.lock:
            cur = self.conn.execute("DELETE FROM memory_facts WHERE key=?", (key,))
            self.conn.commit()
            return cur.rowcount > 0

    def delete_note(self, note_id: str) -> bool:
        with self.lock:
            cur = self.conn.execute("DELETE FROM memory_notes WHERE id=?", (note_id,))
            self.conn.commit()
            return cur.rowcount > 0

    def clear(self) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM memory_facts")
            self.conn.execute("DELETE FROM memory_notes")
            self.conn.commit()


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> tuple[float, ...]: ...


class HashEmbeddingProvider:
    """Deterministic offline embedding fallback; replace with a local model add-on when desired."""

    dimensions = 64

    def embed(self, text: str) -> tuple[float, ...]:
        vector = [0.0] * self.dimensions
        for token in re.findall(r"[\w]+", text.lower()):
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = -1.0 if digest[4] & 1 else 1.0
            vector[index] += sign
        norm = sum(v * v for v in vector) ** 0.5 or 1.0
        return tuple(v / norm for v in vector)


def cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


# ---------- User profile / personalization ----------


@dataclass(frozen=True, slots=True)
class UserProfile:
    """Durable, explicitly editable user preferences used for personalization.

    This is intentionally small and non-sensitive by default. Values are stored
    locally and can be cleared independently of conversation history.
    """

    display_name: str | None = None
    locale: str | None = None
    timezone: str | None = None
    preferred_provider: str | None = None
    preferred_model: str | None = None
    preferred_voice: str | None = None


class UserProfileStore:
    """SQLite-backed single-user profile store with explicit clear/update semantics."""

    def __init__(self, conn: sqlite3.Connection, lock: RLock) -> None:
        self.conn, self.lock = conn, lock
        with lock:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS user_profile (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    payload_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )
            conn.commit()

    def get(self) -> UserProfile:
        with self.lock:
            row = self.conn.execute("SELECT payload_json FROM user_profile WHERE id=1").fetchone()
        if not row:
            return UserProfile()
        return UserProfile(**json.loads(row[0]))

    def update(self, **changes: Any) -> UserProfile:
        current = asdict(self.get())
        allowed = set(current)
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unknown profile fields: {sorted(unknown)}")
        for key, value in changes.items():
            if value is not None and not isinstance(value, str):
                raise TypeError(f"profile field {key} must be a string or null")
            current[key] = value.strip() if isinstance(value, str) else value
        profile = UserProfile(**current)
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO user_profile(id,payload_json,updated_at) VALUES(1,?,?)",
                (json.dumps(asdict(profile)), time.time()),
            )
            self.conn.commit()
        return profile

    def clear(self) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM user_profile WHERE id=1")
            self.conn.commit()


# ---------- Alerts + notifications ----------


@dataclass(frozen=True, slots=True)
class Alert:
    id: str
    kind: str
    title: str
    due_at: float
    recurring_seconds: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    active: bool = True


@dataclass(frozen=True, slots=True)
class Notification:
    id: str
    title: str
    body: str
    created_at: float
    read: bool = False
    source: str = "virinda"


class AlertScheduler:
    """Durable local alert/notification scheduler with a background worker.

    OVOS Alerts remains the preferred production UX/integration point; this scheduler
    provides a deterministic local implementation for standalone mode and tests.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        lock: RLock,
        emit: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.conn, self.lock, self.emit = conn, lock, emit
        self._stop = Event()
        self._thread: Thread | None = None
        with lock:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                    due_at REAL NOT NULL, recurring_seconds REAL, payload_json TEXT NOT NULL, active INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL,
                    created_at REAL NOT NULL, read INTEGER NOT NULL, source TEXT NOT NULL);
                """
            )
            conn.commit()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="virinda-alerts", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        self._thread = None

    def schedule(
        self,
        kind: str,
        title: str,
        due_at: float,
        *,
        recurring_seconds: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Alert:
        alert = Alert(uuid4().hex, kind, title, due_at, recurring_seconds, payload or {})
        with self.lock:
            self.conn.execute(
                "INSERT INTO alerts VALUES(?,?,?,?,?,?,?)",
                (
                    alert.id,
                    alert.kind,
                    alert.title,
                    alert.due_at,
                    alert.recurring_seconds,
                    json.dumps(alert.payload),
                    1,
                ),
            )
            self.conn.commit()
        return alert

    def cancel(self, alert_id: str) -> bool:
        with self.lock:
            cur = self.conn.execute("UPDATE alerts SET active=0 WHERE id=?", (alert_id,))
            self.conn.commit()
            return cur.rowcount > 0

    def list(self) -> list[Alert]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id,kind,title,due_at,recurring_seconds,payload_json,active FROM alerts WHERE active=1 ORDER BY due_at"
            ).fetchall()
        return [
            Alert(row[0], row[1], row[2], row[3], row[4], json.loads(row[5]), bool(row[6]))
            for row in rows
        ]

    def _run(self) -> None:
        while not self._stop.is_set():
            now = time.time()
            due = []
            with self.lock:
                rows = self.conn.execute(
                    "SELECT id,kind,title,due_at,recurring_seconds,payload_json FROM alerts WHERE active=1 AND due_at<=?",
                    (now,),
                ).fetchall()
                for row in rows:
                    if row[4]:
                        self.conn.execute(
                            "UPDATE alerts SET due_at=? WHERE id=?", (now + row[4], row[0])
                        )
                    else:
                        self.conn.execute("UPDATE alerts SET active=0 WHERE id=?", (row[0],))
                self.conn.commit()
            for row in rows:
                payload = json.loads(row[5])
                if self.emit:
                    self.emit(
                        "alert.fired",
                        {"id": row[0], "kind": row[1], "title": row[2], "payload": payload},
                    )
            self._stop.wait(0.25)

    def notify(self, title: str, body: str, *, source: str = "virinda") -> Notification:
        item = Notification(uuid4().hex, title, body, time.time(), False, source)
        with self.lock:
            self.conn.execute(
                "INSERT INTO notifications VALUES(?,?,?,?,?,?)",
                (item.id, item.title, item.body, item.created_at, 0, item.source),
            )
            self.conn.commit()
        if self.emit:
            self.emit("notification.created", asdict(item))
        return item

    def notifications(self, unread_only: bool = False, limit: int = 100) -> list[Notification]:
        sql = (
            "SELECT id,title,body,created_at,read,source FROM notifications "
            + ("WHERE read=0 " if unread_only else "")
            + "ORDER BY created_at DESC LIMIT ?"
        )
        with self.lock:
            rows = self.conn.execute(sql, (limit,)).fetchall()
        return [Notification(row[0], row[1], row[2], row[3], bool(row[4]), row[5]) for row in rows]

    def mark_read(self, notification_id: str) -> bool:
        with self.lock:
            cur = self.conn.execute(
                "UPDATE notifications SET read=1 WHERE id=?", (notification_id,)
            )
            self.conn.commit()
            return cur.rowcount > 0


# ---------- Safe tools ----------


class ToolExecutionAudit:
    """Append-only local record of privileged tool executions.

    Audit entries contain risk, approval and outcome metadata but should never contain
    secrets or full sensitive payloads.
    """

    def __init__(self, conn: sqlite3.Connection, lock: RLock) -> None:
        self.conn, self.lock = conn, lock
        with lock:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS tool_audit(id TEXT PRIMARY KEY, tool TEXT, risk TEXT, approved INTEGER, success INTEGER, summary TEXT, created_at REAL)"
            )
            conn.commit()

    def record(self, tool: str, risk: str, approved: bool, success: bool, summary: str) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO tool_audit VALUES(?,?,?,?,?,?,?)",
                (uuid4().hex, tool, risk, int(approved), int(success), summary[:1000], time.time()),
            )
            self.conn.commit()

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id,tool,risk,approved,success,summary,created_at FROM tool_audit ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            dict(
                id=r[0],
                tool=r[1],
                risk=r[2],
                approved=bool(r[3]),
                success=bool(r[4]),
                summary=r[5],
                created_at=r[6],
            )
            for r in rows
        ]


def system_info() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "hostname": platform.node(),
        "cpu_count": os.cpu_count(),
        "cwd": str(Path.cwd()),
        "home": str(Path.home()),
        "disk_free": shutil.disk_usage(Path.home()).free,
    }


def open_application(command: list[str]) -> dict[str, Any]:
    if not command or any(not isinstance(x, str) or not x for x in command):
        raise ValueError("invalid command")
    executable = shutil.which(command[0])
    if not executable:
        raise FileNotFoundError(command[0])
    proc = subprocess.Popen(
        [executable, *command[1:]],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"pid": proc.pid, "executable": executable}


def _validate_public_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http/https URLs are allowed")
    if not parsed.hostname:
        raise ValueError("URL hostname is required")
    if parsed.username or parsed.password:
        raise ValueError("URL credentials are not allowed")
    host = parsed.hostname.rstrip(".")
    try:
        addr = ipaddress.ip_address(host)
        addresses = [addr]
    except ValueError:
        try:
            infos = __import__("socket").getaddrinfo(
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=__import__("socket").SOCK_STREAM,
            )
            addresses = [ipaddress.ip_address(item[4][0]) for item in infos]
        except OSError as exc:
            raise ValueError("unable to resolve URL host") from exc
    for addr in addresses:
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ):
            raise ValueError("local/private URL targets are not allowed")
    return parsed


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _safe_urlopen(url: str, *, timeout: float = 10.0, max_bytes: int | None = None):
    _validate_public_url(url)
    opener = urllib.request.build_opener(_NoRedirect)
    current = url
    for _ in range(4):
        request = urllib.request.Request(current, headers={"User-Agent": "VirindaAI/1.x"})
        response = opener.open(request, timeout=timeout)
        if response.status not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("Location")
        response.close()
        if not location:
            raise ValueError("redirect missing Location header")
        current = urllib.parse.urljoin(current, location)
        _validate_public_url(current)
    raise ValueError("too many redirects")


def open_url(url: str) -> dict[str, Any]:
    _validate_public_url(url)
    for cmd in (("xdg-open", url), ("gio", "open", url)):
        if shutil.which(cmd[0]):
            subprocess.Popen(
                list(cmd),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return {"url": url, "opened": True, "command": cmd[0]}
    raise RuntimeError("no desktop URL opener installed")


def fetch_url(url: str, max_bytes: int = 256_000) -> str:
    if max_bytes <= 0 or max_bytes > 4_000_000:
        raise ValueError("max_bytes must be between 1 and 4000000")
    response = _safe_urlopen(url, timeout=10.0)
    try:
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("response exceeds maximum size")
        return data.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    finally:
        response.close()


def safe_read(path: Path, allowed_roots: tuple[Path, ...], max_bytes: int = 1_000_000) -> str:
    target = path.expanduser().resolve()
    roots = tuple(root.expanduser().resolve() for root in allowed_roots)
    if not any(os.path.commonpath((str(target), str(root))) == str(root) for root in roots):
        raise PermissionError("path is outside approved directories")
    return target.read_text(encoding="utf-8")[:max_bytes]


def safe_write(path: Path, content: str, allowed_roots: tuple[Path, ...]) -> None:
    target = path.expanduser().resolve()
    roots = tuple(root.expanduser().resolve() for root in allowed_roots)
    if not any(os.path.commonpath((str(target), str(root))) == str(root) for root in roots):
        raise PermissionError("path is outside approved directories")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def clipboard_get() -> str:
    for cmd in (
        ("wl-paste", "--no-newline"),
        ("xclip", "-selection", "clipboard", "-o"),
        ("xsel", "--clipboard", "--output"),
    ):
        if shutil.which(cmd[0]):
            return subprocess.check_output(cmd, text=True, timeout=3)
    raise RuntimeError("no clipboard provider installed")


def clipboard_set(text: str) -> None:
    if shutil.which("wl-copy"):
        subprocess.run(["wl-copy"], input=text, text=True, check=True)
        return
    if shutil.which("xclip"):
        subprocess.run(["xclip", "-selection", "clipboard"], input=text, text=True, check=True)
        return
    if shutil.which("xsel"):
        subprocess.run(["xsel", "--clipboard", "--input"], input=text, text=True, check=True)
        return
    raise RuntimeError("no clipboard provider installed")


def screenshot(output: Path) -> Path:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ("grim", str(output)),
        ("gnome-screenshot", "-f", str(output)),
        ("import", str(output)),
    ):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, check=True)
            return output
    raise RuntimeError("no screenshot provider installed")


class OVOSBusAdapter:
    """Optional generic adapter for OVOS message bus topics without importing OVOS at module load."""

    def __init__(self, bus: Any) -> None:
        self.bus = bus

    def emit(self, topic: str, data: dict[str, Any]) -> None:
        self.bus.emit(self.bus.message(topic, data))


class OVOSAlertsAdapter:
    """Bridge Virinda notifications to an OVOS bus; the actual alerts skill owns scheduling/UI."""

    def __init__(self, bus_adapter: OVOSBusAdapter) -> None:
        self.bus = bus_adapter

    def notify(self, title: str, body: str, *, source: str = "virinda") -> None:
        self.bus.emit("virinda.notification", {"title": title, "body": body, "source": source})


class OVOSGuiAdapter:
    """Publish UI state to a configurable OVOS GUI message topic."""

    def __init__(self, bus_adapter: OVOSBusAdapter, topic: str = "virinda.gui.state") -> None:
        self.bus, self.topic = bus_adapter, topic

    def publish(self, state: dict[str, Any]) -> None:
        self.bus.emit(self.topic, state)


@dataclass(frozen=True, slots=True)
class MeetingTranscript:
    id: str
    started_at: float
    ended_at: float | None
    transcript: str


class MeetingStore:
    def __init__(self, conn: sqlite3.Connection, lock: RLock) -> None:
        self.conn, self.lock = conn, lock
        with lock:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS meetings(id TEXT PRIMARY KEY, started_at REAL NOT NULL, ended_at REAL, transcript TEXT NOT NULL)"
            )
            conn.commit()

    def start(self) -> MeetingTranscript:
        item = MeetingTranscript(uuid4().hex, time.time(), None, "")
        with self.lock:
            self.conn.execute(
                "INSERT INTO meetings VALUES(?,?,?,?)", (item.id, item.started_at, None, "")
            )
            self.conn.commit()
        return item

    def append(self, meeting_id: str, text: str) -> None:
        with self.lock:
            self.conn.execute(
                "UPDATE meetings SET transcript=CASE WHEN transcript='' THEN ? ELSE transcript || char(10) || ? END WHERE id=?",
                (text, text, meeting_id),
            )
            self.conn.commit()

    def stop(self, meeting_id: str) -> MeetingTranscript | None:
        with self.lock:
            self.conn.execute(
                "UPDATE meetings SET ended_at=? WHERE id=?", (time.time(), meeting_id)
            )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT id,started_at,ended_at,transcript FROM meetings WHERE id=?", (meeting_id,)
            ).fetchone()
        return None if row is None else MeetingTranscript(*row)

    def list(self) -> list[MeetingTranscript]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id,started_at,ended_at,transcript FROM meetings ORDER BY started_at DESC"
            ).fetchall()
        return [MeetingTranscript(*r) for r in rows]


# ---------- Voice profiles ----------


@dataclass(frozen=True, slots=True)
class VoiceProfile:
    name: str
    wake_word: str = "hey virinda"
    wake_threshold: float = 0.5
    tts_voice: str = "default"
    language: str = "en-us"
    enabled: bool = True


class VoiceProfileStore:
    def __init__(self, conn: sqlite3.Connection, lock: RLock) -> None:
        self.conn, self.lock = conn, lock
        with lock:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS voice_profiles(name TEXT PRIMARY KEY, payload_json TEXT NOT NULL, updated_at REAL NOT NULL)"
            )
            conn.commit()

    def save(self, profile: VoiceProfile) -> VoiceProfile:
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO voice_profiles VALUES(?,?,?)",
                (profile.name, json.dumps(asdict(profile)), time.time()),
            )
            self.conn.commit()
        return profile

    def list(self) -> list[VoiceProfile]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT payload_json FROM voice_profiles ORDER BY name"
            ).fetchall()
        return [VoiceProfile(**json.loads(r[0])) for r in rows]


# ---------- Automation + proactive context ----------


@dataclass(frozen=True, slots=True)
class Routine:
    """Persistent declarative automation.

    ``trigger`` uses one of the forms:

    - ``at:<unix timestamp>``
    - ``every:<timestamp>`` (legacy repeating interval)
    - ``schedule:<expression>`` (natural-language recurring schedule)
    - ``keyword:<text>``
    - ``event:<event name>``
    - ``app:<application substring>``

    ``action`` is a backwards-compatible string. Multiple steps can be separated with
    ``||`` and each step uses ``notify:<title>|<body>`` or
    ``tool:<tool name>|<JSON kwargs>``. Tool steps can be gated with
    ``approve:tool:<tool name>|<JSON kwargs>``.
    """

    id: str
    name: str
    trigger: str
    action: str
    enabled: bool = True
    retry_limit: int = 0
    retry_backoff_seconds: float = 2.0
    require_approval: bool = False


@dataclass(frozen=True, slots=True)
class RoutineRun:
    id: str
    routine_id: str
    status: str
    attempt: int
    started_at: float
    finished_at: float | None = None
    error: str | None = None
    approval_required: bool = False


class RoutineStore:
    """Persistent store for the constrained, non-shell automation DSL.

    Schema migration is additive so older Virinda databases remain readable.
    """

    def __init__(self, conn: sqlite3.Connection, lock: RLock) -> None:
        self.conn, self.lock = conn, lock
        with lock:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS routines(
                    id TEXT PRIMARY KEY,name TEXT NOT NULL,trigger TEXT NOT NULL,action TEXT NOT NULL,
                    enabled INTEGER NOT NULL,retry_limit INTEGER NOT NULL DEFAULT 0,
                    retry_backoff_seconds REAL NOT NULL DEFAULT 2.0,
                    require_approval INTEGER NOT NULL DEFAULT 0
                )"""
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(routines)").fetchall()}
            if "retry_limit" not in columns:
                conn.execute(
                    "ALTER TABLE routines ADD COLUMN retry_limit INTEGER NOT NULL DEFAULT 0"
                )
            if "retry_backoff_seconds" not in columns:
                conn.execute(
                    "ALTER TABLE routines ADD COLUMN retry_backoff_seconds REAL NOT NULL DEFAULT 2.0"
                )
            if "require_approval" not in columns:
                conn.execute(
                    "ALTER TABLE routines ADD COLUMN require_approval INTEGER NOT NULL DEFAULT 0"
                )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS routine_runs(
                    id TEXT PRIMARY KEY,routine_id TEXT NOT NULL,status TEXT NOT NULL,attempt INTEGER NOT NULL,
                    started_at REAL NOT NULL,finished_at REAL,error TEXT,approval_required INTEGER NOT NULL DEFAULT 0
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_routine_runs_routine ON routine_runs(routine_id, started_at DESC)"
            )
            conn.commit()

    def save(self, routine: Routine) -> Routine:
        if routine.retry_limit < 0 or routine.retry_limit > 10:
            raise ValueError("retry_limit must be between 0 and 10")
        if routine.retry_backoff_seconds < 0 or routine.retry_backoff_seconds > 300:
            raise ValueError("retry_backoff_seconds must be between 0 and 300")
        with self.lock:
            self.conn.execute(
                """INSERT OR REPLACE INTO routines
                   (id,name,trigger,action,enabled,retry_limit,retry_backoff_seconds,require_approval)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    routine.id,
                    routine.name,
                    routine.trigger,
                    routine.action,
                    int(routine.enabled),
                    routine.retry_limit,
                    routine.retry_backoff_seconds,
                    int(routine.require_approval),
                ),
            )
            self.conn.commit()
        return routine

    def list(self) -> list[Routine]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT id,name,trigger,action,enabled,retry_limit,retry_backoff_seconds,require_approval FROM routines ORDER BY name"
            ).fetchall()
        return [
            Routine(r[0], r[1], r[2], r[3], bool(r[4]), int(r[5]), float(r[6]), bool(r[7]))
            for r in rows
        ]

    def get(self, routine_id: str) -> Routine | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT id,name,trigger,action,enabled,retry_limit,retry_backoff_seconds,require_approval FROM routines WHERE id=?",
                (routine_id,),
            ).fetchone()
        return (
            None
            if row is None
            else Routine(
                row[0],
                row[1],
                row[2],
                row[3],
                bool(row[4]),
                int(row[5]),
                float(row[6]),
                bool(row[7]),
            )
        )

    def delete(self, routine_id: str) -> bool:
        with self.lock:
            cur = self.conn.execute("DELETE FROM routines WHERE id=?", (routine_id,))
            self.conn.commit()
            return cur.rowcount > 0

    def update(self, routine_id: str, **changes: Any) -> Routine | None:
        allowed = {
            "name",
            "trigger",
            "action",
            "enabled",
            "retry_limit",
            "retry_backoff_seconds",
            "require_approval",
        }
        if set(changes) - allowed:
            raise ValueError("unsupported routine fields")
        current = self.get(routine_id)
        if current is None:
            return None
        values = {
            "name": current.name,
            "trigger": current.trigger,
            "action": current.action,
            "enabled": current.enabled,
            "retry_limit": current.retry_limit,
            "retry_backoff_seconds": current.retry_backoff_seconds,
            "require_approval": current.require_approval,
        }
        values.update(changes)
        return self.save(
            Routine(
                routine_id,
                str(values["name"]).strip(),
                str(values["trigger"]).strip(),
                str(values["action"]).strip(),
                bool(values["enabled"]),
                int(values["retry_limit"]),
                float(values["retry_backoff_seconds"]),
                bool(values["require_approval"]),
            )
        )

    def conflicts(self, routine: Routine, exclude_id: str | None = None) -> list[Routine]:
        normalized = " ".join(routine.trigger.lower().split())
        conflicts = []
        for existing in self.list():
            if not existing.enabled or (exclude_id and existing.id == exclude_id):
                continue
            if " ".join(existing.trigger.lower().split()) == normalized:
                conflicts.append(existing)
        return conflicts

    def disable(self, routine_id: str) -> bool:
        with self.lock:
            cur = self.conn.execute("UPDATE routines SET enabled=0 WHERE id=?", (routine_id,))
            self.conn.commit()
            return cur.rowcount > 0

    def record_run(self, run: RoutineRun) -> RoutineRun:
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO routine_runs(id,routine_id,status,attempt,started_at,finished_at,error,approval_required) VALUES(?,?,?,?,?,?,?,?)",
                (
                    run.id,
                    run.routine_id,
                    run.status,
                    run.attempt,
                    run.started_at,
                    run.finished_at,
                    run.error,
                    int(run.approval_required),
                ),
            )
            self.conn.commit()
        return run

    def update_run(self, run_id: str, **changes: Any) -> RoutineRun | None:
        allowed = {"status", "attempt", "finished_at", "error", "approval_required"}
        if set(changes) - allowed:
            raise ValueError("unsupported routine run fields")
        with self.lock:
            row = self.conn.execute(
                "SELECT id,routine_id,status,attempt,started_at,finished_at,error,approval_required FROM routine_runs WHERE id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            current = RoutineRun(
                row[0], row[1], row[2], row[3], row[4], row[5], row[6], bool(row[7])
            )
            values = {
                "status": current.status,
                "attempt": current.attempt,
                "finished_at": current.finished_at,
                "error": current.error,
                "approval_required": current.approval_required,
            }
            values.update(changes)
            self.conn.execute(
                "UPDATE routine_runs SET status=?,attempt=?,finished_at=?,error=?,approval_required=? WHERE id=?",
                (
                    values["status"],
                    values["attempt"],
                    values["finished_at"],
                    values["error"],
                    int(values["approval_required"]),
                    run_id,
                ),
            )
            self.conn.commit()
            return RoutineRun(
                run_id,
                current.routine_id,
                values["status"],
                values["attempt"],
                current.started_at,
                values["finished_at"],
                values["error"],
                bool(values["approval_required"]),
            )

    def runs(self, routine_id: str | None = None, limit: int = 100) -> list[RoutineRun]:
        with self.lock:
            if routine_id:
                rows = self.conn.execute(
                    "SELECT id,routine_id,status,attempt,started_at,finished_at,error,approval_required FROM routine_runs WHERE routine_id=? ORDER BY started_at DESC LIMIT ?",
                    (routine_id, limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT id,routine_id,status,attempt,started_at,finished_at,error,approval_required FROM routine_runs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [RoutineRun(r[0], r[1], r[2], r[3], r[4], r[5], r[6], bool(r[7])) for r in rows]

    def last_success(self, routine_id: str) -> RoutineRun | None:
        with self.lock:
            row = self.conn.execute(
                "SELECT id,routine_id,status,attempt,started_at,finished_at,error,approval_required FROM routine_runs WHERE routine_id=? AND status='succeeded' ORDER BY finished_at DESC LIMIT 1",
                (routine_id,),
            ).fetchone()
        return (
            None
            if row is None
            else RoutineRun(row[0], row[1], row[2], row[3], row[4], row[5], row[6], bool(row[7]))
        )

    def has_active_run(self, routine_id: str) -> bool:
        """Return whether a routine already has queued/running/pending work."""
        with self.lock:
            row = self.conn.execute(
                "SELECT 1 FROM routine_runs WHERE routine_id=? AND status IN ('queued','running','pending_approval') ORDER BY started_at DESC LIMIT 1",
                (routine_id,),
            ).fetchone()
        return row is not None

    def stale_runs(
        self, *, older_than_seconds: float, now: float | None = None
    ) -> list[RoutineRun]:
        """Return active runs older than the supplied age for operator recovery."""
        cutoff = (time.time() if now is None else now) - max(1.0, float(older_than_seconds))
        with self.lock:
            rows = self.conn.execute(
                "SELECT id,routine_id,status,attempt,started_at,finished_at,error,approval_required "
                "FROM routine_runs WHERE status IN ('queued','running') AND started_at < ? ORDER BY started_at ASC",
                (cutoff,),
            ).fetchall()
        return [RoutineRun(r[0], r[1], r[2], r[3], r[4], r[5], r[6], bool(r[7])) for r in rows]


@dataclass(frozen=True, slots=True)
class ContextSignals:
    active_application: str | None = None
    headset_connected: bool | None = None
    present: bool | None = None
    quiet_hours: bool = False
    meeting_active: bool = False


class ProactiveEngine:
    """Evaluates local context signals against explicit proactive policy rules.

    The engine returns decisions; delivery is delegated to notification/OVOS adapters.
    """

    def __init__(self, notify: Callable[[str, str], Any]) -> None:
        self.notify = notify
        self._seen: set[str] = set()

    def evaluate(self, signals: ContextSignals, *, now: float | None = None) -> list[str]:
        _ = now or time.time()
        actions: list[str] = []
        if (
            signals.meeting_active
            and signals.headset_connected is False
            and "meeting-no-headset" not in self._seen
        ):
            self._seen.add("meeting-no-headset")
            actions.append("meeting-no-headset")
            self.notify("Meeting mode", "A meeting is active but no headset is connected.")
        if (
            signals.active_application
            and "terminal" in signals.active_application.lower()
            and not signals.quiet_hours
            and "terminal-tip" not in self._seen
        ):
            self._seen.add("terminal-tip")
            actions.append("terminal-tip")
        return actions


# ---------- Multimodal / benchmark / speaker ID ----------


@dataclass(frozen=True, slots=True)
class MultimodalInput:
    kind: str
    source: str
    content: bytes | str
    metadata: dict[str, Any] = field(default_factory=dict)


class VisionProvider(Protocol):
    def analyze(self, image: MultimodalInput, prompt: str) -> str: ...


def capture_screen_input(path: Path) -> MultimodalInput:
    p = screenshot(path)
    return MultimodalInput("image", str(p), p.read_bytes(), {"path": str(p)})


def capture_clipboard_input() -> MultimodalInput:
    return MultimodalInput("text", "clipboard", clipboard_get())


@dataclass(frozen=True, slots=True)
class VoiceLatencySample:
    wake_ms: float | None
    end_of_speech_ms: float | None
    stt_ms: float | None
    llm_first_token_ms: float | None
    tts_first_audio_ms: float | None
    total_ms: float | None


@dataclass(frozen=True, slots=True)
class VoiceEventSample:
    """Timestamped events captured from the live OVOS voice pipeline.

    Event names are intentionally transport-neutral so a future native OVOS GUI,
    MessageBus subscriber, or diagnostics process can feed the same benchmark model.
    """

    turn_id: str
    event: str
    timestamp: float


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def latency_sample_from_events(events: list[VoiceEventSample]) -> VoiceLatencySample:
    """Derive one latency sample from a turn's timestamped voice lifecycle.

    Missing stages remain ``None`` instead of being fabricated. This matters for
    offline acceptance tests and for partial OVOS integrations where wake detection
    may not be observable outside Dinkum Listener.
    """
    by_event: dict[str, float] = {}
    for event in events:
        by_event.setdefault(event.event, event.timestamp)
    record_started = by_event.get("record.started")
    wake_detected = by_event.get("wake.detected")
    speech_ended = by_event.get("speech.ended") or by_event.get("record.ended")
    stt_completed = by_event.get("stt.completed")
    first_token = by_event.get("llm.first_token")
    first_audio = by_event.get("audio.output.started") or by_event.get("tts.first_audio")
    turn_completed = by_event.get("turn.completed") or by_event.get("audio.output.ended")

    def delta(start: float | None, end: float | None) -> float | None:
        if start is None or end is None or end < start:
            return None
        return (end - start) * 1000

    return VoiceLatencySample(
        wake_ms=delta(wake_detected, record_started),
        end_of_speech_ms=delta(record_started, speech_ended),
        stt_ms=delta(speech_ended, stt_completed),
        llm_first_token_ms=delta(stt_completed, first_token),
        tts_first_audio_ms=delta(first_token, first_audio),
        total_ms=delta(record_started or wake_detected, turn_completed),
    )


class VoiceBenchmark:
    """Persists measured voice-path latency samples and reports p50/p95.

    Hardware claims must come from real OVOS event timestamps; synthetic tests only
    validate storage and aggregation semantics. Missing stages are preserved as missing.
    """

    def __init__(self, conn: sqlite3.Connection, lock: RLock) -> None:
        self.conn, self.lock = conn, lock
        with lock:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS voice_benchmarks(id TEXT PRIMARY KEY,payload_json TEXT,created_at REAL)"
            )
            conn.commit()

    def record(self, sample: VoiceLatencySample) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT INTO voice_benchmarks VALUES(?,?,?)",
                (uuid4().hex, json.dumps(asdict(sample)), time.time()),
            )
            self.conn.commit()

    def record_events(self, events: list[VoiceEventSample]) -> VoiceLatencySample:
        sample = latency_sample_from_events(events)
        self.record(sample)
        return sample

    def summary(self) -> dict[str, Any]:
        with self.lock:
            rows = self.conn.execute(
                "SELECT payload_json FROM voice_benchmarks ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        samples = [json.loads(r[0]) for r in rows]
        if not samples:
            return {"count": 0}
        metrics = (
            "wake_ms",
            "end_of_speech_ms",
            "stt_ms",
            "llm_first_token_ms",
            "tts_first_audio_ms",
            "total_ms",
        )
        result: dict[str, Any] = {"count": len(samples), "window": min(100, len(samples))}
        for metric in metrics:
            values = [float(sample[metric]) for sample in samples if sample.get(metric) is not None]
            if not values:
                result[metric] = {"count": 0, "p50": None, "p95": None, "mean": None}
                continue
            result[metric] = {
                "count": len(values),
                "p50": _percentile(values, 0.50),
                "p95": _percentile(values, 0.95),
                "mean": sum(values) / len(values),
            }
        return result


class SpeakerIdentifier:
    """Local, privacy-preserving centroid classifier for PCM16 mono samples."""

    def __init__(self) -> None:
        self._centroids: dict[str, list[float]] = {}

    @staticmethod
    def features(samples: list[int]) -> list[float]:
        if not samples:
            return [0.0, 0.0, 0.0]
        mean = sum(samples) / len(samples)
        rms = (sum(x * x for x in samples) / len(samples)) ** 0.5
        zc = sum(1 for a, b in zip(samples, samples[1:]) if (a < 0) != (b < 0)) / max(
            1, len(samples) - 1
        )
        return [mean / 32768.0, rms / 32768.0, zc]

    def enroll(self, name: str, samples: list[int]) -> None:
        self._centroids[name] = self.features(samples)

    def identify(self, samples: list[int]) -> tuple[str, float] | None:
        if not self._centroids:
            return None
        f = self.features(samples)
        best = min(
            self._centroids.items(), key=lambda item: sum((a - b) ** 2 for a, b in zip(item[1], f))
        )
        distance = sum((a - b) ** 2 for a, b in zip(best[1], f)) ** 0.5
        return best[0], max(0.0, 1.0 - distance)


# ---------- Satellite transport ----------


@dataclass(frozen=True, slots=True)
class SatelliteEnvelope:
    """Versioned authenticated message envelope for future remote/satellite transport.

    This is a transport primitive, not a replacement for a production OVOS/HiveMind
    security model.
    """

    message_type: str
    data: dict[str, Any]
    origin: str = "virinda"
    timestamp: float = field(default_factory=time.time)
    nonce: str = field(default_factory=lambda: uuid4().hex)

    def canonical_bytes(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode("utf-8")

    def validate(self, *, now: float | None = None, max_age_seconds: float = 30.0) -> None:
        if not self.message_type.strip() or len(self.message_type) > 128:
            raise ValueError("invalid satellite message type")
        if not self.nonce or len(self.nonce) > 128:
            raise ValueError("invalid satellite nonce")
        age = abs((now or time.time()) - self.timestamp)
        if age > max_age_seconds:
            raise ValueError("stale satellite message")


class SatelliteTransport(Protocol):
    def send(self, envelope: SatelliteEnvelope) -> None: ...
    def close(self) -> None: ...


class OVOSBusSatellite:
    """Optional OVOS message-bus bridge; no OVOS dependency at import time."""

    def __init__(self, bus_client: Any) -> None:
        self.bus = bus_client

    def send(self, envelope: SatelliteEnvelope) -> None:
        self.bus.emit(self.bus.message("virinda.satellite", asdict(envelope)))

    def close(self) -> None:
        pass


# ---------- Desktop overlay ----------

OVERLAY_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Virinda</title>
<style>
:root{font-family:system-ui,-apple-system,sans-serif;color-scheme:light dark}body{margin:0;background:#0f1115;color:#eef1f5}main{max-width:1100px;margin:0 auto;padding:24px}header{display:flex;justify-content:space-between;align-items:center;gap:16px;position:sticky;top:0;background:#0f1115ee;backdrop-filter:blur(12px);padding:12px 0;z-index:2}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.card{background:#171a21;border:1px solid #2a3040;border-radius:16px;padding:16px;box-shadow:0 8px 30px #0005}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.muted{opacity:.7;font-size:.9rem}button{font:inherit;border:1px solid #394050;background:#222735;color:inherit;border-radius:10px;padding:9px 12px;cursor:pointer}button.primary{background:#5d7cff;border-color:#6f8cff}button.danger{background:#55262a;border-color:#7c363c}input,textarea{font:inherit;width:100%;box-sizing:border-box;background:#0f1218;color:inherit;border:1px solid #394050;border-radius:10px;padding:10px}.field{margin:10px 0}.pill{display:inline-block;border-radius:999px;padding:4px 8px;background:#252b38;font-size:.8rem}.routine{border:1px solid #2a3040;border-radius:12px;padding:12px;margin:10px 0}.routine-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}.steps{white-space:pre-wrap;background:#0f1218;border-radius:10px;padding:10px;margin-top:8px;overflow:auto}.ok{color:#7ce0a3}.warn{color:#ffd16b}.err{color:#ff8d8d}@media(max-width:800px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body><main>
<header><div><h1 style="margin:0">Virinda</h1><div id="state" class="muted">Loading…</div></div><div class="row"><button onclick="setMode('normal')">Normal</button><button onclick="setMode('focus')">Focus</button><button onclick="setMode('private')">Private</button><button onclick="setMode('quiet')">Quiet</button></div></header>
<section class="grid">
<div class="card"><h2>Conversation</h2><div class="row"><input id="q" placeholder="Ask Virinda"><button class="primary" onclick="ask()">Ask</button><button onclick="cancelAsk()">Stop</button></div><pre id="out" class="steps"></pre><div id="live" class="muted"></div></div>
<div class="card"><h2>Routine editor</h2><div class="field"><label>Name</label><input id="rname" placeholder="Morning Review"></div><div class="field"><label>Trigger</label><input id="rtrigger" placeholder="schedule:every weekday at 9 am"></div><div class="field"><label>Actions</label><textarea id="raction" rows="6" placeholder="notify:Virinda|Review the dashboard||approve:tool:browser.open|{&quot;url&quot;:&quot;https://example.com&quot;}"></textarea></div><div class="row"><label><input type="checkbox" id="rapproval"> Require approval</label><label><input type="checkbox" id="rconflict"> Allow conflicts</label></div><div class="row"><button class="primary" onclick="saveRoutine()">Save</button><button onclick="previewEditor()">Preview</button><button onclick="clearEditor()">New</button></div><pre id="preview" class="steps"></pre></div>
</section>
<section class="card" style="margin-top:18px"><div class="row" style="justify-content:space-between"><h2 style="margin:0">Routines</h2><button onclick="loadRoutines()">Refresh</button></div><div id="routines"></div></section>
<section class="card" style="margin-top:18px"><div class="row" style="justify-content:space-between"><h2 style="margin:0">Recent runs</h2><button onclick="loadRuns()">Refresh</button></div><pre id="runs" class="steps"></pre></section>
<script>
let editingId=null;
async function api(path,opts={}){const r=await fetch(path,opts);const d=await r.json();if(!r.ok)throw new Error(d.error||'request failed');return d}
const jsonOpts=(body)=>({method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
async function refresh(){try{const [s,live]=await Promise.all([api('/api/status'),api('/api/live-context')]);state.textContent=s.status+' · '+s.lifecycle+' · '+s.context.mode;liveEl.textContent='Listening: '+live.listening+' · Speaking: '+live.speaking+' · Last user: '+(live.last_user_utterance||'—');}catch(e){state.textContent='offline'}}
async function ask(){try{const r=await api('/api/ask',jsonOpts({text:q.value}));out.textContent=r.result||r.error||'';refresh()}catch(e){out.textContent=e.message}}
async function cancelAsk(){await api('/api/cancel',jsonOpts({reason:'overlay'}));refresh()}
async function setMode(m){await api('/api/context',jsonOpts({mode:m}));refresh()}
function clearEditor(){editingId=null;rname.value='';rtrigger.value='';raction.value='';rapproval.checked=false;rconflict.checked=false;preview.textContent='';}
function editRoutine(r){editingId=r.id;rname.value=r.name;rtrigger.value=r.trigger;raction.value=r.action;rapproval.checked=!!r.require_approval;rconflict.checked=false;preview.textContent='';window.scrollTo({top:0,behavior:'smooth'})}
async function saveRoutine(){try{const p={name:rname.value,trigger:rtrigger.value,action:raction.value,retry_limit:0,retry_backoff_seconds:2,require_approval:rapproval.checked,allow_conflict:rconflict.checked};await api(editingId?'/api/routine-update':'/api/routine-save',jsonOpts(editingId?{id:editingId,changes:p}:p));clearEditor();await loadRoutines()}catch(e){preview.textContent='Error: '+e.message}}
async function previewEditor(){if(!editingId){preview.textContent='Save the routine first, then preview it.';return}try{preview.textContent=JSON.stringify(await api('/api/routine-preview',jsonOpts({id:editingId})),null,2)}catch(e){preview.textContent='Error: '+e.message}}
async function previewRoutine(id){editingId=id;try{preview.textContent=JSON.stringify(await api('/api/routine-preview',jsonOpts({id})),null,2)}catch(e){preview.textContent='Error: '+e.message}}
async function loadRoutines(){try{const rs=await api('/api/routines');routines.innerHTML=rs.length?rs.map(r=>`<div class="routine"><div class="routine-head"><div><strong>${esc(r.name)}</strong><div class="muted">${esc(r.trigger)}</div></div><span class="pill">${r.enabled?'enabled':'disabled'}</span></div><div class="steps">${esc(r.action)}</div><div class="row"><button onclick='editRoutine(${JSON.stringify(r)})'>Edit</button><button onclick='previewRoutine(${JSON.stringify(r.id)})'>Preview</button><button onclick='runNow(${JSON.stringify(r.id)})'>Run now</button><button onclick='disableRoutine(${JSON.stringify(r.id)})'>Disable</button><button class="danger" onclick='deleteRoutine(${JSON.stringify(r.id)})'>Delete</button></div></div>`).join(''):'<div class="muted">No routines.</div>'}catch(e){routines.textContent=e.message}await loadRuns()}
async function loadRuns(){try{runs.textContent=JSON.stringify(await api('/api/routine-runs'),null,2)}catch(e){runs.textContent=e.message}}
async function disableRoutine(id){await api('/api/routine-disable',jsonOpts({id}));loadRoutines()}
async function deleteRoutine(id){if(confirm('Delete this routine?')){await api('/api/routine-delete',jsonOpts({id}));loadRoutines()}}
async function runDue(){await api('/api/routine-run',jsonOpts({}));loadRoutines()}
async function runNow(id){try{const r=await api('/api/routine-run-now',jsonOpts({id}));preview.textContent='Run status: '+r.status;loadRoutines()}catch(e){preview.textContent='Error: '+e.message}}
function esc(s){return String(s??'').replace(/[&<>\"]/g,c=>c==='&'?'&amp;':c==='<'?'&lt;':c==='>'?'&gt;':'&quot;')}
const state=document.getElementById('state'),liveEl=document.getElementById('live'),out=document.getElementById('out'),q=document.getElementById('q'),rname=document.getElementById('rname'),rtrigger=document.getElementById('rtrigger'),raction=document.getElementById('raction'),rapproval=document.getElementById('rapproval'),rconflict=document.getElementById('rconflict'),preview=document.getElementById('preview'),routines=document.getElementById('routines'),runs=document.getElementById('runs');
refresh();loadRoutines();setInterval(()=>{refresh();loadRoutines()},5000);
</script></main></body></html>
"""

# ---------- Additional roadmap primitives ----------


@dataclass(frozen=True, slots=True)
class WakeWordResult:
    expected: bool
    detected: bool
    latency_ms: float


class WakeWordEvaluator:
    """Evaluate recorded wake-word decisions and derive FAR/FRR metrics."""

    @staticmethod
    def evaluate(results: list[WakeWordResult]) -> dict[str, float | int]:
        positives = [r for r in results if r.expected]
        negatives = [r for r in results if not r.expected]
        false_rejections = sum(1 for r in positives if not r.detected)
        false_accepts = sum(1 for r in negatives if r.detected)
        latencies = [r.latency_ms for r in positives if r.detected]
        return {
            "samples": len(results),
            "false_rejection_rate": false_rejections / len(positives) if positives else 0.0,
            "false_accept_rate": false_accepts / len(negatives) if negatives else 0.0,
            "mean_detection_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        }


class RoutineRunner:
    """Execute safe routines with retries, multi-step actions and approval checkpoints."""

    def __init__(
        self,
        store: RoutineStore,
        notify: Callable[[str, str], Any],
        tool_executor: Callable[..., Any],
        approval_requester: Callable[[str], dict[str, Any]] | None = None,
        emit: Callable[[str, dict[str, Any]], Any] | None = None,
        context_provider: Callable[[], dict[str, Any]] | None = None,
        job_broker: JobBroker | None = None,
        job_subject: str = "virinda.jobs.automation.execute",
    ) -> None:
        self.store, self.notify, self.tool_executor = store, notify, tool_executor
        self.approval_requester, self.emit, self.context_provider = (
            approval_requester,
            emit,
            context_provider,
        )
        self.job_broker, self.job_subject = job_broker, job_subject

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self.emit:
            try:
                self.emit(event, payload)
            except Exception:
                pass

    @staticmethod
    def _matches_event(
        routine: Routine, event_name: str, payload: dict[str, Any] | None = None
    ) -> bool:
        if routine.trigger.startswith("event:"):
            expected = routine.trigger.split(":", 1)[1].strip().lower()
            return expected == event_name.strip().lower()
        if routine.trigger.startswith("app:"):
            app = str((payload or {}).get("application", "")).lower()
            expected = routine.trigger.split(":", 1)[1].strip().lower()
            return bool(expected and expected in app)
        return False

    def dispatch(
        self,
        routine: Routine,
        *,
        trigger_context: dict[str, Any] | None = None,
        approved_run: bool = False,
        run_id: str | None = None,
    ) -> str:
        """Queue a routine for background execution when a JobBroker is configured.

        Without a broker, execution remains synchronous for unit tests and standalone
        compatibility mode. The public return value is the execution/run identifier.
        """
        run_id = run_id or uuid4().hex
        if self.job_broker is None:
            return self.execute(
                routine,
                trigger_context=trigger_context,
                approved_run=approved_run,
                run_id=run_id,
            )
        payload = {
            "routine_id": routine.id,
            "trigger_context": trigger_context or {},
            "approved_run": bool(approved_run),
            "run_id": run_id,
        }
        self.store.record_run(RoutineRun(run_id, routine.id, "queued", 0, time.time()))
        self.job_broker.publish(
            JobEnvelope(
                subject=self.job_subject,
                payload=payload,
                idempotency_key=f"routine-run:{run_id}",
                session_id=self.context_provider().get("session_id")
                if self.context_provider
                else None,
            )
        )
        self._emit(
            "routine.queued", {"run_id": run_id, "routine_id": routine.id, "name": routine.name}
        )
        return run_id

    def wait_for_terminal(self, run_id: str, timeout: float = 30.0) -> str:
        """Wait for an asynchronously queued run to reach a terminal state."""
        deadline = time.time() + max(0.1, timeout)
        while time.time() < deadline:
            runs = [run for run in self.store.runs(limit=500) if run.id == run_id]
            if runs:
                status = runs[0].status
                if status in {"succeeded", "failed", "pending_approval"}:
                    return status
            time.sleep(0.05)
        return "queued"

    def handle_job(self, job: JobEnvelope) -> str:
        """Execute a broker-delivered automation job exactly once from its payload."""
        payload = job.payload
        routine_id = str(payload.get("routine_id", ""))
        routine = self.store.get(routine_id)
        if routine is None:
            raise KeyError(routine_id)
        return self.execute(
            routine,
            trigger_context=dict(payload.get("trigger_context") or {}),
            approved_run=bool(payload.get("approved_run", False)),
            run_id=str(payload.get("run_id") or job.id),
        )

    def run_event(self, event_name: str, payload: dict[str, Any] | None = None) -> list[str]:
        actions = []
        for routine in self.store.list():
            if routine.enabled and self._matches_event(routine, event_name, payload):
                status = self._dispatch_status(routine, trigger_context=payload or {})
                if status in {"succeeded", "pending_approval", "queued"}:
                    actions.append(routine.id)
        return actions

    def run_keyword(self, keyword: str) -> list[str]:
        actions = []
        for routine in self.store.list():
            if not routine.enabled or not routine.trigger.startswith("keyword:"):
                continue
            expected = routine.trigger.split(":", 1)[1].strip().lower()
            if expected and expected in keyword.lower():
                status = self._dispatch_status(routine, trigger_context={"text": keyword})
                if status in {"succeeded", "pending_approval", "queued"}:
                    actions.append(routine.id)
        return actions

    def _dispatch_status(
        self, routine: Routine, *, trigger_context: dict[str, Any] | None = None
    ) -> str:
        """Dispatch and return a status; local jobs retain synchronous API semantics."""
        result = self.dispatch(routine, trigger_context=trigger_context)
        if self.job_broker is None:
            return result
        if getattr(self.job_broker, "synchronous", False):
            return self.wait_for_terminal(str(result), timeout=30.0)
        return "queued"

    def _schedule_due(self, routine: Routine, now: float) -> bool:
        expression = routine.trigger.split(":", 1)[1].strip()
        from datetime import datetime, timedelta

        current = datetime.fromtimestamp(now).astimezone()
        import re as _re

        last = self.store.last_success(routine.id)
        # Interval schedule: every N minutes/hours/days/weeks.
        interval_match = _re.fullmatch(
            r"every\s+(\d+)\s+(minutes?|hours?|days?|weeks?)", expression, _re.IGNORECASE
        )
        if interval_match:
            amount = int(interval_match.group(1))
            multiplier = {
                "minute": 60.0,
                "minutes": 60.0,
                "hour": 3600.0,
                "hours": 3600.0,
                "day": 86400.0,
                "days": 86400.0,
                "week": 604800.0,
                "weeks": 604800.0,
            }[interval_match.group(2).lower()]
            interval = amount * multiplier
            if not last or not last.finished_at:
                return False
            return now >= last.finished_at + interval

        clock_match = _re.fullmatch(
            r"every\s+(day|weekday|week)(?:\s+at\s+(.+))?", expression, _re.IGNORECASE
        )
        if not clock_match:
            return False
        unit, clock = clock_match.group(1).lower(), clock_match.group(2)
        if not clock:
            if not last or not last.finished_at:
                return False
            interval = {"day": 86400.0, "week": 604800.0, "weekday": 86400.0}[unit]
            return now >= last.finished_at + interval
        try:
            from virinda.core.natural_commands import parse_due_time

            zone_name = getattr(current.tzinfo, "key", None) or str(current.tzinfo)
            # Build today's clock target directly so passed times remain today's
            # occurrence instead of being rolled forward by parse_due_time.
            target_ts = parse_due_time(
                f"at {clock}",
                now=current.replace(hour=0, minute=0, second=0, microsecond=0),
                timezone=zone_name,
            )
            candidate = datetime.fromtimestamp(target_ts, current.tzinfo)
            for _ in range(8):
                if unit == "weekday" and candidate.weekday() >= 5:
                    candidate += timedelta(days=1)
                    continue
                if candidate > current:
                    return False
                if not last or not last.finished_at or candidate.timestamp() > last.finished_at:
                    return candidate.timestamp() <= now
                candidate += timedelta(days=1 if unit != "week" else 7)
            return False
        except Exception:
            return False

    def _due_match(self, routine: Routine, now: float) -> bool:
        if routine.trigger.startswith("at:"):
            try:
                return float(routine.trigger.split(":", 1)[1].strip()) <= now
            except ValueError:
                return False
        if routine.trigger.startswith("every:"):
            try:
                return float(routine.trigger.split(":", 1)[1].strip()) <= now
            except ValueError:
                return False
        if routine.trigger.startswith("schedule:"):
            return self._schedule_due(routine, now)
        return False

    def run_due(self, now: float | None = None) -> list[str]:
        now = now if now is not None else time.time()
        actions = []
        for routine in self.store.list():
            if not routine.enabled or not self._due_match(routine, now):
                continue
            if self.store.has_active_run(routine.id):
                continue
            if routine.trigger.startswith("at:"):
                status = self._dispatch_status(routine, trigger_context={"now": now})
                if self.job_broker is None and status == "succeeded":
                    self.store.disable(routine.id)
                if status in {"succeeded", "pending_approval", "queued"}:
                    actions.append(routine.id)
            elif routine.trigger.startswith("every:"):
                interval = float(routine.trigger.split(":", 1)[1].strip())
                status = self._dispatch_status(routine, trigger_context={"now": now})
                if status in {"succeeded", "pending_approval", "queued"}:
                    if self.job_broker is None:
                        self.store.save(
                            Routine(
                                routine.id,
                                routine.name,
                                f"every:{now + max(1.0, interval)}",
                                routine.action,
                                True,
                                routine.retry_limit,
                                routine.retry_backoff_seconds,
                                routine.require_approval,
                            )
                        )
                    actions.append(routine.id)
            elif routine.trigger.startswith("schedule:"):
                status = self._dispatch_status(routine, trigger_context={"now": now})
                if status in {"succeeded", "pending_approval", "queued"}:
                    actions.append(routine.id)
        return actions

    def _interpolate(self, value: str, trigger_context: dict[str, Any] | None) -> str:
        context = {}
        if self.context_provider:
            try:
                context.update(self.context_provider())
            except Exception:
                pass
        context.update(trigger_context or {})

        def lookup(match: re.Match[str]) -> str:
            path = match.group(1).strip().split(".")
            current: Any = context
            for part in path:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return ""
            return str(current)

        return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", lookup, value)

    def _actions(
        self, action: str, trigger_context: dict[str, Any] | None = None
    ) -> list[tuple[bool, str, str]]:
        action = self._interpolate(action, trigger_context)
        result = []
        for raw in [item.strip() for item in action.split("||") if item.strip()]:
            if ":" not in raw:
                raise ValueError("routine action must use kind:payload syntax")
            kind, payload = raw.split(":", 1)
            approve = False
            if kind == "approve":
                if not payload.startswith("tool:"):
                    raise ValueError("approve action must wrap a tool")
                kind = "tool"
                payload = payload.split(":", 1)[1]
                approve = True
            if kind not in {"notify", "tool"}:
                raise ValueError(f"unsupported routine action: {kind}")
            result.append((approve, kind, payload))
        return result

    def explain(
        self, routine: Routine, *, trigger_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return a side-effect-free execution plan for a routine.

        The result is intentionally serializable and does not create a run record,
        request an approval token, invoke a tool, or emit a notification.
        """
        actions = self._actions(routine.action, trigger_context)
        steps: list[dict[str, Any]] = []
        requires_approval = routine.require_approval
        for index, (approved_action, kind, payload) in enumerate(actions, start=1):
            if kind == "notify":
                title, _, body = payload.partition("|")
                steps.append(
                    {
                        "index": index,
                        "kind": "notify",
                        "title": title or routine.name,
                        "body": body or payload,
                        "approval_required": False,
                    }
                )
                continue
            name, _, raw = payload.partition("|")
            kwargs = json.loads(raw) if raw else {}
            needs_approval = routine.require_approval or approved_action
            requires_approval = requires_approval or needs_approval
            steps.append(
                {
                    "index": index,
                    "kind": "tool",
                    "tool": name,
                    "kwargs": kwargs,
                    "approval_required": needs_approval,
                }
            )
        conflicts = [asdict(item) for item in self.store.conflicts(routine, exclude_id=routine.id)]
        return {
            "routine": asdict(routine),
            "steps": steps,
            "requires_approval": requires_approval,
            "conflicts": conflicts,
            "will_execute": bool(routine.enabled and not conflicts),
            "side_effects": [
                "notification" if step["kind"] == "notify" else "tool" for step in steps
            ],
        }

    def dry_run(
        self, routine: Routine, *, trigger_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Alias for :meth:`explain` kept as an explicit product-facing operation."""
        return self.explain(routine, trigger_context=trigger_context)

    def execute(
        self,
        routine: Routine,
        *,
        trigger_context: dict[str, Any] | None = None,
        approved_run: bool = False,
        run_id: str | None = None,
    ) -> str:
        run_id = run_id or uuid4().hex
        existing = next((run for run in self.store.runs(limit=500) if run.id == run_id), None)
        if existing is not None:
            if existing.routine_id != routine.id:
                raise ValueError("run id belongs to a different routine")
            if existing.status == "succeeded":
                return "succeeded"
            if existing.status == "pending_approval" and not approved_run:
                return "pending_approval"
            if existing.status == "failed" and not approved_run:
                # A broker redelivery of a failed attempt is allowed to retry through
                # the routine's normal retry policy. Preserve the original start time.
                started = existing.started_at
            else:
                started = existing.started_at
        else:
            started = time.time()
        run = RoutineRun(run_id, routine.id, "running", 1, started)
        self.store.record_run(run)
        self._emit(
            "routine.started",
            {
                "run_id": run_id,
                "routine_id": routine.id,
                "name": routine.name,
                "trigger": routine.trigger,
            },
        )
        actions = self._actions(routine.action, trigger_context)
        for approved_action, kind, payload in actions:
            if kind == "notify":
                title, _, body = payload.partition("|")
                self.notify(title or routine.name, body or payload)
                continue
            name, _, raw = payload.partition("|")
            kwargs = json.loads(raw) if raw else {}
            needs_approval = routine.require_approval or approved_action
            if needs_approval and not approved_run:
                if not self.approval_requester:
                    self.store.update_run(
                        run_id,
                        status="failed",
                        finished_at=time.time(),
                        error="approval requester unavailable",
                    )
                    return "failed"
                token_info = self.approval_requester(name)
                self.store.update_run(
                    run_id,
                    status="pending_approval",
                    finished_at=None,
                    error=None,
                    approval_required=True,
                )
                self._emit(
                    "routine.approval_required",
                    {
                        "run_id": run_id,
                        "routine_id": routine.id,
                        "tool": name,
                        "approval": {k: v for k, v in token_info.items() if k != "token"},
                    },
                )
                return "pending_approval"
        attempts = max(1, routine.retry_limit + 1)
        last_error = None
        for attempt in range(1, attempts + 1):
            self.store.update_run(
                run_id,
                attempt=attempt,
                status="running",
                error=None,
                approval_required=False,
                finished_at=None,
            )
            try:
                for approved_action, kind, payload in actions:
                    if kind == "notify":
                        continue
                    name, _, raw = payload.partition("|")
                    kwargs = json.loads(raw) if raw else {}
                    self.tool_executor(name, approved=approved_run or approved_action, **kwargs)
                self.store.update_run(
                    run_id,
                    status="succeeded",
                    attempt=attempt,
                    finished_at=time.time(),
                    error=None,
                    approval_required=False,
                )
                if routine.trigger.startswith("at:"):
                    self.store.disable(routine.id)
                self._emit(
                    "routine.completed",
                    {
                        "run_id": run_id,
                        "routine_id": routine.id,
                        "status": "succeeded",
                        "attempt": attempt,
                    },
                )
                return "succeeded"
            except Exception as exc:
                last_error = str(exc)
                if attempt < attempts and routine.retry_backoff_seconds:
                    self._emit(
                        "routine.retry",
                        {
                            "run_id": run_id,
                            "routine_id": routine.id,
                            "attempt": attempt,
                            "error": last_error,
                        },
                    )
                    time.sleep(min(30.0, routine.retry_backoff_seconds * attempt))
        self.store.update_run(
            run_id,
            status="failed",
            attempt=attempts,
            finished_at=time.time(),
            error=last_error,
            approval_required=False,
        )
        self._emit(
            "routine.failed", {"run_id": run_id, "routine_id": routine.id, "error": last_error}
        )
        return "failed"

    def resume_approved(self, run_id: str) -> str:
        runs = [r for r in self.store.runs(limit=500) if r.id == run_id]
        if not runs:
            raise KeyError(run_id)
        prior = runs[0]
        routine = self.store.get(prior.routine_id)
        if routine is None:
            raise KeyError(prior.routine_id)
        return self.dispatch(routine, approved_run=True, run_id=run_id)


@dataclass(frozen=True, slots=True)
class AudioDevice:
    name: str
    kind: str
    source: str
    default: bool = False


def list_audio_devices() -> list[AudioDevice]:
    devices: list[AudioDevice] = []
    commands = [
        ("input", "arecord", ["-L"]),
        ("output", "aplay", ["-L"]),
    ]
    for kind, executable, args in commands:
        if not shutil.which(executable):
            continue
        try:
            output = subprocess.check_output(
                [executable, *args], text=True, stderr=subprocess.DEVNULL, timeout=3
            )
        except (OSError, subprocess.SubprocessError):
            continue
        for line in output.splitlines():
            if line and not line.startswith(" ") and not line.startswith("\t"):
                devices.append(AudioDevice(line.strip(), kind, line.strip(), False))
    return devices


def choose_audio_device(
    devices: list[AudioDevice], preferred: str | None = None
) -> AudioDevice | None:
    if not devices:
        return None
    if preferred:
        for item in devices:
            if preferred.lower() in item.name.lower() or preferred.lower() in item.source.lower():
                return item
    return devices[0]


def summarize_notifications(items: list[Notification]) -> str:
    unread = [n for n in items if not n.read]
    if not unread:
        return "No unread notifications."
    return " ".join(f"{n.title}: {n.body}" for n in unread[:10])


class BrowserSearch:
    """Minimal configurable search adapter; defaults to DuckDuckGo HTML when enabled."""

    def __init__(self, endpoint: str = "https://html.duckduckgo.com/html/") -> None:
        self.endpoint = endpoint

    def search(self, query: str, limit: int = 5) -> list[dict[str, str]]:
        if not query.strip():
            raise ValueError("query is required")
        url = self.endpoint + "?" + urllib.parse.urlencode({"q": query})
        html = fetch_url(url, 512_000)
        matches = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        results = []
        for href, title in matches[:limit]:
            title = re.sub(r"<[^>]+>", "", title)
            results.append({"title": title, "url": urllib.parse.unquote(href)})
        return results


class DesktopContextCollector:
    def collect(self) -> ContextSignals:
        active = None
        if shutil.which("xdotool"):
            try:
                wid = subprocess.check_output(
                    ["xdotool", "getactivewindow"], text=True, timeout=1
                ).strip()
                active = (
                    subprocess.check_output(
                        ["xdotool", "getwindowname", wid], text=True, timeout=1
                    ).strip()
                    or None
                )
            except (OSError, subprocess.SubprocessError):
                pass
        if active is None and shutil.which("swaymsg"):
            try:
                raw = subprocess.check_output(["swaymsg", "-t", "get_tree"], text=True, timeout=1)
                titles = re.findall(r'"name":"([^"]+)"', raw)
                active = titles[0] if titles else None
            except (OSError, subprocess.SubprocessError):
                pass
        headset = None
        if shutil.which("wpctl"):
            try:
                text = subprocess.check_output(["wpctl", "status"], text=True, timeout=2).lower()
                headset = "headset" in text or "headphones" in text
            except (OSError, subprocess.SubprocessError):
                pass
        return ContextSignals(active_application=active, headset_connected=headset)


class OpenAICompatibleVisionProvider:
    """Optional OpenAI-compatible vision adapter for local or remote multimodal models."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 90.0) -> None:
        self.base_url, self.api_key, self.model, self.timeout = (
            base_url.rstrip("/"),
            api_key,
            model,
            timeout,
        )

    def analyze(self, image: MultimodalInput, prompt: str) -> str:
        if not isinstance(image.content, (bytes, bytearray)):
            raise ValueError("image content must be bytes")
        import base64

        encoded = base64.b64encode(bytes(image.content)).decode("ascii")
        mime = image.metadata.get("mime", "image/png")
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{encoded}"},
                            },
                        ],
                    }
                ],
                "stream": False,
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        try:
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("invalid vision response") from exc


def capture_camera_input(path: Path, device: str = "/dev/video0") -> MultimodalInput:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg"):
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "v4l2", "-i", device, "-frames:v", "1", str(path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=8,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"camera capture failed: {exc}") from exc
        return MultimodalInput(
            "image", str(path), path.read_bytes(), {"path": str(path), "mime": "image/png"}
        )
    raise RuntimeError("ffmpeg is required for camera capture")


class SecureSatelliteClient:
    """Simple HMAC-authenticated JSON-line transport for a future HiveMind/OVOS bridge."""

    def __init__(self, host: str, port: int, secret: bytes, timeout: float = 5.0) -> None:
        import hmac

        self.host, self.port, self.secret, self.timeout, self._hmac = (
            host,
            port,
            secret,
            timeout,
            hmac,
        )

    def send(self, envelope: SatelliteEnvelope) -> None:
        envelope.validate()
        payload = envelope.canonical_bytes()
        sig = self._hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
        data = json.dumps({"payload": asdict(envelope), "hmac": sig}) + "\n"
        import socket

        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.sendall(data.encode())

    def close(self) -> None:
        return None


def briefing(
    alerts: list[Alert],
    notifications: list[Notification],
    signals: ContextSignals,
    *,
    profile: UserProfile | None = None,
    now: float | None = None,
) -> str:
    """Build a bounded, local daily briefing from durable/ephemeral state.

    The briefing intentionally avoids sensitive memory and never invokes the LLM.
    It is suitable for spoken delivery and desktop presentation.
    """
    now = now or time.time()
    parts: list[str] = []
    name = profile.display_name if profile else None
    if name:
        parts.append(f"Good to see you, {name}.")
    upcoming = [a for a in alerts if a.due_at >= now][:3]
    if upcoming:
        labels = []
        for alert in upcoming:
            delta = max(0, int(alert.due_at - now))
            if delta < 3600:
                when = f"in {max(1, delta // 60)} minutes"
            elif delta < 86400:
                when = f"in {delta // 3600} hours"
            else:
                when = f"in {delta // 86400} days"
            labels.append(f"{alert.title} {when}")
        parts.append("You have upcoming alerts: " + "; ".join(labels) + ".")
    unread = [n for n in notifications if not n.read]
    if unread:
        parts.append(
            f"You have {len(unread)} unread notification{'s' if len(unread) != 1 else ''}."
        )
    if signals.meeting_active:
        parts.append("Meeting mode is active.")
    if signals.active_application:
        parts.append(f"You are currently in {signals.active_application}.")
    if signals.quiet_hours:
        parts.append("Quiet hours are active.")
    return " ".join(parts) if parts else "Nothing urgent to report."
