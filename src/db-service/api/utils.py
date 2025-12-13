import os
import uuid
import json
from typing import List
import logging

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
            "vectorizer": "none",
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

    results: List[Dict] = []

    for idx, doc in enumerate(documents):
        payload = {
            "model": reranker_model,
            "text_1": query,
            "text_2": doc,
        }

        resp = requests.post(f"{reranker_url}/v1/score", json=payload)

        if resp.status_code != 200:
            raise RuntimeError(
                f"Реранкер вернул {resp.status_code}: {resp.text[:500]}"
            )

        data = resp.json()

        if "score" in data:
            score = float(data["score"])
        elif "data" in data and data["data"]:
            score = float(data["data"][0].get("score", 0.0))
        else:
            raise RuntimeError(
                f"Не удалось получить score из ответа реранкера: {data}"
            )

        results.append({"index": idx, "score": score})

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
