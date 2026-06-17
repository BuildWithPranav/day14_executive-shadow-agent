from datetime import UTC, datetime

import structlog

from app.config import Settings
from app.connectors.email import EmailConnector
from app.connectors.slack import SlackConnector
from app.llm import build_shadow_model
from app.models import IncomingMessage
from app.repositories import ShadowRepository
from app.schemas import (
    ActorRequest,
    ContextSnippet,
    DraftDetailResponse,
    EmailEventPayload,
    IngestResponse,
    IncomingMessageRecord,
    KnowledgeIngestRequest,
    SentMessageIngestRequest,
    SlackEventPayload,
)


class ShadowService:
    """Application service that ingests context, drafts replies, and dispatches approved sends."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = structlog.get_logger(__name__)
        self.repository = ShadowRepository(settings.database_path)
        self.model = build_shadow_model(settings)
        self.slack = SlackConnector(settings)
        self.email = EmailConnector(settings)

    async def ingest_knowledge(self, request: KnowledgeIngestRequest) -> IngestResponse:
        """Add a knowledge base document."""

        record_id = await self.repository.ingest_knowledge(
            source_type=request.source_type,
            title=request.title,
            content=request.content,
            tags=request.tags,
        )
        return IngestResponse(id=record_id, status="stored")

    async def ingest_sent_message(self, request: SentMessageIngestRequest) -> IngestResponse:
        """Add a historical sent message for style learning."""

        record_id = await self.repository.ingest_sent_message(
            channel=request.channel,
            sender=request.sender,
            recipient=request.recipient,
            subject=request.subject,
            body=request.body,
            created_at=request.created_at,
        )
        return IngestResponse(id=record_id, status="stored")

    async def handle_slack_event(self, request: SlackEventPayload) -> DraftDetailResponse:
        """Process an inbound Slack message into a saved draft."""

        incoming = IncomingMessage(
            channel="slack",
            source_message_id=request.ts,
            sender=request.user_name or request.user_id,
            recipient=None,
            thread_key=request.thread_ts or request.ts,
            subject=None,
            body=request.text,
            metadata={
                "channel_id": request.channel_id,
                "channel_name": request.channel_name,
                "user_id": request.user_id,
                "ts": request.ts,
                "thread_ts": request.thread_ts,
            },
            created_at=datetime.now(UTC),
        )
        return await self._shadow_incoming_message(incoming)

    async def handle_email_event(self, request: EmailEventPayload) -> DraftDetailResponse:
        """Process an inbound email into a saved draft."""

        incoming = IncomingMessage(
            channel="email",
            source_message_id=request.message_id,
            sender=request.from_address,
            recipient=request.to_address,
            thread_key=request.thread_key or request.message_id,
            subject=request.subject,
            body=request.body,
            metadata={
                "message_id": request.message_id,
                "from_address": request.from_address,
                "to_address": request.to_address,
                "thread_key": request.thread_key,
            },
            created_at=datetime.now(UTC),
        )
        return await self._shadow_incoming_message(incoming)

    async def _shadow_incoming_message(self, incoming: IncomingMessage) -> DraftDetailResponse:
        """Run retrieval, drafting, and preview creation for an inbound message."""

        incoming_id = await self.repository.create_incoming_message(incoming)
        query_text = f"{incoming.subject or ''} {incoming.body}"
        knowledge_matches = await self.repository.search_knowledge(query_text, limit=4)
        style_matches = await self.repository.search_style_messages(query_text, limit=4)
        combined_context = [
            ContextSnippet(
                source=item.source,
                title=item.title,
                content=item.content,
                score=item.score,
            )
            for item in [*knowledge_matches, *style_matches]
        ]
        incoming_record = IncomingMessageRecord(
            id=incoming_id,
            channel=incoming.channel,
            source_message_id=incoming.source_message_id,
            sender=incoming.sender,
            recipient=incoming.recipient,
            thread_key=incoming.thread_key,
            subject=incoming.subject,
            body=incoming.body,
            metadata=incoming.metadata,
            status="received",
            created_at=incoming.created_at,
        )
        decision = await self.model.generate_draft(
            incoming_message=incoming_record,
            retrieved_context=combined_context,
        )
        draft_id = await self.repository.create_draft(
            incoming_message_id=incoming_id,
            channel=incoming.channel,
            recipient=incoming.sender if incoming.channel == "email" else None,
            subject=decision.subject,
            body=decision.body,
            rationale=decision.rationale,
            urgency=decision.urgency,
            confidence=decision.confidence,
            retrieved_context=combined_context,
        )

        preview_location = f"dashboard://draft/{draft_id}"
        if incoming.channel == "slack":
            try:
                preview_location = await self.slack.send_preview(
                    preview_text=f"Executive Shadow draft\n\n{decision.body}",
                    channel_id=str(incoming.metadata.get("channel_id", "")),
                    thread_ts=incoming.thread_key,
                ) or preview_location
            except Exception:
                self.logger.exception("slack_preview_failed", draft_id=draft_id)

        await self.repository.set_draft_preview_location(draft_id, preview_location)
        detail = await self.repository.get_draft_detail(draft_id)
        if detail is None:
            raise RuntimeError("Draft was created but could not be reloaded.")
        return detail

    async def list_drafts(self, status: str | None) -> list:
        """List drafts by status."""

        return await self.repository.list_drafts(status)

    async def get_draft(self, draft_id: int) -> DraftDetailResponse:
        """Fetch a single draft by id."""

        detail = await self.repository.get_draft_detail(draft_id)
        if detail is None:
            raise ValueError(f"Draft {draft_id} not found.")
        return detail

    async def approve_draft(self, draft_id: int, actor: ActorRequest) -> DraftDetailResponse:
        """Approve and dispatch a draft."""

        detail = await self.get_draft(draft_id)
        if detail.draft.status != "pending":
            raise ValueError(f"Draft {draft_id} is not pending.")

        if detail.draft.channel == "slack":
            channel_id = str(detail.incoming_message.metadata.get("channel_id", ""))
            if not channel_id:
                raise RuntimeError("Slack channel_id missing from inbound metadata.")
            await self.slack.send_reply(
                channel_id=channel_id,
                text=detail.draft.body,
                thread_ts=detail.incoming_message.thread_key,
            )
        else:
            subject = detail.draft.subject or self._default_reply_subject(detail.incoming_message.subject)
            await self.email.send_email(
                to_address=detail.incoming_message.sender,
                subject=subject,
                body=detail.draft.body,
            )

        await self.repository.update_draft_status(
            draft_id=draft_id,
            status="sent",
            actor=actor.actor,
            note=actor.note,
            sent_at=datetime.now(UTC),
        )
        await self.repository.mark_incoming_status(detail.incoming_message.id, "answered")
        return await self.get_draft(draft_id)

    async def reject_draft(self, draft_id: int, actor: ActorRequest) -> DraftDetailResponse:
        """Reject a draft without sending it."""

        detail = await self.get_draft(draft_id)
        await self.repository.update_draft_status(
            draft_id=draft_id,
            status="rejected",
            actor=actor.actor,
            note=actor.note,
        )
        await self.repository.mark_incoming_status(detail.incoming_message.id, "awaiting_rewrite")
        return await self.get_draft(draft_id)

    def _default_reply_subject(self, subject: str | None) -> str:
        """Return a safe reply subject when the model omits one."""

        value = subject or "Follow-up"
        return value if value.lower().startswith("re:") else f"Re: {value}"
