from pathlib import Path
import sqlite3

from marina.infrastructure.persistence.sqlite import SQLiteConversationStore


def test_old_session_schema_is_migrated(tmp_path: Path):
    path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            generation_id INTEGER NOT NULL,
            sequence INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        INSERT INTO sessions VALUES ('legacy', 'text', 1.0, 2.0);
        PRAGMA user_version=1;
        """
    )
    conn.commit()
    conn.close()

    store = SQLiteConversationStore(path)
    restored = store.load_latest_session()
    assert restored is not None
    assert restored.id == "legacy"
    assert restored.provider == "echo"
    assert restored.model == "offline-demo"
    assert restored.mode.value == "conversation"
    assert store.health()["integrity"] == "ok"
    store.close()
