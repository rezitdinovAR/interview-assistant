from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class MetricResult(BaseModel):
    """Результат одной метрики"""

    metric_name: str = Field(..., description="Название метрики")
    score: float = Field(..., description="Значение метрики (0-1)")
    description: Optional[str] = Field(None, description="Описание метрики")


class EvaluationRequest(BaseModel):
    """Запрос на оценку ответов"""

    questions: List[str] = Field(..., description="Список вопросов")
    ground_truths: List[str] = Field(..., description="Эталонные ответы")
    answers: List[str] = Field(..., description="Ответы модели")
    contexts: Optional[List[List[str]]] = Field(
        None, description="Контексты для каждого ответа (опционально)"
    )
    metrics: Optional[List[str]] = Field(
        None,
        description="Список метрик для вычисления. Если не указан, используются все доступные метрики",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "questions": ["Что такое машинное обучение?"],
                "ground_truths": ["Машинное обучение - это..."],
                "answers": ["Машинное обучение представляет собой..."],
                "contexts": [["Контекст 1", "Контекст 2"]],
                "metrics": ["faithfulness", "answer_relevancy", "context_precision"],
            }
        }


class EvaluationResponse(BaseModel):
    """Ответ с результатами оценки"""

    results: List[MetricResult] = Field(..., description="Результаты метрик")
    average_score: Optional[float] = Field(
        None, description="Средний балл по всем метрикам"
    )
    total_samples: int = Field(..., description="Количество оцененных примеров")

    class Config:
        json_schema_extra = {
            "example": {
                "results": [
                    {
                        "metric_name": "faithfulness",
                        "score": 0.85,
                        "description": "Метрика верности ответа контексту",
                    },
                    {
                        "metric_name": "answer_relevancy",
                        "score": 0.92,
                        "description": "Релевантность ответа вопросу",
                    },
                ],
                "average_score": 0.885,
                "total_samples": 10,
            }
        }


class StatusResponse(BaseModel):
    """Статус операции"""

    status: str = Field(..., description="Статус")
    message: Optional[str] = Field(None, description="Сообщение")

