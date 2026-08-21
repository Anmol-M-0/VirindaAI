from __future__ import annotations

from marina.domain.models import Message, Session
from marina.infrastructure.persistence.sqlite import SQLiteConversationStore


def test_health_and_backup(tmp_path):
    source = SQLiteConversationStore(tmp_path / "source.sqlite3")
    try:
        session = Session()
        source.ensure_session(session)
        source.append_message(session.id, Message("user", "hello"))
        health = source.health()
        assert health["integrity"] == "ok"
        assert health["messages"] == 1
        backup = source.backup(tmp_path / "backup.sqlite3")
    finally:
        source.close()

    restored = SQLiteConversationStore(backup)
    try:
        assert [m.content for m in restored.load_messages(session.id)] == ["hello"]
    finally:
        restored.close()
