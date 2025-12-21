from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str

    chat_service_url: str = "http://chat-service:8080"
    leetcode_service_url: str = "http://leetcode-service:8000"

    redis_uri: str = "redis://redis:6379/0"

    admin_ids: str = ""

    limit_user_per_hour: int = 10
    limit_bot_per_hour: int = 50

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def get_admin_ids(self) -> List[int]:
        if not self.admin_ids:
            return []
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
