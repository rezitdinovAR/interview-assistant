from pydantic import BaseModel, Field
from typing import Optional


class ChatRequest(BaseModel):
    """Запрос для отправки сообщения в чат"""

    user_id: str = Field(..., description="ID пользователя", min_length=1)
    message: str = Field(..., description="Сообщение пользователя", min_length=1)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user123",
                    "message": "Что такое замыкание в JavaScript?"
                }
            ]
        }
    }


class ChatResponse(BaseModel):
    """Ответ от чат-бота"""

    user_id: str = Field(..., description="ID пользователя")
    message: str = Field(..., description="Ответ от LLM")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user123",
                    "message": "Замыкание (closure) в JavaScript..."
                }
            ]
        }
    }


class ResetRequest(BaseModel):
    """Запрос для сброса контекста пользователя"""

    user_id: str = Field(..., description="ID пользователя", min_length=1)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user123"
                }
            ]
        }
    }


class StatusResponse(BaseModel):
    """Статус операции"""

    status: str = Field(..., description="Статус выполнения")
    message: Optional[str] = Field(None, description="Дополнительное сообщение")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "OK",
                    "message": "Context has been reset"
                }
            ]
        }
    }
