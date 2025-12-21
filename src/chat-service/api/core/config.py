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

    # LLM
    llm_base_url: str
    llm_api_key: str
    llm_model_name: str

    # Proxy settings (optional)
    proxy_url: Optional[str] = None  # Format: socks5://user:pass@host:port or http://host:port

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
