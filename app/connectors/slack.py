import hashlib
import hmac
import time
from typing import Any

import httpx

from app.config import Settings


class SlackConnector:
    """Async Slack API client for previews and approved replies."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_token = settings.slack_bot_token
        self.signing_secret = settings.slack_signing_secret

    def verify_signature(self, *, timestamp: str | None, signature: str | None, body: bytes) -> bool:
        """Verify Slack request signatures when configured."""

        if not self.signing_secret:
            return True
        if not timestamp or not signature:
            return False
        if abs(time.time() - int(timestamp)) > 300:
            return False
        basestring = f"v0:{timestamp}:{body.decode('utf-8')}".encode("utf-8")
        digest = "v0=" + hmac.new(
            self.signing_secret.encode("utf-8"),
            basestring,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(digest, signature)

    async def send_preview(
        self,
        *,
        preview_text: str,
        channel_id: str,
        thread_ts: str | None,
    ) -> str | None:
        """Mirror a preview to Slack when configured."""

        target_channel = self.settings.slack_preview_channel_id or channel_id
        if self.settings.dry_run_sends:
            return f"slack-preview://{target_channel}/{thread_ts or 'root'}"
        if not self.api_token:
            return None

        payload: dict[str, Any] = {
            "channel": target_channel,
            "text": preview_text,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts
        if self.settings.slack_preview_user_id:
            payload["text"] = f"Preview for <@{self.settings.slack_preview_user_id}>\n\n{preview_text}"

        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {self.api_token}"},
                json=payload,
            )
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack preview failed: {data}")
        return f"slack://{data.get('channel')}/{data.get('ts')}"

    async def send_reply(self, *, channel_id: str, text: str, thread_ts: str | None) -> str:
        """Send an approved Slack response."""

        if self.settings.dry_run_sends:
            return f"slack-send://{channel_id}/{thread_ts or 'root'}"
        if not self.api_token:
            raise RuntimeError("SLACK_BOT_TOKEN is required for live Slack sends.")

        payload: dict[str, Any] = {"channel": channel_id, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
            response = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={"Authorization": f"Bearer {self.api_token}"},
                json=payload,
            )
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack send failed: {data}")
        return f"slack://{data.get('channel')}/{data.get('ts')}"
