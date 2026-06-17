from pathlib import Path

import aiosqlite

from app.config import Settings


async def init_db(settings: Settings) -> None:
    """Initialize SQLite tables and FTS indexes."""

    db_path = Path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
            USING fts5(title, content, tags)
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                subject TEXT,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS sent_message_fts
            USING fts5(subject, body)
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS incoming_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                source_message_id TEXT,
                sender TEXT NOT NULL,
                recipient TEXT,
                thread_key TEXT,
                subject TEXT,
                body TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incoming_message_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                recipient TEXT,
                subject TEXT,
                body TEXT NOT NULL,
                rationale TEXT NOT NULL,
                urgency TEXT NOT NULL,
                confidence REAL NOT NULL,
                status TEXT NOT NULL,
                preview_location TEXT,
                approved_by TEXT,
                approval_note TEXT,
                sent_at TEXT,
                retrieved_context_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (incoming_message_id) REFERENCES incoming_messages(id)
            )
            """
        )
        await db.commit()
