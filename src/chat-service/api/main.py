from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.core.config import settings
from api.core.dependencies import set_llm, cleanup_llm
from api.services import LLMGraphMemoryWithRAG
from api.routers import chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управление жизненным циклом приложения.
    Инициализация LLM при старте и очистка при остановке.
    """
    # Startup: инициализация LLM сервиса
    llm_service = LLMGraphMemoryWithRAG()
    set_llm(llm_service)

    yield

    # Shutdown: очистка ресурсов
    await cleanup_llm()


# Создание FastAPI приложения
app = FastAPI(
    title=settings.app_name,
    description="Chat service with RAG for interview preparation",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Подключаем роутеры
app.include_router(chat_router)


@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Проверка здоровья приложения"""
    return {
        "status": "healthy",
        "service": settings.app_name
    }
