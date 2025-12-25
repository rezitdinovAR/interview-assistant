from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения"""

    app_name: str = "RAG Evaluation Service"
    app_version: str = "1.0.0"
    debug: bool = False

    embedding_url: str = "http://158.160.168.247:8081"
    embedding_model: str = "Qwen3-Embedding-8B"

    chat_service_url: str = "http://host.docker.internal:8084"

    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_model_name: Optional[str] = None

    questions_csv_path: str = "/workspace/data/questions.csv"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
