import os
from typing import Optional

import httpx

from api.core.config import settings


class ChatClient:
    """Клиент для работы с chat-service (RAG системой)"""

    def __init__(self):
        self.chat_service_url = os.getenv(
            "CHAT_SERVICE_URL", settings.chat_service_url
        )

    async def get_answer(
        self, question: str, user_id: str = "evaluation_user"
    ) -> tuple[Optional[str], list[str]]:
        """
        Получить ответ от RAG системы на вопрос.

        Args:
            question: Вопрос пользователя
            user_id: ID пользователя (по умолчанию "evaluation_user")

        Returns:
            tuple: (Ответ от RAG системы, список sources/контекстов)
        """
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.chat_service_url}/api/v1/chat",
                    json={
                        "user_id": user_id,
                        "message": question,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("message"), data.get("sources", [])
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"Ошибка запроса к chat-service: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Неожиданная ошибка при получении ответа от chat-service: {e}"
            ) from e

    async def reset_context(self, user_id: str = "evaluation_user") -> None:
        """
        Сбросить контекст диалога для пользователя.

        Args:
            user_id: ID пользователя
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.chat_service_url}/api/v1/reset",
                    json={"user_id": user_id},
                )
                response.raise_for_status()
        except Exception as e:
            # Логируем, но не прерываем выполнение
            print(f"Предупреждение: не удалось сбросить контекст: {e}")

