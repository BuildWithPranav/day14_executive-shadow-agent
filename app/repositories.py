import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from app.models import IncomingMessage, RetrievedItem
from app.schemas import ContextSnippet, DraftDetailResponse, DraftRecord, IncomingMessageRecord


TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _fts_query(text: str) -> str:
    tokens = TOKEN_RE.findall(text.lower())
    unique_tokens: list[str] = []
    for token in tokens:
        if token not in unique_tokens:
            unique_tokens.append(token)
    return " OR ".join(f'"{token}"*' for token in unique_tokens[:12])


class ShadowRepository:
    """Async repository wrapping SQLite persistence and retrieval."""

    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)

    async def ingest_knowledge(
        self,
        *,
        source_type: str,
        title: str,
        content: str,
        tags: list[str],
    ) -> int:
        """Insert a knowledge document and index it for search."""

        created_at = _now_iso()
        tags_json = json.dumps(tags, ensure_ascii=False)
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO knowledge_documents (source_type, title, content, tags_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source_type, title, content, tags_json, created_at),
            )
            doc_id = cursor.lastrowid
            await db.execute(
                "INSERT INTO knowledge_fts(rowid, title, content, tags) VALUES (?, ?, ?, ?)",
                (doc_id, title, content, " ".join(tags)),
            )
            await db.commit()
        return int(doc_id)

    async def ingest_sent_message(
        self,
        *,
        channel: str,
        sender: str,
        recipient: str,
        subject: str | None,
        body: str,
        created_at: datetime | None,
    ) -> int:
        """Insert a historical sent message and index it for style retrieval."""

        created_value = (created_at or datetime.now(UTC)).isoformat()
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO sent_messages (channel, sender, recipient, subject, body, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (channel, sender, recipient, subject, body, created_value),
            )
            message_id = cursor.lastrowid
            await db.execute(
                "INSERT INTO sent_message_fts(rowid, subject, body) VALUES (?, ?, ?)",
                (message_id, subject or "", body),
            )
            await db.commit()
        return int(message_id)

    async def create_incoming_message(self, message: IncomingMessage) -> int:
        """Persist an inbound message event."""

        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO incoming_messages (
                    channel, source_message_id, sender, recipient, thread_key,
                    subject, body, metadata_json, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.channel,
                    message.source_message_id,
                    message.sender,
                    message.recipient,
                    message.thread_key,
                    message.subject,
                    message.body,
                    json.dumps(message.metadata, ensure_ascii=False),
                    "received",
                    message.created_at.isoformat(),
                ),
            )
            incoming_id = cursor.lastrowid
            await db.commit()
        return int(incoming_id)

    async def search_knowledge(self, query: str, limit: int = 4) -> list[RetrievedItem]:
        """Search the knowledge base with SQLite FTS5."""

        fts_query = _fts_query(query)
        if not fts_query:
            return []
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT kd.title, kd.content, bm25(knowledge_fts) AS score
                FROM knowledge_fts
                JOIN knowledge_documents kd ON kd.id = knowledge_fts.rowid
                WHERE knowledge_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (fts_query, limit),
            )
            rows = await cursor.fetchall()
        return [
            RetrievedItem(
                source="knowledge",
                title=str(row["title"]),
                content=str(row["content"]),
                score=float(row["score"]),
            )
            for row in rows
        ]

    async def search_style_messages(self, query: str, limit: int = 4) -> list[RetrievedItem]:
        """Search prior sent messages for tone and phrasing examples."""

        fts_query = _fts_query(query)
        if not fts_query:
            return []
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT COALESCE(subject, 'Sent message') AS title, body, bm25(sent_message_fts) AS score
                FROM sent_message_fts
                JOIN sent_messages sm ON sm.id = sent_message_fts.rowid
                WHERE sent_message_fts MATCH ?
                ORDER BY score
                LIMIT ?
                """,
                (fts_query, limit),
            )
            rows = await cursor.fetchall()
        return [
            RetrievedItem(
                source="style",
                title=str(row["title"]),
                content=str(row["body"]),
                score=float(row["score"]),
            )
            for row in rows
        ]

    async def create_draft(
        self,
        *,
        incoming_message_id: int,
        channel: str,
        recipient: str | None,
        subject: str | None,
        body: str,
        rationale: str,
        urgency: str,
        confidence: float,
        retrieved_context: list[ContextSnippet],
    ) -> int:
        """Persist a generated draft."""

        created_at = _now_iso()
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO drafts (
                    incoming_message_id, channel, recipient, subject, body, rationale,
                    urgency, confidence, status, preview_location, approved_by,
                    approval_note, sent_at, retrieved_context_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incoming_message_id,
                    channel,
                    recipient,
                    subject,
                    body,
                    rationale,
                    urgency,
                    confidence,
                    "pending",
                    None,
                    None,
                    None,
                    None,
                    json.dumps([item.model_dump() for item in retrieved_context], ensure_ascii=False),
                    created_at,
                    created_at,
                ),
            )
            draft_id = cursor.lastrowid
            await db.commit()
        return int(draft_id)

    async def set_draft_preview_location(self, draft_id: int, preview_location: str | None) -> None:
        """Update preview metadata after mirroring to Slack or dashboard."""

        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                "UPDATE drafts SET preview_location = ?, updated_at = ? WHERE id = ?",
                (preview_location, _now_iso(), draft_id),
            )
            await db.commit()

    async def update_draft_status(
        self,
        *,
        draft_id: int,
        status: str,
        actor: str,
        note: str | None,
        sent_at: datetime | None = None,
    ) -> None:
        """Update the workflow status for a draft."""

        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """
                UPDATE drafts
                SET status = ?, approved_by = ?, approval_note = ?, sent_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    actor,
                    note,
                    sent_at.isoformat() if sent_at else None,
                    _now_iso(),
                    draft_id,
                ),
            )
            await db.commit()

    async def mark_incoming_status(self, incoming_message_id: int, status: str) -> None:
        """Update the inbound message workflow status."""

        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                "UPDATE incoming_messages SET status = ? WHERE id = ?",
                (status, incoming_message_id),
            )
            await db.commit()

    async def get_draft_detail(self, draft_id: int) -> DraftDetailResponse | None:
        """Fetch a single draft with its inbound message and retrieval context."""

        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT
                    d.id AS draft_id,
                    d.incoming_message_id,
                    d.channel AS draft_channel,
                    d.recipient AS draft_recipient,
                    d.subject AS draft_subject,
                    d.body AS draft_body,
                    d.rationale,
                    d.urgency,
                    d.confidence,
                    d.status AS draft_status,
                    d.preview_location,
                    d.approved_by,
                    d.approval_note,
                    d.sent_at,
                    d.retrieved_context_json,
                    d.created_at AS draft_created_at,
                    d.updated_at AS draft_updated_at,
                    i.id AS incoming_id,
                    i.channel AS incoming_channel,
                    i.source_message_id,
                    i.sender,
                    i.recipient,
                    i.thread_key,
                    i.subject,
                    i.body,
                    i.metadata_json,
                    i.status AS incoming_status,
                    i.created_at AS incoming_created_at
                FROM drafts d
                JOIN incoming_messages i ON i.id = d.incoming_message_id
                WHERE d.id = ?
                """,
                (draft_id,),
            )
            row = await cursor.fetchone()

        if row is None:
            return None

        context_items = [ContextSnippet.model_validate(item) for item in json.loads(row["retrieved_context_json"])]
        draft = DraftRecord(
            id=int(row["draft_id"]),
            incoming_message_id=int(row["incoming_message_id"]),
            channel=str(row["draft_channel"]),
            recipient=row["draft_recipient"],
            subject=row["draft_subject"],
            body=str(row["draft_body"]),
            rationale=str(row["rationale"]),
            urgency=str(row["urgency"]),
            confidence=float(row["confidence"]),
            status=str(row["draft_status"]),
            preview_location=row["preview_location"],
            approved_by=row["approved_by"],
            approval_note=row["approval_note"],
            sent_at=datetime.fromisoformat(row["sent_at"]) if row["sent_at"] else None,
            created_at=datetime.fromisoformat(str(row["draft_created_at"])),
            updated_at=datetime.fromisoformat(str(row["draft_updated_at"])),
        )
        incoming = IncomingMessageRecord(
            id=int(row["incoming_id"]),
            channel=str(row["incoming_channel"]),
            source_message_id=row["source_message_id"],
            sender=str(row["sender"]),
            recipient=row["recipient"],
            thread_key=row["thread_key"],
            subject=row["subject"],
            body=str(row["body"]),
            metadata=json.loads(row["metadata_json"]),
            status=str(row["incoming_status"]),
            created_at=datetime.fromisoformat(str(row["incoming_created_at"])),
        )
        return DraftDetailResponse(
            draft=draft,
            incoming_message=incoming,
            retrieved_context=context_items,
        )

    async def list_drafts(self, status: str | None = None) -> list[DraftRecord]:
        """List drafts filtered by workflow status."""

        query = (
            "SELECT id, incoming_message_id, channel, recipient, subject, body, rationale, urgency, confidence, status, preview_location, approved_by, approval_note, sent_at, created_at, updated_at FROM drafts"
        )
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY updated_at DESC"

        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()

        return [
            DraftRecord(
                id=int(row["id"]),
                incoming_message_id=int(row["incoming_message_id"]),
                channel=str(row["channel"]),
                recipient=row["recipient"],
                subject=row["subject"],
                body=str(row["body"]),
                rationale=str(row["rationale"]),
                urgency=str(row["urgency"]),
                confidence=float(row["confidence"]),
                status=str(row["status"]),
                preview_location=row["preview_location"],
                approved_by=row["approved_by"],
                approval_note=row["approval_note"],
                sent_at=datetime.fromisoformat(row["sent_at"]) if row["sent_at"] else None,
                created_at=datetime.fromisoformat(str(row["created_at"])),
                updated_at=datetime.fromisoformat(str(row["updated_at"])),
            )
            for row in rows
        ]
