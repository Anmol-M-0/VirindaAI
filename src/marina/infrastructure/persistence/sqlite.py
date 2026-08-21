from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from time import time
from typing import Any

from marina.domain.events import EVENT_TYPES, AssistantEvent
from marina.domain.models import Message, Session


class SQLiteConversationStore:
    """Durable local store with one connection, protected for concurrent runtime threads."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                provider TEXT NOT NULL DEFAULT 'echo',
                model TEXT NOT NULL DEFAULT 'offline-demo',
                mode TEXT NOT NULL DEFAULT 'text',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                generation_id INTEGER NOT NULL,
                sequence INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id, id);
            CREATE INDEX IF NOT EXISTS idx_events_session_id ON events(session_id, id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_events_session_generation_sequence
                ON events(session_id, generation_id, sequence);
            """
        )
        self._migrate_schema()
        self._conn.commit()

    def _migrate_schema(self) -> None:
        """Apply additive migrations for databases created by earlier releases."""
        version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(sessions)").fetchall()}

        if "provider" not in columns:
            self._conn.execute(
                "ALTER TABLE sessions ADD COLUMN provider TEXT NOT NULL DEFAULT 'echo'"
            )
        if "model" not in columns:
            self._conn.execute(
                "ALTER TABLE sessions ADD COLUMN model TEXT NOT NULL DEFAULT 'offline-demo'"
            )
        if "mode" not in columns:
            self._conn.execute(
                "ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'text'"
            )

        if version < 2:
            self._conn.execute("PRAGMA user_version=2")

    def ensure_session(self, session: Session) -> None:
        with self._lock:
            now = time()
            self._conn.execute(
                """INSERT INTO sessions(id, provider, model, mode, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET provider=excluded.provider,
                       model=excluded.model, mode=excluded.mode, updated_at=excluded.updated_at""",
                (session.id, session.provider, session.model, session.mode.value, now, now),
            )
            self._conn.commit()

    def append_message(self, session_id: str, message: Message) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, message.role, message.content, message.created_at),
            )
            self._touch(session_id)
            self._conn.commit()

    def append_event(self, session_id: str, event: AssistantEvent) -> None:
        payload = json.dumps(event.to_payload(), sort_keys=True, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """INSERT INTO events(session_id, generation_id, sequence, event_type,
                                      payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, generation_id, sequence) DO UPDATE SET
                       event_type=excluded.event_type,
                       payload_json=excluded.payload_json,
                       created_at=excluded.created_at""",
                (session_id, event.generation_id, event.sequence, type(event).__name__, payload, event.created_at),
            )
            self._touch(session_id)
            self._conn.commit()

    def _touch(self, session_id: str) -> None:
        self._conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (time(), session_id))

    def load_messages(self, session_id: str) -> list[Message]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content, created_at FROM messages WHERE session_id=? ORDER BY id", (session_id,)
            ).fetchall()
        return [Message(role=row[0], content=row[1], created_at=row[2]) for row in rows]

    def list_sessions(self) -> list[str]:
        with self._lock:
            return [row[0] for row in self._conn.execute("SELECT id FROM sessions ORDER BY updated_at DESC")]

    def load_latest_session(self) -> Session | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, provider, model, mode FROM sessions ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        from marina.domain.models import InteractionMode, LifecycleState
        mode_value = {
            "text": InteractionMode.CONVERSATION.value,
            "voice": InteractionMode.CONVERSATION.value,
        }.get(row[3], row[3])
        try:
            mode = InteractionMode(mode_value)
        except ValueError:
            mode = InteractionMode.CONVERSATION
        return Session(
            id=row[0],
            generation_id=0,
            lifecycle=LifecycleState.IDLE,
            mode=mode,
            provider=row[1] or "echo",
            model=row[2] or "offline-demo",
        )

    def load_events(self, session_id: str, limit: int = 100) -> list[AssistantEvent]:
        if limit < 1:
            return []
        with self._lock:
            rows = self._conn.execute(
                """SELECT generation_id, sequence, event_type, payload_json, created_at
                   FROM events WHERE session_id=? ORDER BY id DESC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
        events: list[AssistantEvent] = []
        for generation, sequence, event_type, payload_json, created_at in reversed(rows):
            cls = EVENT_TYPES.get(event_type)
            if cls is None:
                continue
            payload: dict[str, Any] = json.loads(payload_json)
            payload.pop("generation_id", None)
            payload.pop("sequence", None)
            payload.pop("created_at", None)
            events.append(cls(generation_id=generation, sequence=sequence, created_at=created_at, **payload))
        return events

    def health(self) -> dict[str, object]:
        with self._lock:
            row = self._conn.execute("PRAGMA integrity_check").fetchone()
            message_count = self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            event_count = self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            session_count = self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        return {
            "path": str(self.path),
            "integrity": row[0],
            "sessions": session_count,
            "messages": message_count,
            "events": event_count,
            "journal_mode": "wal",
        }

    def backup(self, destination: Path) -> Path:
        destination = Path(destination).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            destination_conn = sqlite3.connect(destination)
            try:
                self._conn.backup(destination_conn)
                destination_conn.commit()
            finally:
                destination_conn.close()
        return destination

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    @property
    def lock(self) -> RLock:
        return self._lock

    def close(self) -> None:
        with self._lock:
            self._conn.close()
