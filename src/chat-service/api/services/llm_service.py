import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal, TypedDict

import aiofiles
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.redis import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from api.core.config import settings
from api.services.db_client import DBServiceClient


class InterviewAssistantState(TypedDict):
    messages: list
    is_interview_related: bool | None
    retrieved_context: str | None


class RouterSchema(BaseModel):
    is_interview_related: bool = Field(
        False, description="Относится ли вопрос к подготовки к собеседованиям"
    )


class LLMGraphMemoryWithRAG:
    def __init__(self):
        self.max_tokens = settings.max_tokens
        self.max_history = settings.max_history
        self.top_k_documents = settings.top_k_documents

        self.system_prompt = self._load_system_prompt()
        self.initial_state = {
            "messages": [SystemMessage(content=self.system_prompt)]
        }

        self.db_client = DBServiceClient()
        self.model = self._init_model()
        self.router = self._init_router()

        self.redis_client = None
        self.checkpointer = None
        self.graph = None

    async def initialize(self):
        self.checkpointer = AsyncRedisSaver(settings.redis_uri)
        await self.checkpointer.setup()

        self.redis_client = Redis.from_url(
            settings.redis_uri, decode_responses=True
        )

        self.graph = self._build_graph()

    def _init_router(self):
        kwargs = {
            "model": settings.llm_model_name,
            "api_key": settings.llm_api_key,
            "base_url": settings.llm_base_url,
        }
        if settings.proxy_url:
            kwargs["client_args"] = {"proxy": settings.proxy_url}

        model = ChatOpenAI(**kwargs)
        return model.with_structured_output(RouterSchema)

    def _init_model(self) -> ChatOpenAI:
        kwargs = {
            "model": settings.llm_model_name,
            "api_key": settings.llm_api_key,
            "base_url": settings.llm_base_url,
        }
        if settings.proxy_url:
            kwargs["client_args"] = {"proxy": settings.proxy_url}

        return ChatOpenAI(**kwargs)

    def _route_query(
        self, state: InterviewAssistantState
    ) -> Literal["retrieve_context", "off_topic"]:
        if state["is_interview_related"]:
            return "retrieve_context"
        else:
            return "off_topic"

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(InterviewAssistantState)

        builder.add_node("classify_query", self._classify_query)
        builder.add_node("retrieve_context", self._retrieve_context)
        builder.add_node("answer_with_rag", self._answer_with_rag)
        builder.add_node("off_topic", self._answer_off_topic)

        builder.add_edge(START, "classify_query")
        builder.add_conditional_edges(
            "classify_query",
            self._route_query,
            {"retrieve_context": "retrieve_context", "off_topic": "off_topic"},
        )
        builder.add_edge("retrieve_context", "answer_with_rag")
        builder.add_edge("answer_with_rag", END)
        builder.add_edge("off_topic", END)

        return builder.compile(checkpointer=self.checkpointer)

    def _get_user_query(self, state: InterviewAssistantState) -> str:
        return next(
            m.content
            for m in reversed(state["messages"])
            if isinstance(m, HumanMessage)
        )

    def _load_system_prompt(self) -> str:
        if settings.system_prompt_path:
            prompt_path = Path(settings.system_prompt_path)
            if prompt_path.exists():
                return prompt_path.read_text(encoding="utf-8").strip()

        return """Ты - интеллектуальный ассистент для подготовки к собеседованиям.
                Твоя задача - помогать пользователям готовиться к техническим собеседованиям,
                давая четкие и полезные ответы на основе предоставленного контекста.
                """

    async def _classify_query(
        self, state: InterviewAssistantState
    ) -> Dict[str, Any]:
        try:
            user_query = next(
                m.content
                for m in reversed(state["messages"])
                if isinstance(m, HumanMessage)
            )
        except StopIteration:
            user_query = ""

        system_prompt = """
            Ты — классификатор запросов для технического ассистента.
            Твоя задача — определить, относится ли вопрос пользователя к сфере IT, программирования и подготовки к собеседованиям.

            КАТЕГОРИИ "INTERVIEW_RELATED" (True):
            - Алгоритмы и структуры данных (LeetCode, сортировки, деревья).
            - Языки программирования (Python, Java, C++, syntax, features).
            - Machine Learning, Deep Learning, Data Science (Grid Search, Backprop, NLP, CV).
            - System Design (High Load, базы данных, кэширование, микросервисы).
            - DevOps, CI/CD, Linux, сети.
            - Soft Skills вопросы для собеседований.
            - Вопросы "Что такое X?", "Как работает Y?", "В чем разница между A и B?".

            КАТЕГОРИИ "OFF_TOPIC" (False):
            - Погода, новости, политика.
            - Личные вопросы, не связанные с карьерой.
            - Вопросы про покупку товаров, игры (не разработку), развлечения.

            Ответь СТРОГО в формате JSON: {"is_interview_related": true/false}.
        """

        response = await self.router.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_query),
            ]
        )

        return {
            "is_interview_related": response.is_interview_related,
            "messages": state["messages"],
        }

    async def _retrieve_context(
        self, state: InterviewAssistantState
    ) -> Dict[str, Any]:
        user_query = self._get_user_query(state)

        try:
            documents = await self.db_client.retrieve_documents_async(
                query=user_query, top_k=self.top_k_documents
            )
        except Exception as e:
            print(f"Error retrieving docs: {e}")
            documents = []

        return {"retrieved_context": "\n\n".join(documents) if documents else None}

    async def _answer_with_rag(
        self, state: InterviewAssistantState
    ) -> Dict[str, Any]:
        user_query = self._get_user_query(state)
        retrieved_context = state.get("retrieved_context")
        messages = state["messages"]

        if retrieved_context:
            prompt = f"""Контекст для ответа:
                {retrieved_context}

                Вопрос пользователя:
                {user_query}

                Ответь, используя контекст выше."""
        else:
            prompt = user_query

        response = await self.model.ainvoke(
            [SystemMessage(content=self.system_prompt)]
            + [HumanMessage(content=prompt)]
        )

        return {"messages": messages + [response]}

    def _answer_off_topic(self, state: InterviewAssistantState) -> Dict[str, Any]:
        messages = state["messages"]
        off_topic_response = "Извини, но я специализируюсь только на помощи в подготовке к техническим собеседованиям."
        ai_response = AIMessage(content=off_topic_response)
        return {"messages": messages + [ai_response]}

    async def ask(self, user_id: str, user_message: str) -> str:
        if not self.graph:
            raise RuntimeError("LLM Service not initialized.")

        # Получаем профиль пользователя
        user_profile = "Неизвестный пользователь"
        if self.redis_client:
            data = await self.redis_client.get(f"user_profile:{user_id}")
            if data:
                user_profile = data

        # Формируем персонализированный системный промпт
        personal_system_prompt = f"""
        {self.system_prompt}
        
        ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ (ПОРТРЕТ):
        {user_profile}
        
        Адаптируй ответ под уровень и интересы этого пользователя.
        """

        # Запускаем граф
        initial_state = {
            "messages": [
                SystemMessage(content=personal_system_prompt),
                HumanMessage(content=user_message),
            ],
            "is_interview_related": None,
            "retrieved_context": None,
        }

        result = await self.graph.ainvoke(
            initial_state, config={"configurable": {"thread_id": str(user_id)}}
        )

        ai_message = result["messages"][-1]
        response_text = ""
        if isinstance(ai_message.content, list):
            response_text = "".join(
                block.get("text", "")
                for block in ai_message.content
                if block.get("type") == "text"
            )
        else:
            response_text = ai_message.content

        retrieved_ctx = result.get("retrieved_context")

        dataset_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "query": user_message,
            "context": retrieved_ctx if retrieved_ctx else "",
            "answer": response_text,
            "is_rag_used": bool(retrieved_ctx),
        }

        asyncio.create_task(self._save_to_dataset(dataset_entry))

        return response_text

    async def reset_context(self, user_id: str) -> None:
        if self.redis_client:
            config = {"configurable": {"thread_id": str(user_id)}}
            empty_state = {
                "messages": [SystemMessage(content=self.system_prompt)],
                "is_interview_related": None,
                "retrieved_context": None,
            }
            await self.graph.aupdate_state(config, empty_state)

    async def update_user_profile(self, user_id: str, recent_activity: str):
        """
        Анализирует последнее действие и обновляет портрет пользователя.
        """
        if not self.redis_client:
            return

        profile_key = f"user_profile:{user_id}"
        current_profile = await self.redis_client.get(profile_key)
        current_profile = (
            current_profile
            if current_profile
            else "Новый пользователь. Уровень и интересы пока не известны."
        )

        # Промпт для "Психолога/Ментора"
        profiler_prompt = f"""
        Ты — аналитик навыков разработчика. Твоя задача — поддерживать актуальный краткий портрет пользователя.
        
        ТЕКУЩИЙ ПОРТРЕТ:
        {current_profile}
        
        НОВОЕ СОБЫТИЕ/ДЕЙСТВИЕ:
        {recent_activity}
        
        ЗАДАЧА:
        Обнови портрет. Учти:
        1. Стек технологий (Python, Java, etc).
        2. Уровень знаний (Junior, Middle...).
        3. Слабые места (где ошибается).
        4. Сильные стороны.
        5. Стиль общения (любит кратко или подробно).
        
        Верни ТОЛЬКО обновленный текст портрета (2-3 предложения). Не пиши вступлений.
        """

        try:
            # Используем ту же модель, но с другим промптом
            response = await self.model.ainvoke(
                [HumanMessage(content=profiler_prompt)]
            )
            new_profile = response.content

            # Сохраняем обновленный профиль
            await self.redis_client.set(profile_key, new_profile)
            return new_profile
        except Exception as e:
            print(f"Error updating profile: {e}")
            return current_profile

    async def _save_to_dataset(self, entry: dict):
        """Асинхронная запись в файл через aiofiles"""
        try:
            file_path = "rag_dataset.jsonl"
            # async with открывает файл в отдельном потоке
            async with aiofiles.open(file_path, mode="a", encoding="utf-8") as f:
                await f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"Error writing to dataset: {e}")

    async def close(self) -> None:
        await self.db_client.close()
        if self.redis_client:
            await self.redis_client.aclose()
