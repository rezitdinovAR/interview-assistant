from typing import List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Запрос для отправки сообщения в чат"""

    user_id: str = Field(..., description="ID пользователя", min_length=1)
    message: str = Field(..., description="Сообщение пользователя", min_length=1)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user123",
                    "message": "Что такое замыкание в JavaScript?",
                }
            ]
        }
    }


class ChatResponse(BaseModel):
    """Ответ от чат-бота"""

    user_id: str = Field(..., description="ID пользователя")
    message: str = Field(..., description="Ответ от LLM")
    sources: List[str] = []

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user123",
                    "message": "Замыкание (closure) в JavaScript...",
                    "sources": [
                        "https://developer.mozilla.org/ru/docs/Web/JavaScript/Closures",
                        "https://learn.javascript.ru/closure",
                    ],
                }
            ]
        }
    }


class ResetRequest(BaseModel):
    """Запрос для сброса контекста пользователя"""

    user_id: str = Field(..., description="ID пользователя", min_length=1)

    model_config = {"json_schema_extra": {"examples": [{"user_id": "user123"}]}}


class StatusResponse(BaseModel):
    """Статус операции"""

    status: str = Field(..., description="Статус выполнения")
    message: Optional[str] = Field(None, description="Дополнительное сообщение")

    model_config = {
        "json_schema_extra": {
            "examples": [{"status": "OK", "message": "Context has been reset"}]
        }
    }


class ProfileUpdateRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    activity_description: str = Field(..., min_length=1)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "user_id": "user123",
                    "activity_description": "Решил задачу Two Sum с первой попытки",
                }
            ]
        }
    }
