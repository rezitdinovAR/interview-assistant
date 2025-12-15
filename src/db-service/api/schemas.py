from typing import List, Literal
from pydantic import BaseModel


class Chunks(BaseModel):
    texts: List[str]

class StatusResponse(BaseModel):
    status: Literal["OK", "ERROR"]

class SearchQuery(BaseModel):
    query: str
    top_k: int = 5
