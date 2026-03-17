from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql://allen:allen@localhost:5432/allen_shop"
    DASHSCOPE_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    # 允许使用 Bot 的飞书 open_id，多个用逗号分隔，留空则不限制
    FEISHU_WHITELIST: str = ""
    OSS_BUCKET: str = ""
    OSS_REGION: str = ""
    OSS_ENDPOINT: str = ""
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_PUBLIC_BASE_URL: str = ""

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql://") and not value.startswith("postgresql+psycopg2://"):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL.")
        return value

    @property
    def feishu_whitelist_ids(self) -> List[str]:
        if not self.FEISHU_WHITELIST:
            return []
        return [uid.strip() for uid in self.FEISHU_WHITELIST.split(",") if uid.strip()]

    @property
    def oss_enabled(self) -> bool:
        return all(
            [
                self.OSS_BUCKET,
                self.OSS_ENDPOINT,
                self.OSS_ACCESS_KEY_ID,
                self.OSS_ACCESS_KEY_SECRET,
            ]
        )

    @property
    def oss_upload_host(self) -> str:
        if not self.oss_enabled:
            return ""
        endpoint = self.OSS_ENDPOINT.replace("https://", "").replace("http://", "").strip("/")
        return f"https://{self.OSS_BUCKET}.{endpoint}"

    @property
    def oss_public_base_url(self) -> str:
        return (self.OSS_PUBLIC_BASE_URL or self.oss_upload_host).rstrip("/")


settings = Settings()
