from fastapi import HTTPException, Request, status

from app.config import Settings
from app.connectors.slack import SlackConnector


def require_admin_token(x_admin_token: str | None, settings: Settings) -> None:
    """Validate the admin token for privileged endpoints."""

    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token.")


def require_event_secret(x_event_secret: str | None, settings: Settings) -> None:
    """Validate an optional shared secret for inbound event routes."""

    if settings.inbound_event_secret and x_event_secret != settings.inbound_event_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid event secret.")


async def verify_slack_request(request: Request, settings: Settings, connector: SlackConnector) -> None:
    """Validate Slack signatures when the signing secret is configured."""

    if not settings.slack_signing_secret:
        return
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")
    if not connector.verify_signature(timestamp=timestamp, signature=signature, body=body):
        raise HTTPException(status_code=401, detail="Invalid Slack signature.")
