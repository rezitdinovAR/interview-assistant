import httpx
from typing import List
from pydantic import BaseModel

from api.core.config import settings


class SearchQuery(BaseModel):
    """Схема запроса для поиска в db-service"""

    query: str
    top_k: int = 5


class Chunks(BaseModel):
    """Схема ответа с документами из db-service"""

    texts: List[str]


class DBServiceClient:
    """Клиент для взаимодействия с db-service"""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or settings.db_service_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def retrieve_documents(self, query: str, top_k: int = None) -> List[str]:
        """
        Получает релевантные документы из db-service

        Args:
            query: Поисковый запрос
            top_k: Количество документов для получения

        Returns:
            Список текстов документов
        """
        if top_k is None:
            top_k = settings.top_k_documents

        url = f"{self.base_url}/retrieve"
        payload = SearchQuery(query=query, top_k=top_k)

        try:
            response = await self.client.post(url, json=payload.model_dump())
            response.raise_for_status()

            chunks = Chunks(**response.json())
            return chunks.texts
        except httpx.HTTPError as e:
            raise Exception(f"Error retrieving documents from db-service: {e}")

    async def close(self):
        """Закрывает соединение с клиентом"""
        await self.client.aclose()
