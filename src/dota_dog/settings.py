from __future__ import annotations

from functools import cached_property

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    bot_token: str = Field(alias="BOT_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")
    opendota_base_url: str = Field(
        default="https://api.opendota.com/api",
        alias="OPENDOTA_BASE_URL",
    )
    opendota_api_key: str | None = Field(default=None, alias="OPENDOTA_API_KEY")
    poll_interval_minutes: int = Field(default=15, alias="POLL_INTERVAL_MINUTES")
    default_timezone: str = Field(default="UTC", alias="DEFAULT_TIMEZONE")
    allowed_telegram_user_ids: str = Field(default="", alias="ALLOWED_TELEGRAM_USER_IDS")
    telegram_admin_check_enabled: bool = Field(default=True, alias="TELEGRAM_ADMIN_CHECK_ENABLED")
    opendota_max_retries: int = Field(default=3, alias="OPENDOTA_MAX_RETRIES")
    telegram_send_max_retries: int = Field(default=3, alias="TELEGRAM_SEND_MAX_RETRIES")
    retry_backoff_seconds: float = Field(default=1.0, alias="RETRY_BACKOFF_SECONDS")
    constants_sync_interval_hours: int = Field(default=24, alias="CONSTANTS_SYNC_INTERVAL_HOURS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql+")

    @cached_property
    def allowed_user_ids(self) -> set[int]:
        if not self.allowed_telegram_user_ids.strip():
            return set()
        return {
            int(item.strip()) for item in self.allowed_telegram_user_ids.split(",") if item.strip()
        }


def load_settings() -> Settings:
    return Settings.model_validate({})
