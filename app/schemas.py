from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ChannelName = Literal["slack", "email"]
DraftStatus = Literal["pending", "approved", "rejected", "sent"]
UrgencyLevel = Literal["low", "normal", "high", "critical"]


class KnowledgeIngestRequest(BaseModel):
    """Knowledge base document payload."""

    source_type: str = Field(default="policy", min_length=1)
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class SentMessageIngestRequest(BaseModel):
    """Historical sent message payload used for style learning."""

    channel: ChannelName
    sender: str = Field(min_length=1)
    recipient: str = Field(min_length=1)
    subject: str | None = None
    body: str = Field(min_length=1)
    created_at: datetime | None = None


class SlackEventPayload(BaseModel):
    """Simplified Slack inbound event payload."""

    channel_id: str = Field(min_length=1)
    channel_name: str | None = None
    user_id: str = Field(min_length=1)
    user_name: str | None = None
    text: str = Field(min_length=1)
    ts: str = Field(min_length=1)
    thread_ts: str | None = None


class EmailEventPayload(BaseModel):
    """Generic inbound email event payload."""

    message_id: str = Field(min_length=1)
    from_address: str = Field(min_length=1)
    to_address: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    thread_key: str | None = None


class ActorRequest(BaseModel):
    """Approval or rejection actor payload."""

    actor: str = Field(min_length=1)
    note: str | None = None


class AgentDecision(BaseModel):
    """Normalized model output for triage and draft generation."""

    urgency: UrgencyLevel = "normal"
    intent: str = Field(min_length=1)
    subject: str | None = None
    body: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class ContextSnippet(BaseModel):
    """Retrieved context item used during drafting."""

    source: str
    title: str
    content: str
    score: float


class DraftRecord(BaseModel):
    """Draft record returned by API routes."""

    id: int
    incoming_message_id: int
    channel: ChannelName
    recipient: str | None
    subject: str | None
    body: str
    rationale: str
    urgency: UrgencyLevel
    confidence: float
    status: DraftStatus
    preview_location: str | None = None
    approved_by: str | None = None
    approval_note: str | None = None
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class IncomingMessageRecord(BaseModel):
    """Stored inbound message details."""

    id: int
    channel: ChannelName
    source_message_id: str | None
    sender: str
    recipient: str | None
    thread_key: str | None
    subject: str | None
    body: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime


class DraftDetailResponse(BaseModel):
    """Detailed draft payload including inbound message and retrieval context."""

    draft: DraftRecord
    incoming_message: IncomingMessageRecord
    retrieved_context: list[ContextSnippet] = Field(default_factory=list)


class IngestResponse(BaseModel):
    """Generic ingestion response."""

    id: int
    status: str


class HealthResponse(BaseModel):
    """Service health payload."""

    status: str
    app: str
    environment: str
    llm_backend: str
    dry_run_sends: bool
