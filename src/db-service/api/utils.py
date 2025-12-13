import os
import uuid
import json
from typing import List

import requests
from weaviate import Client


embed_url = os.getenv("EMBEDDING_URL")
embed_model = os.getenv("EMBEDDING_MODEL")
reranker_url = os.getenv("RERANKER_URL")
reranker_model = os.getenv("RERANKER_MODEL")


def ensure_schema(client: Client, name: str) -> None:
    """Создать класс в Weaviate, если его еще нет."""
    if not client.schema.exists(name):
        schema = {
            "class": name,
            "vectorizer": "none",  # вектор задаем сами
            "properties": [
                {
                    "name": "text",
                    "dataType": ["text"],
                }
            ],
        }
        client.schema.create_class(schema)


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """Получить эмбеддинги из vLLM‑эмбеддера."""
    try:
        resp = requests.post(
            f"{embed_url}/v1/embeddings",
            json={
                "input": texts,
                "model": embed_model,
            },
            timeout=60,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Ошибка запроса к эмбеддеру: {e}")

    if resp.status_code != 200:
        raise RuntimeError(
            f"Эмбеддер вернул {resp.status_code}: {resp.text[:500]}"
        )

    data = resp.json()
    return [item["embedding"] for item in data["data"]]


async def rerank(
    query: str,
    documents: List[str],
    top_k: int = 7
) -> List[dict]:
    """
    Реранк кандидатов
    Возвращает список словарей [{"index": int, "score": float}, ...]
    отсортированных по score по убыванию и обрезанных до top_k.
    """
    if not documents:
        return []

    try:
        resp = requests.post(
            f"{rerank_url}/v1/score",
            json={
                "model": rerank_model,
                "input": {
                    "query": query,
                    "documents": documents,
                },
                # Если твой сервер поддерживает ограничение количества прямо в запросе,
                # можно дополнительно передать top_k здесь, но это опционально:
                # "top_k": top_k,
            },
            timeout=60,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Ошибка запроса к реранкеру: {e}")

    if resp.status_code != 200:
        raise RuntimeError(
            f"Реранкер вернул {resp.status_code}: {resp.text[:500]}"
        )

    data = resp.json()
    items = data.get("data", [])

    # Фильтруем и сортируем результаты, затем обрезаем до top_k
    valid = [
        item
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("index"), int)
        and 0 <= item["index"] < len(documents)
        and isinstance(item.get("score"), (int, float))
    ]

    valid_sorted = sorted(valid, key=lambda x: x["score"], reverse=True)
    return valid_sorted[:top_k]
