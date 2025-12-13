from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import uvicorn

from .routers import router


app = FastAPI(
    description=main_description,
    openapi_tags=tags_metadata
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(router)