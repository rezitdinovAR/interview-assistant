from executor import run_code
from fastapi import FastAPI, HTTPException
from leetcode import (
    get_problem_by_slug,
    get_problems_list,
    get_random_question,
)
from pydantic import BaseModel

app = FastAPI()


class DifficultyRequest(BaseModel):
    difficulty: str = "EASY"


class ExecuteRequest(BaseModel):
    code: str
    test_code: str


class SearchRequest(BaseModel):
    keyword: str


class SlugRequest(BaseModel):
    slug: str


class ListRequest(BaseModel):
    limit: int = 10
    skip: int = 0
    difficulty: str = "EASY"
    category: str = "algorithms"


@app.post("/random-question")
async def random_q(req: DifficultyRequest):
    try:
        data = await get_random_question(req.difficulty)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/execute")
async def execute(req: ExecuteRequest):
    result = await run_code(req.code, req.test_code)
    return result


@app.post("/problem")
async def get_problem(req: SlugRequest):
    try:
        data = await get_problem_by_slug(req.slug)
        return data
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/list")
async def list_problems(req: ListRequest):
    try:
        data = await get_problems_list(
            category=req.category,
            limit=req.limit,
            skip=req.skip,
            difficulty=req.difficulty,
        )
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
