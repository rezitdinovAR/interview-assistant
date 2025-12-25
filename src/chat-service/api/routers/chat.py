import logging
import os
import traceback
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.core.dependencies import get_llm
from api.schemas import (
    ChatRequest,
    ChatResponse,
    ProfileUpdateRequest,
    ResetRequest,
    StatusResponse,
)
from api.services import LLMGraphMemoryWithRAG

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest, llm: LLMGraphMemoryWithRAG = Depends(get_llm)
) -> ChatResponse:
    """
    Отправить сообщение в чат.

    Принимает сообщение от пользователя, получает контекст из RAG,
    и возвращает ответ от LLM.
    """
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        response_text = await llm.ask(request.user_id, request.message)
        return ChatResponse(user_id=request.user_id, message=response_text)
    except Exception as e:
        logger.error(f"Error processing chat message: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f"Error processing chat message: {str(e)}"
        )


@router.post("/reset", response_model=StatusResponse)
async def reset_context(
    request: ResetRequest, llm: LLMGraphMemoryWithRAG = Depends(get_llm)
) -> StatusResponse:
    """
    Сбросить контекст диалога пользователя.

    Удаляет всю историю сообщений пользователя из Redis.
    """
    try:
        await llm.reset_context(request.user_id)
        return StatusResponse(
            status="OK",
            message=f"Context for user {request.user_id} has been reset",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error resetting context: {str(e)}"
        )


@router.post("/profile/update", response_model=StatusResponse)
async def update_profile(
    request: ProfileUpdateRequest, llm: LLMGraphMemoryWithRAG = Depends(get_llm)
) -> StatusResponse:
    """Обновить портрет пользователя на основе события"""
    try:
        new_profile = await llm.update_user_profile(
            request.user_id, request.activity_description
        )
        return StatusResponse(status="OK", message=new_profile)
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        return StatusResponse(status="Error", message=str(e))


@router.get("/dataset/download")
async def download_dataset():
    """Скачать датасет RAG"""
    file_path = "rag_dataset.jsonl"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Dataset is empty")

    return FileResponse(
        path=file_path,
        filename=f"rag_dataset_{datetime.now().strftime('%Y%m%d')}.jsonl",
        media_type="application/json",
    )


@router.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {"status": "healthy", "service": "chat-service"}
