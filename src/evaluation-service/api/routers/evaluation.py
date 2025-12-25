import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from api.core.config import settings
from api.schemas.evaluation import (
    EvaluationRequest,
    EvaluationResponse,
    MetricResult,
    StatusResponse,
)
from api.services.chat_client import ChatClient
from api.services.evaluation_service import EvaluationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["evaluation"])

evaluation_service = EvaluationService()
chat_client = ChatClient()


def save_evaluation_results(
    questions: List[str],
    ground_truths: List[str],
    answers: List[str],
    contexts: List[List[str]],
    scores: dict,
    output_dir: str = "./",
) -> str:
    """
    Сохранить результаты оценки в JSON файл.

    Args:
        questions: Список вопросов
        ground_truths: Список эталонных ответов
        answers: Список ответов модели
        contexts: Список контекстов (источников)
        scores: Словарь с метриками
        output_dir: Директория для сохранения результатов

    Returns:
        Путь к сохраненному файлу
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"evaluation_{timestamp}.json"
    filepath = Path(output_dir) / filename

    evaluation_data = {
        "timestamp": datetime.now().isoformat(),
        "total_samples": len(questions),
        "metrics": scores,
        "samples": [],
    }

    for i in range(len(questions)):
        sample = {
            "index": i + 1,
            "question": questions[i],
            "ground_truth": ground_truths[i],
            "model_answer": answers[i],
            "contexts": contexts[i] if i < len(contexts) else [],
        }
        evaluation_data["samples"].append(sample)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(evaluation_data, f, ensure_ascii=False, indent=2)

    logger.info(f"Результаты оценки сохранены в {filepath}")
    return str(filepath)


@router.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_answers(request: EvaluationRequest) -> EvaluationResponse:
    """
    Оценить ответы RAG системы различными метриками.

    Принимает вопросы, эталонные ответы, ответы модели и опционально контексты.
    Возвращает результаты оценки по выбранным метрикам.
    """
    try:
        scores = await evaluation_service.evaluate(
            questions=request.questions,
            ground_truths=request.ground_truths,
            answers=request.answers,
            contexts=request.contexts,
            metrics=request.metrics,
        )

        results = []
        total_score = 0.0
        metric_count = 0

        for metric_name, score in scores.items():
            description = evaluation_service.AVAILABLE_METRICS.get(metric_name, {}).get(
                "description"
            )
            results.append(
                MetricResult(
                    metric_name=metric_name,
                    score=score,
                    description=description,
                )
            )
            total_score += score
            metric_count += 1

        average_score = total_score / metric_count if metric_count > 0 else None

        return EvaluationResponse(
            results=results,
            average_score=average_score,
            total_samples=len(request.questions),
        )
    except ValueError as e:
        logger.error(f"Ошибка валидации: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка при оценке: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Ошибка при оценке ответов: {str(e)}"
        )


@router.get("/metrics", response_model=dict)
async def get_available_metrics() -> dict:
    """
    Получить список доступных метрик с описаниями.
    """
    return {
        "metrics": evaluation_service.get_available_metrics(),
        "service": settings.app_name,
    }


@router.get("/health")
async def health_check() -> StatusResponse:
    """Проверка здоровья сервиса"""
    return StatusResponse(status="healthy", message="Service is running")


@router.post("/evaluate-from-csv", response_model=EvaluationResponse)
async def evaluate_from_csv(
    csv_path: Optional[str] = Query(
        None,
        description="Путь к CSV файлу. Если не указан, используется файл по умолчанию",
    ),
    metrics: Optional[List[str]] = Query(
        None, description="Список метрик для вычисления"
    ),
    chat_service_url: Optional[str] = Query(
        None,
        description="URL chat-service. Если не указан, используется значение из настроек",
    ),
    user_id: Optional[str] = Query(
        "evaluation_user", description="ID пользователя для запросов к chat-service"
    ),
) -> EvaluationResponse:
    """
    Оценить ответы из CSV файла.

    Загружает вопросы и эталонные ответы из CSV файла,
    для каждого вопроса получает ответ от RAG системы (chat-service),
    затем выполняет оценку ответов используя ragas.
    """
    try:
        df = evaluation_service.load_questions_from_csv(csv_path)

        required_columns = ["Вопрос", "Эталонный ответ"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise HTTPException(
                status_code=400,
                detail=f"В CSV файле отсутствуют необходимые колонки: {missing_columns}",
            )

        df_filtered = df[["Вопрос", "Эталонный ответ"]].dropna()
        questions = df_filtered["Вопрос"].tolist()
        ground_truths = df_filtered["Эталонный ответ"].tolist()

        if not questions:
            raise HTTPException(
                status_code=400,
                detail="В CSV файле нет валидных вопросов и эталонных ответов",
            )

        original_url = None
        if chat_service_url:
            original_url = chat_client.chat_service_url
            chat_client.chat_service_url = chat_service_url

        try:
            await chat_client.reset_context(user_id)

            logger.info(
                f"Начинаем получение ответов от RAG системы для {len(questions)} вопросов"
            )
            answers = []
            contexts = []
            for i, question in enumerate(questions, 1):
                logger.info(
                    f"Обработка вопроса {i}/{len(questions)}: {question[:50]}..."
                )
                try:
                    answer, sources = await chat_client.get_answer(question, user_id)
                    if answer:
                        answers.append(answer)
                        contexts.append(sources if sources else [])
                    else:
                        logger.warning(f"Пустой ответ для вопроса {i}")
                        answers.append("")
                        contexts.append([])
                except Exception as e:
                    logger.error(f"Ошибка при получении ответа для вопроса {i}: {e}")
                    answers.append("")
                    contexts.append([])

            if original_url:
                chat_client.chat_service_url = original_url

            if not (
                len(questions) == len(ground_truths) == len(answers) == len(contexts)
            ):
                raise HTTPException(
                    status_code=500,
                    detail=f"Несоответствие длин: questions={len(questions)}, ground_truths={len(ground_truths)}, answers={len(answers)}, contexts={len(contexts)}",
                )

            valid_indices = [
                i for i, answer in enumerate(answers) if answer and answer.strip()
            ]

            if not valid_indices:
                raise HTTPException(
                    status_code=400,
                    detail="Не удалось получить ни одного ответа от RAG системы",
                )

            valid_questions = [questions[i] for i in valid_indices]
            valid_ground_truths = [ground_truths[i] for i in valid_indices]
            valid_answers = [answers[i] for i in valid_indices]
            valid_contexts = [contexts[i] for i in valid_indices]

            logger.info(f"Выполняем оценку для {len(valid_questions)} валидных ответов")

            scores = await evaluation_service.evaluate(
                questions=valid_questions,
                ground_truths=valid_ground_truths,
                answers=valid_answers,
                contexts=valid_contexts,
                metrics=metrics,
            )

            try:
                saved_path = save_evaluation_results(
                    questions=valid_questions,
                    ground_truths=valid_ground_truths,
                    answers=valid_answers,
                    contexts=valid_contexts,
                    scores=scores,
                )
                logger.info(f"Результаты сохранены в {saved_path}")
            except Exception as e:
                logger.error(f"Ошибка при сохранении результатов: {e}", exc_info=True)

            results = []
            total_score = 0.0
            metric_count = 0

            for metric_name, score in scores.items():
                description = evaluation_service.AVAILABLE_METRICS.get(
                    metric_name, {}
                ).get("description")
                results.append(
                    MetricResult(
                        metric_name=metric_name,
                        score=score,
                        description=description,
                    )
                )
                total_score += score
                metric_count += 1

            average_score = total_score / metric_count if metric_count > 0 else None

            return EvaluationResponse(
                results=results,
                average_score=average_score,
                total_samples=len(valid_questions),
            )
        finally:
            if original_url:
                chat_client.chat_service_url = original_url

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при оценке из CSV: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Ошибка при оценке из CSV: {str(e)}"
        )
