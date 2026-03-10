from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "sqlite:///./allen_shop.db"
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WHITELIST: str = ""
    ANTHROPIC_API_KEY: str = ""

    @property
    def telegram_whitelist_ids(self) -> List[int]:
        if not self.TELEGRAM_WHITELIST:
            return []
        return [int(uid.strip()) for uid in self.TELEGRAM_WHITELIST.split(",") if uid.strip()]


settings = Settings()
