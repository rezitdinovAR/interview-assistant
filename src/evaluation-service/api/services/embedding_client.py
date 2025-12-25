import os
from typing import List

import httpx

from api.core.config import settings


class EmbeddingClient:
    """Клиент для работы с сервисом эмбеддингов"""

    def __init__(self):
        self.embedding_url = os.getenv("EMBEDDING_URL", settings.embedding_url)
        self.embedding_model = os.getenv(
            "EMBEDDING_MODEL", settings.embedding_model
        )

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Получить эмбеддинги для списка текстов.

        Args:
            texts: Список текстов для эмбеддинга

        Returns:
            Список эмбеддингов (каждый эмбеддинг - список float)
        """
        if not texts:
            return []

        try:
            print(f"[EmbeddingClient] Отправка запроса к {self.embedding_url}/v1/embeddings для {len(texts)} текстов")
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.embedding_url}/v1/embeddings",
                    json={
                        "input": texts,
                        "model": self.embedding_model,
                    },
                )
                response.raise_for_status()
                data = response.json()
                print(f"[EmbeddingClient] Получено {len(data.get('data', []))} эмбеддингов")
                return [item["embedding"] for item in data["data"]]
        except httpx.HTTPError as e:
            print(f"[EmbeddingClient] HTTP ошибка: {e}")
            raise RuntimeError(
                f"Ошибка запроса к эмбеддеру ({self.embedding_url}): {e}"
            ) from e
        except Exception as e:
            print(f"[EmbeddingClient] Неожиданная ошибка: {e}")
            raise RuntimeError(
                f"Неожиданная ошибка при получении эмбеддингов: {e}"
            ) from e

