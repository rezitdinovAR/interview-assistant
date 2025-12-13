from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import uvicorn

from .routers import router


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(router)