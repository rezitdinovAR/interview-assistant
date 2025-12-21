from executor import run_code
from fastapi import FastAPI, HTTPException
from leetcode import get_random_question
from pydantic import BaseModel

app = FastAPI()


class DifficultyRequest(BaseModel):
    difficulty: str = "EASY"


class ExecuteRequest(BaseModel):
    code: str
    test_code: str


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


@app.get("/health")
def health():
    return {"status": "ok"}
