from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class IncomingMessage:
    """Internal representation of an inbound Slack or email message."""

    channel: str
    source_message_id: str | None
    sender: str
    recipient: str | None
    thread_key: str | None
    subject: str | None
    body: str
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(slots=True)
class RetrievedItem:
    """FTS retrieval result."""

    source: str
    title: str
    content: str
    score: float
