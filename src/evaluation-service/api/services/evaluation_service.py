import asyncio
import logging
import os
from typing import Dict, List, Optional

import pandas as pd
from datasets import Dataset
from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

from api.core.config import settings
from api.services.embedding_client import EmbeddingClient

logger = logging.getLogger(__name__)


class LangChainEmbeddingWrapper(Embeddings):
    """Обертка для EmbeddingClient, совместимая с LangChain"""

    def __init__(self, embedding_client: EmbeddingClient):
        self.embedding_client = embedding_client
        self._loop = None

    def _get_event_loop(self):
        """Получить или создать event loop"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Event loop is closed")
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents (синхронная версия)"""
        loop = self._get_event_loop()
        return loop.run_until_complete(self.embedding_client.embed_texts(texts))

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query (синхронная версия)"""
        loop = self._get_event_loop()
        result = loop.run_until_complete(self.embedding_client.embed_texts([text]))
        return result[0] if result else []

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents (асинхронная версия)"""
        return await self.embedding_client.embed_texts(texts)

    async def aembed_query(self, text: str) -> List[float]:
        """Embed a single query (асинхронная версия)"""
        result = await self.embedding_client.embed_texts([text])
        return result[0] if result else []


class EvaluationService:
    """Сервис для оценки ответов RAG системы с помощью ragas"""

    AVAILABLE_METRICS = {
        "faithfulness": {
            "metric": faithfulness,
            "description": "Метрика верности ответа контексту (насколько ответ основан на предоставленном контексте)",
        },
        "answer_relevancy": {
            "metric": answer_relevancy,
            "description": "Релевантность ответа вопросу (насколько ответ соответствует вопросу)",
        },
        "context_precision": {
            "metric": context_precision,
            "description": "Точность контекста (насколько релевантен извлеченный контекст)",
        },
        "context_recall": {
            "metric": context_recall,
            "description": "Полнота контекста (насколько полон извлеченный контекст)",
        },
    }

    def __init__(self):
        self.embedding_client = EmbeddingClient()
        self.embeddings = LangChainEmbeddingWrapper(self.embedding_client)
        self.llm = self._init_llm()

    def _init_llm(self) -> Optional[ChatOpenAI]:
        """
        Инициализировать LLM для ragas метрик.
        Если настройки не указаны, возвращает None (ragas будет использовать OpenAI по умолчанию).
        """
        llm_base_url = os.getenv("LLM_BASE_URL", settings.llm_base_url)
        llm_api_key = os.getenv("LLM_API_KEY", settings.llm_api_key)
        llm_model_name = os.getenv("LLM_MODEL_NAME", settings.llm_model_name)

        if not all([llm_base_url, llm_api_key, llm_model_name]):
            logger.warning(
                "LLM настройки не указаны. Ragas будет использовать OpenAI по умолчанию "
                "для метрик, требующих LLM. Укажите LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME "
                "для использования кастомного LLM."
            )
            return None

        try:
            llm = ChatOpenAI(
                model=llm_model_name, api_key=llm_api_key, base_url=llm_base_url
            )
            logger.info(
                f"Инициализирован LLM для ragas: {llm_model_name} ({llm_base_url})"
            )
            return llm
        except Exception as e:
            logger.error(f"Ошибка при инициализации LLM: {e}")
            return None

    def _prepare_dataset(
        self,
        questions: List[str],
        ground_truths: List[str],
        answers: List[str],
        contexts: Optional[List[List[str]]] = None,
    ) -> Dataset:
        """
        Подготовить датасет для оценки.

        Args:
            questions: Список вопросов
            ground_truths: Список эталонных ответов
            answers: Список ответов модели
            contexts: Список контекстов для каждого ответа (опционально)

        Returns:
            Dataset для ragas
        """
        if contexts is None:
            contexts = [[] for _ in questions]

        n = len(questions)
        if not (len(ground_truths) == len(answers) == len(contexts) == n):
            raise ValueError(
                "Все списки должны иметь одинаковую длину. "
                f"questions: {len(questions)}, ground_truths: {len(ground_truths)}, "
                f"answers: {len(answers)}, contexts: {len(contexts)}"
            )

        data = {
            "question": questions,
            "ground_truth": ground_truths,
            "answer": answers,
            "contexts": contexts,
        }

        return Dataset.from_dict(data)

    async def evaluate(
        self,
        questions: List[str],
        ground_truths: List[str],
        answers: List[str],
        contexts: Optional[List[List[str]]] = None,
        metrics: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """
        Оценить ответы RAG системы.

        Args:
            questions: Список вопросов
            ground_truths: Список эталонных ответов
            answers: Список ответов модели
            contexts: Список контекстов для каждого ответа (опционально)
            metrics: Список метрик для вычисления. Если None, используются все доступные

        Returns:
            Словарь с результатами метрик {metric_name: score}
        """
        if metrics is None:
            metrics = list(self.AVAILABLE_METRICS.keys())
        else:
            invalid_metrics = set(metrics) - set(self.AVAILABLE_METRICS.keys())
            if invalid_metrics:
                raise ValueError(
                    f"Неизвестные метрики: {invalid_metrics}. "
                    f"Доступные метрики: {list(self.AVAILABLE_METRICS.keys())}"
                )

        dataset = self._prepare_dataset(questions, ground_truths, answers, contexts)

        selected_metrics = [
            self.AVAILABLE_METRICS[metric]["metric"] for metric in metrics
        ]

        try:
            logger.info(
                f"Начинаем оценку для {len(questions)} вопросов с метриками: {metrics}"
            )
            evaluate_kwargs = {
                "dataset": dataset,
                "metrics": selected_metrics,
                "embeddings": self.embeddings,
            }

            if self.llm:
                evaluate_kwargs["llm"] = self.llm
                logger.info("Используется кастомный LLM для ragas метрик")

            print("[EVAL] Вызываем ragas.evaluate...")
            result = evaluate(**evaluate_kwargs)
            print(f"[EVAL] Ragas.evaluate завершен. Тип результата: {type(result)}")

            scores = {}

            if hasattr(result, "scores"):
                result_scores = result.scores
                print(f"[EVAL] Извлекаем метрики из result.scores: {result_scores}")

                if isinstance(result_scores, list) and len(result_scores) > 0:
                    print(
                        f"[EVAL] result.scores - это список из {len(result_scores)} семплов"
                    )

                    import math

                    for metric in metrics:
                        try:
                            metric_values = []
                            for sample_scores in result_scores:
                                if metric in sample_scores:
                                    value = sample_scores[metric]
                                    if hasattr(value, "item"):
                                        value = value.item()
                                    if not (math.isnan(value) or math.isinf(value)):
                                        metric_values.append(float(value))

                            if metric_values:
                                avg_value = sum(metric_values) / len(metric_values)
                                scores[metric] = avg_value
                                logger.info(
                                    f"Метрика {metric}: {avg_value:.4f} "
                                    f"(усреднено по {len(metric_values)} из {len(result_scores)} семплов)"
                                )
                            else:
                                logger.warning(
                                    f"Метрика {metric}: все значения nan/inf, устанавливаем 0.0"
                                )
                                scores[metric] = 0.0
                        except Exception as e:
                            logger.error(f"Ошибка при обработке метрики {metric}: {e}")
                            scores[metric] = 0.0
                else:
                    import math

                    for metric in metrics:
                        try:
                            if metric in result_scores:
                                metric_value = float(result_scores[metric])
                                if math.isnan(metric_value) or math.isinf(metric_value):
                                    logger.warning(
                                        f"Метрика {metric} имеет недопустимое значение ({metric_value}), устанавливаем 0.0"
                                    )
                                    scores[metric] = 0.0
                                else:
                                    scores[metric] = metric_value
                                    logger.info(f"Метрика {metric}: {scores[metric]}")
                            else:
                                logger.warning(
                                    f"Метрика {metric} не найдена в result.scores"
                                )
                                scores[metric] = 0.0
                        except Exception as e:
                            logger.error(f"Ошибка при обработке метрики {metric}: {e}")
                            scores[metric] = 0.0
            elif hasattr(result, "to_pandas"):
                df = result.to_pandas()
                print(f"[EVAL] Колонки DataFrame: {df.columns.tolist()}")

                for metric in metrics:
                    try:
                        if metric in df.columns:
                            valid_count = df[metric].notna().sum()
                            avg_score = df[metric].mean(skipna=True)

                            import math

                            if math.isnan(avg_score):
                                logger.warning(
                                    f"Метрика {metric}: все значения nan, устанавливаем 0.0"
                                )
                                scores[metric] = 0.0
                            else:
                                scores[metric] = float(avg_score)
                                logger.info(
                                    f"Метрика {metric}: {scores[metric]:.4f} "
                                    f"(усреднено по {valid_count} из {len(df)} семплов)"
                                )
                        else:
                            logger.warning(f"Метрика {metric} не найдена в DataFrame")
                            scores[metric] = 0.0
                    except Exception as e:
                        logger.error(f"Ошибка при обработке метрики {metric}: {e}")
                        scores[metric] = 0.0
            else:
                logger.error("Не удалось извлечь метрики из результата RAGAS")
                scores = {metric: 0.0 for metric in metrics}

            return scores
        except Exception as e:
            logger.error(f"Ошибка при оценке: {e}", exc_info=True)
            raise RuntimeError(f"Ошибка при оценке ответов: {e}") from e

    def load_questions_from_csv(self, csv_path: Optional[str] = None) -> pd.DataFrame:
        """
        Загрузить вопросы из CSV файла.

        Args:
            csv_path: Путь к CSV файлу. Если None, используется путь из настроек

        Returns:
            DataFrame с вопросами
        """
        if csv_path is None:
            csv_path = settings.questions_csv_path

        try:
            df = pd.read_csv(csv_path, encoding="utf-8")
            logger.info(f"Загружено {len(df)} вопросов из {csv_path}")
            return df
        except Exception as e:
            logger.error(f"Ошибка при загрузке CSV: {e}", exc_info=True)
            raise RuntimeError(f"Не удалось загрузить CSV файл: {e}") from e

    def get_available_metrics(self) -> Dict[str, str]:
        """
        Получить список доступных метрик с описаниями.

        Returns:
            Словарь {metric_name: description}
        """
        return {
            name: info["description"] for name, info in self.AVAILABLE_METRICS.items()
        }
