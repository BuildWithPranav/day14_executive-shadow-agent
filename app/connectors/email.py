from email.message import EmailMessage

import aiosmtplib

from app.config import Settings


class EmailConnector:
    """Async SMTP connector for approved email sends."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_email(self, *, to_address: str, subject: str, body: str) -> str:
        """Send an approved email or return a dry-run transport URI."""

        if self.settings.dry_run_sends:
            return f"smtp-dry-run://{to_address}"
        if not self.settings.smtp_host or not self.settings.smtp_from:
            raise RuntimeError("SMTP_HOST and SMTP_FROM are required for live email sends.")

        message = EmailMessage()
        message["From"] = self.settings.smtp_from
        message["To"] = to_address
        message["Subject"] = subject
        message.set_content(body)

        await aiosmtplib.send(
            message,
            hostname=self.settings.smtp_host,
            port=self.settings.smtp_port,
            username=self.settings.smtp_username,
            password=self.settings.smtp_password,
            start_tls=self.settings.smtp_use_tls,
        )
        return f"smtp://{to_address}"
