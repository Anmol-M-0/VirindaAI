from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from virinda.domain.events import (
    LifecycleChanged,
    ResponseCompleted,
    ResponseDelta,
)
from virinda.domain.models import InteractionMode, Message, Session
from virinda.infrastructure.persistence.migrations import (
    CURRENT_SCHEMA_VERSION,
    IncompatibleSchemaError,
    get_schema_version,
    migrate_database,
    verify_integrity,
)
from virinda.infrastructure.persistence.sqlite import SQLiteConversationStore


def test_fresh_database_migration(tmp_path: Path):
    db_path = tmp_path / "fresh.sqlite3"
    conn = sqlite3.connect(db_path)
    version = migrate_database(conn)
    assert version == CURRENT_SCHEMA_VERSION
    assert get_schema_version(conn) == CURRENT_SCHEMA_VERSION

    # Verify tables created
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "sessions" in tables
    assert "messages" in tables
    assert "events" in tables

    # Verify structural and foreign key integrity
    verify_integrity(conn)
    conn.close()


def test_legacy_v1_migration_to_v2(tmp_path: Path):
    db_path = tmp_path / "legacy_v1.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    # Create a pure v1 legacy database
    conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        );
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            generation_id INTEGER NOT NULL,
            sequence INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        );
        PRAGMA user_version = 1;
        """
    )

    # Insert legacy sample records
    conn.execute(
        "INSERT INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)",
        ("sess_legacy_001", 1700000000.0, 1700000010.0),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        ("sess_legacy_001", "user", "What is the time?", 1700000001.0),
    )
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        ("sess_legacy_001", "assistant", "It is 12:00 PM.", 1700000002.0),
    )
    conn.execute(
        "INSERT INTO events (session_id, generation_id, sequence, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            "sess_legacy_001",
            1,
            1,
            "TranscriptFinal",
            json.dumps({"text": "What is the time?"}),
            1700000001.0,
        ),
    )
    conn.commit()

    assert get_schema_version(conn) == 1

    # Apply migration
    new_version = migrate_database(conn)
    assert new_version == CURRENT_SCHEMA_VERSION
    assert get_schema_version(conn) == CURRENT_SCHEMA_VERSION

    # Verify existing data is 100% preserved
    session_row = conn.execute(
        "SELECT id, provider, model, mode, created_at, updated_at FROM sessions WHERE id = 'sess_legacy_001'"
    ).fetchone()
    assert session_row[0] == "sess_legacy_001"
    assert session_row[1] == "echo"  # default value applied
    assert session_row[2] == "offline-demo"  # default value applied
    assert session_row[3] == "text"  # default value applied
    assert session_row[4] == 1700000000.0
    assert session_row[5] == 1700000010.0

    messages = conn.execute(
        "SELECT role, content FROM messages WHERE session_id = 'sess_legacy_001' ORDER BY id ASC"
    ).fetchall()
    assert len(messages) == 2
    assert messages[0] == ("user", "What is the time?")
    assert messages[1] == ("assistant", "It is 12:00 PM.")

    events = conn.execute(
        "SELECT event_type, generation_id, sequence FROM events WHERE session_id = 'sess_legacy_001'"
    ).fetchall()
    assert len(events) == 1
    assert events[0] == ("TranscriptFinal", 1, 1)

    verify_integrity(conn)
    conn.close()


def test_sqlite_conversation_store_integration(tmp_path: Path):
    db_path = tmp_path / "store_test.sqlite3"
    store = SQLiteConversationStore(db_path)
    assert store.schema_version == CURRENT_SCHEMA_VERSION

    # Write sessions, messages, events through store API
    session = Session(
        id="sess_live_100", provider="openai", model="gpt-4o", mode=InteractionMode.CONVERSATION
    )
    store.ensure_session(session)
    store.append_message("sess_live_100", Message("user", "Hello Virinda", 100.0))
    store.append_message("sess_live_100", Message("assistant", "Hello! How can I help?", 101.0))
    store.append_event(
        "sess_live_100",
        LifecycleChanged(generation_id=1, sequence=1, state="thinking", created_at=100.0),
    )
    store.append_event(
        "sess_live_100",
        ResponseDelta(generation_id=1, sequence=2, text="Hello! How can I help?", created_at=101.0),
    )
    store.append_event(
        "sess_live_100",
        ResponseCompleted(
            generation_id=1, sequence=3, text="Hello! How can I help?", created_at=102.0
        ),
    )

    # Re-open database with a new SQLiteConversationStore instance (testing idempotent load)
    store2 = SQLiteConversationStore(db_path)
    assert store2.schema_version == CURRENT_SCHEMA_VERSION
    loaded_messages = store2.load_messages("sess_live_100")
    assert len(loaded_messages) == 2
    assert loaded_messages[0].content == "Hello Virinda"
    assert loaded_messages[1].content == "Hello! How can I help?"

    loaded_events = store2.load_events("sess_live_100")
    assert len(loaded_events) == 3

    health = store2.health()
    assert health["integrity"] == "ok"
    assert health["sessions"] == 1
    assert health["messages"] == 2
    assert health["events"] == 3


def test_migration_idempotence(tmp_path: Path):
    db_path = tmp_path / "idempotent.sqlite3"
    conn = sqlite3.connect(db_path)
    v1 = migrate_database(conn)
    v2 = migrate_database(conn)
    v3 = migrate_database(conn)
    assert v1 == v2 == v3 == CURRENT_SCHEMA_VERSION
    verify_integrity(conn)
    conn.close()


def test_refusal_of_unknown_future_schema(tmp_path: Path):
    db_path = tmp_path / "future_schema.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version = 999")
    conn.commit()

    with pytest.raises(IncompatibleSchemaError) as exc_info:
        migrate_database(conn)

    assert "version 999 is newer than supported version" in str(exc_info.value)
    conn.close()
