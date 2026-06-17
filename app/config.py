from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "executive-shadow-agent"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    database_path: str = "data/shadow.db"
    admin_token: str = "change-me"
    inbound_event_secret: str | None = None

    llm_backend: Literal["heuristic", "openai"] = "heuristic"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    request_timeout_seconds: float = 45.0
    max_retries: int = 3

    slack_bot_token: str | None = None
    slack_signing_secret: str | None = None
    slack_preview_user_id: str | None = None
    slack_preview_channel_id: str | None = None

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True

    dry_run_sends: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
