from typing import Optional
from fastapi import HTTPException

from api.core.config import settings


# Глобальная переменная для хранения экземпляра LLM
_llm_instance: Optional["LLMGraphMemoryWithRAG"] = None


def get_llm() -> "LLMGraphMemoryWithRAG":
    """
    Dependency для получения экземпляра LLM.
    Используется в FastAPI роутерах.
    """
    global _llm_instance
    if _llm_instance is None:
        raise HTTPException(status_code=500, detail="LLM service not initialized")
    return _llm_instance


def set_llm(llm: "LLMGraphMemoryWithRAG") -> None:
    """
    Устанавливает глобальный экземпляр LLM.
    Вызывается при старте приложения.
    """
    global _llm_instance
    _llm_instance = llm


async def cleanup_llm() -> None:
    """
    Очищает ресурсы LLM.
    Вызывается при остановке приложения.
    """
    global _llm_instance
    if _llm_instance:
        await _llm_instance.close()
        _llm_instance = None
