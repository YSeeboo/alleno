from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql://allen:allen@localhost:5432/allen_shop"
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WHITELIST: str = ""
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = ""

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql://") and not value.startswith("postgresql+psycopg2://"):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL.")
        return value

    @property
    def telegram_whitelist_ids(self) -> List[int]:
        if not self.TELEGRAM_WHITELIST:
            return []
        return [int(uid.strip()) for uid in self.TELEGRAM_WHITELIST.split(",") if uid.strip()]


settings = Settings()
