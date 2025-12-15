from fastapi import APIRouter, HTTPException, Depends
import logging
import traceback

from api.schemas import ChatRequest, ChatResponse, ResetRequest, StatusResponse
from api.services import LLMGraphMemoryWithRAG
from api.core.dependencies import get_llm

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    llm: LLMGraphMemoryWithRAG = Depends(get_llm)
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
            status_code=500,
            detail=f"Error processing chat message: {str(e)}"
        )


@router.post("/reset", response_model=StatusResponse)
async def reset_context(
    request: ResetRequest,
    llm: LLMGraphMemoryWithRAG = Depends(get_llm)
) -> StatusResponse:
    """
    Сбросить контекст диалога пользователя.

    Удаляет всю историю сообщений пользователя из Redis.
    """
    try:
        await llm.reset_context(request.user_id)
        return StatusResponse(
            status="OK",
            message=f"Context for user {request.user_id} has been reset"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error resetting context: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "service": "chat-service"
    }
