import json
from pathlib import Path
from typing import Literal

import structlog
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.db import init_db
from app.logging import configure_logging
from app.schemas import (
    ActorRequest,
    DraftDetailResponse,
    DraftRecord,
    EmailEventPayload,
    HealthResponse,
    IngestResponse,
    KnowledgeIngestRequest,
    SentMessageIngestRequest,
    SlackEventPayload,
)
from app.security import require_admin_token, require_event_secret, verify_slack_request
from app.service import ShadowService

settings = get_settings()
configure_logging(settings.log_level)
logger = structlog.get_logger(__name__)
service = ShadowService(settings)
app = FastAPI(title=settings.app_name, version="0.1.0")


@app.on_event("startup")
async def startup() -> None:
    """Initialize the local database on boot."""

    await init_db(settings)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health probe for the service."""

    return HealthResponse(
        status="ok",
        app=settings.app_name,
        environment=settings.environment,
        llm_backend=settings.llm_backend,
        dry_run_sends=settings.dry_run_sends,
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Serve the inline approval dashboard."""

    html = Path("app/ui/dashboard.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.post("/ingest/knowledge", response_model=IngestResponse)
async def ingest_knowledge(
    payload: KnowledgeIngestRequest,
    x_admin_token: str | None = Header(default=None),
) -> IngestResponse:
    """Ingest a policy or FAQ document."""

    require_admin_token(x_admin_token, settings)
    return await service.ingest_knowledge(payload)


@app.post("/ingest/sent-message", response_model=IngestResponse)
async def ingest_sent_message(
    payload: SentMessageIngestRequest,
    x_admin_token: str | None = Header(default=None),
) -> IngestResponse:
    """Ingest a prior sent message for tone learning."""

    require_admin_token(x_admin_token, settings)
    return await service.ingest_sent_message(payload)


@app.post("/events/slack", response_model=DraftDetailResponse)
async def slack_event(
    request: Request,
    x_event_secret: str | None = Header(default=None),
) -> DraftDetailResponse | dict[str, str]:
    """Handle a Slack event or simplified Slack payload."""

    require_event_secret(x_event_secret, settings)
    await verify_slack_request(request, settings, service.slack)

    raw_body = await request.body()
    payload_json = json.loads(raw_body.decode("utf-8"))
    if payload_json.get("type") == "url_verification":
        return {"challenge": str(payload_json.get("challenge", ""))}

    event_body = payload_json.get("event", payload_json)
    if event_body.get("subtype") == "bot_message":
        raise HTTPException(status_code=400, detail="Bot messages are ignored.")
    try:
        payload = SlackEventPayload(
            channel_id=event_body["channel_id"] if "channel_id" in event_body else event_body["channel"],
            channel_name=event_body.get("channel_name"),
            user_id=event_body["user_id"] if "user_id" in event_body else event_body["user"],
            user_name=event_body.get("user_name"),
            text=event_body["text"],
            ts=event_body["ts"],
            thread_ts=event_body.get("thread_ts"),
        )
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Missing Slack field: {exc}") from exc
    return await service.handle_slack_event(payload)


@app.post("/events/email", response_model=DraftDetailResponse)
async def email_event(
    payload: EmailEventPayload,
    x_event_secret: str | None = Header(default=None),
) -> DraftDetailResponse:
    """Handle a generic inbound email event."""

    require_event_secret(x_event_secret, settings)
    return await service.handle_email_event(payload)


@app.get("/drafts", response_model=list[DraftRecord])
async def list_drafts(
    status: Literal["pending", "approved", "rejected", "sent"] | None = None,
    x_admin_token: str | None = Header(default=None),
) -> list[DraftRecord]:
    """List drafts for the dashboard."""

    require_admin_token(x_admin_token, settings)
    return await service.list_drafts(status)


@app.get("/drafts/{draft_id}", response_model=DraftDetailResponse)
async def get_draft(draft_id: int, x_admin_token: str | None = Header(default=None)) -> DraftDetailResponse:
    """Return a single draft detail payload."""

    require_admin_token(x_admin_token, settings)
    try:
        return await service.get_draft(draft_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/drafts/{draft_id}/approve", response_model=DraftDetailResponse)
async def approve_draft(
    draft_id: int,
    payload: ActorRequest,
    x_admin_token: str | None = Header(default=None),
) -> DraftDetailResponse:
    """Approve and send a draft."""

    require_admin_token(x_admin_token, settings)
    try:
        return await service.approve_draft(draft_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("approve_draft_failed", draft_id=draft_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/drafts/{draft_id}/reject", response_model=DraftDetailResponse)
async def reject_draft(
    draft_id: int,
    payload: ActorRequest,
    x_admin_token: str | None = Header(default=None),
) -> DraftDetailResponse:
    """Reject a draft without sending it."""

    require_admin_token(x_admin_token, settings)
    try:
        return await service.reject_draft(draft_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
