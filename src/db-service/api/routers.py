import os
import uuid

from fastapi import APIRouter, HTTPException
from weaviate import Client

from .utils import ensure_schema, embed_texts, rerank
from .schemas import Chunks, StatusResponse, SearchQuery


db_url = os.getenv("WEAVIATE_URL")
client = Client(db_url)
ensure_schema(client, "doc")

router = APIRouter()


@router.post("/add_chunks", response_model=StatusResponse)
async def add_chunks(chunks: Chunks) -> StatusResponse:
    if not chunks.texts:
        raise HTTPException(status_code=400, detail="chunks is empty")

    try:
        vectors = await embed_texts(chunks.texts)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if len(vectors) != len(chunks.texts):
        raise HTTPException(
            status_code=500,
            detail="Количество эмбеддингов не совпадает с количеством чанков",
        )

    try:
        with client.batch(batch_size=100) as batch:
            for text, vector in zip(chunks.texts, vectors):
                batch.add_data_object(
                    data_object={"text": text},
                    class_name="doc",
                    uuid=str(uuid.uuid4()),
                    vector=vector,
                )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Ошибка записи в Weaviate: {e}"
        )

    return StatusResponse(status="OK")


@router.post("/retrieve", response_model=Chunks)
async def retrieve(req: SearchQuery) -> Chunks:
    if not req.query:
        raise HTTPException(status_code=400, detail="query is empty")

    top_k = max(1, req.top_k)

    try:
        query_vec = await embed_texts([req.query])[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        near_vector = {"vector": query_vec}
        res = (
            client.query.get("doc", ["text"])
            .with_near_vector(near_vector)
            .with_limit(30)
            .do()
        )
        objects = res["data"]["Get"].get("doc", [])
        candidates = [obj["text"] for obj in objects]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Ошибка поиска в Weaviate: {e}"
        )

    if not candidates:
        return Chunks(texts=[])

    try:
        ranked = await rerank(req.query, candidates, top_k=top_k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    result = [
        candidates[item["index"]]
        for item in ranked
    ]

    return Chunks(texts=result)
