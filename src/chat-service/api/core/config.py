import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения"""

    # API Settings
    app_name: str = "Interview Assistant Chat Service"
    app_version: str = "1.0.0"
    debug: bool = False

    # Redis
    redis_uri: str = "redis://redis:6379"

    # DB Service
    db_service_url: str = "http://api:8080"

    # OpenAI
    openai_api_key: str
    openai_base_url: str = "https://api.proxyapi.ru/openai/v1"
    openai_model: str = "gpt-4o-mini-2024-07-18"

    # RAG Settings
    top_k_documents: int = 5
    max_tokens: int = 10000
    max_history: int = 10

    # System Prompt
    system_prompt_path: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False


# Глобальный экземпляр настроек
settings = Settings()
