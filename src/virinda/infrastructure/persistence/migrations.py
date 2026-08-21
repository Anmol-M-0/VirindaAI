from __future__ import annotations

import sqlite3
from typing import Callable

CURRENT_SCHEMA_VERSION = 2


class MigrationError(RuntimeError):
    """Raised when a schema migration fails."""


class IncompatibleSchemaError(RuntimeError):
    """Raised when the database schema version is newer than this release supports."""


def _migration_v1(conn: sqlite3.Connection) -> None:
    """Version 1: Base sessions, messages, and events tables."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
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


def _migration_v2(conn: sqlite3.Connection) -> None:
    """Version 2: Add provider, model, and mode columns to sessions table."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "provider" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN provider TEXT NOT NULL DEFAULT 'echo'")
    if "model" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN model TEXT NOT NULL DEFAULT 'offline-demo'")
    if "mode" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'text'")


MIGRATIONS: list[tuple[int, Callable[[sqlite3.Connection], None]]] = [
    (1, _migration_v1),
    (2, _migration_v2),
]


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current PRAGMA user_version of the database."""
    cursor = conn.execute("PRAGMA user_version")
    row = cursor.fetchone()
    return int(row[0]) if row else 0


def verify_integrity(conn: sqlite3.Connection) -> None:
    """Verify structural and foreign key integrity of the SQLite database."""
    # 1. Structural integrity check
    integrity_rows = conn.execute("PRAGMA integrity_check").fetchall()
    if not integrity_rows or integrity_rows[0][0].lower() != "ok":
        errors = [r[0] for r in integrity_rows]
        raise MigrationError(f"SQLite structural integrity check failed: {errors}")

    # 2. Foreign key integrity check
    fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
    if fk_errors:
        raise MigrationError(f"SQLite foreign key check failed with violations: {fk_errors}")


def migrate_database(conn: sqlite3.Connection) -> int:
    """Apply all pending migrations sequentially within an isolated transaction.

    Returns the resulting schema version.
    """
    version = get_schema_version(conn)

    if version > CURRENT_SCHEMA_VERSION:
        raise IncompatibleSchemaError(
            f"Database schema version {version} is newer than supported version {CURRENT_SCHEMA_VERSION}. "
            "Please upgrade VirindaAI to access this database."
        )

    if version == CURRENT_SCHEMA_VERSION:
        verify_integrity(conn)
        return version

    # Ensure foreign keys are enabled
    conn.execute("PRAGMA foreign_keys = ON")

    for target_version, migration_fn in MIGRATIONS:
        if version < target_version:
            try:
                # Executes in a savepoint/transaction
                migration_fn(conn)
                conn.execute(f"PRAGMA user_version = {target_version}")
                conn.commit()
                version = target_version
            except Exception as exc:
                conn.rollback()
                raise MigrationError(
                    f"Failed migrating schema to version {target_version}: {exc}"
                ) from exc

    verify_integrity(conn)
    return version
