from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.core.config import settings
from api.core.dependencies import cleanup_llm, set_llm
from api.routers import chat_router
from api.services import LLMGraphMemoryWithRAG


@asynccontextmanager
async def lifespan(app: FastAPI):
    llm_service = LLMGraphMemoryWithRAG()

    await llm_service.initialize()

    set_llm(llm_service)

    yield

    await cleanup_llm()


app = FastAPI(
    title=settings.app_name,
    description="Chat service with RAG for interview preparation",
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}
