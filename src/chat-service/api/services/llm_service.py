import asyncio
from typing import Dict, Any, Literal, TypedDict
from pathlib import Path
import json

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.redis import AsyncRedisSaver
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from langchain_core.messages.utils import trim_messages, count_tokens_approximately

from api.core.config import settings
from api.services.db_client import DBServiceClient
from pydantic import BaseModel, Field
    
class InterviewAssistantState(TypedDict):
    """Состояние для графа Interview Assistant"""
    messages: list
    is_interview_related: bool | None
    retrieved_context: str | None
    
class RouterSchema(BaseModel):
    is_interview_related: bool = Field(
        False, description="Относится ли вопрос к подготовки к собеседованиям"
    )

class LLMGraphMemoryWithRAG:
    """
    Класс-обёртка над LangGraph + RedisSaver для хранения контекста диалога
    и общения с LLM с поддержкой RAG (Retrieval Augmented Generation).
    """

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
        self.graph = self._init_graph()
        
    def _init_router(self):
        """Создаёт подключение к модели Google Gemini"""
        kwargs = {
            "model": settings.google_model,
            "api_key": settings.google_api_key,
        }

        # Добавляем proxy если указан
        if settings.proxy_url:
            kwargs["client_args"] = {"proxy": settings.proxy_url}

        model = ChatGoogleGenerativeAI(**kwargs)
        model=model.with_structured_output(RouterSchema)
        
        return model
        
    def _init_model(self) -> ChatGoogleGenerativeAI:
        """Создаёт подключение к модели Google Gemini"""
        kwargs = {
            "model": settings.google_model,
            "api_key": settings.google_api_key,
        }

        # Добавляем proxy если указан
        if settings.proxy_url:
            kwargs["client_args"] = {"proxy": settings.proxy_url}

        model = ChatGoogleGenerativeAI(**kwargs)
        return model

    def _route_query(self, state: InterviewAssistantState) -> Literal["retrieve_context", "off_topic"]:
        """
        Router: Определяет следующую ноду на основе классификации запроса
        """
        if state["is_interview_related"]:
            return "retrieve_context"
        else:
            return "off_topic"

    def _init_graph(self) -> StateGraph:
        """Создаёт граф для хранения сообщений с Redis-чекпоинтом"""
        checkpointer = AsyncRedisSaver(settings.redis_uri)
        # setup() будет вызван автоматически при первом использовании

        # Создаем граф с кастомным состоянием
        builder = StateGraph(InterviewAssistantState)

        # Добавляем ноды
        builder.add_node("classify_query", self._classify_query)
        builder.add_node("retrieve_context", self._retrieve_context)
        builder.add_node("answer_with_rag", self._answer_with_rag)
        builder.add_node("off_topic", self._answer_off_topic)

        # Настраиваем маршрутизацию
        # START -> classify_query (классификация запроса)
        builder.add_edge(START, "classify_query")

        # classify_query -> conditional routing (по результату классификации)
        builder.add_conditional_edges(
            "classify_query",
            self._route_query,
            {
                "retrieve_context": "retrieve_context",
                "off_topic": "off_topic"
            }
        )

        # retrieve_context -> answer_with_rag (получили контекст, генерируем ответ)
        builder.add_edge("retrieve_context", "answer_with_rag")

        # answer_with_rag -> END (завершаем работу)
        builder.add_edge("answer_with_rag", END)

        # off_topic -> END (завершаем работу)
        builder.add_edge("off_topic", END)

        return builder.compile(checkpointer=checkpointer)
    
    def _get_user_query(self, state: InterviewAssistantState) -> str:
        return next(
            m.content for m in reversed(state["messages"])
            if isinstance(m, HumanMessage)
        )

    def _load_system_prompt(self) -> str:
        """Загружает system prompt из файла или использует по умолчанию"""
        if settings.system_prompt_path:
            prompt_path = Path(settings.system_prompt_path)
            if prompt_path.exists():
                return prompt_path.read_text(encoding="utf-8").strip()

        # Prompt по умолчанию
        return """Ты - интеллектуальный ассистент для подготовки к собеседованиям.
                Твоя задача - помогать пользователям готовиться к техническим собеседованиям,
                давая четкие и полезные ответы на основе предоставленного контекста.

                Правила работы:
                1. Анализируй весь предоставленный контекст и синтезируй из него единый, связный ответ
                2. НЕ перечисляй документы в ответе (не пиши "в документе 1...", "в документе 2...")
                3. Давай прямой, структурированный ответ на вопрос пользователя на основе документов
                4. Используй примеры кода и конкретные детали из контекста
                5. Если в контексте недостаточно информации, честно скажи об этом
                6. Будь кратким и по делу, избегай лишних вступлений
            """


    async def _classify_query(self, state: InterviewAssistantState) -> Dict[str, Any]:
        """
        Node 1: Классифицирует запрос пользователя (structured output)
        """

        # Берём последний вопрос пользователя из messages
        user_query = next(
            m.content for m in reversed(state["messages"])
            if isinstance(m, HumanMessage)
        )

        system_prompt = f"""
            Ты — классификатор пользовательских запросов.

            Определи, относится ли вопрос к:
            - техническим собеседованиям
            - подготовке к интервью
            - вопросам, которые задают на собеседованиях
            - карьере в IT в контексте интервью

            Ответь СТРОГО в формате JSON.
            НЕ добавляй пояснений, текста или комментариев.
        """

        response = await self.router.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_query)
        ])


        return {
            "is_interview_related": response.is_interview_related,
            "messages": state["messages"],
        }
    
    async def _retrieve_context(self, state: InterviewAssistantState) -> Dict[str, Any]:
        """
        Node 2a: Получает контекст из базы данных для вопросов о собеседованиях
        """
        user_query = self._get_user_query(state)
        print(user_query)
        print(self.top_k_documents)

        documents = await self.db_client.retrieve_documents_async(
            query=user_query,
            top_k=self.top_k_documents
        )
        try:
            "\n\n".join(documents)
        except:
            print('doc err')
            documents = []

        return {
            "retrieved_context": "\n\n".join(documents) if documents else None
        }

    async def _answer_with_rag(self, state: InterviewAssistantState) -> Dict[str, Any]:
        """
        Node 2b: Генерирует ответ на основе контекста из RAG
        """
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
            [SystemMessage(content=self.system_prompt)] + [HumanMessage(content=prompt)]
        )

        return {"messages": messages + [response]}


    def _answer_off_topic(self, state: InterviewAssistantState) -> Dict[str, Any]:
        """
        Node 3: Вежливо отказывает в помощи по темам не связанным с собеседованиями
        """
        messages = state["messages"]

        off_topic_response = """Извини, но я специализируюсь только на помощи в подготовке к техническим собеседованиям.
            Твой вопрос не относится к этой теме.

            Я могу помочь тебе с:
            • Подготовкой к техническим интервью
            • Разбором вопросов с собеседований
            • Объяснением концепций и технологий в контексте собеседований
            • Советами по прохождению интервью

            Задай, пожалуйста, вопрос, связанный с подготовкой к собеседованиям!"""

        ai_response = AIMessage(content=off_topic_response)

        return {"messages": messages + [ai_response]}

    async def ask(self, user_id: str, user_message: str) -> str:
        """
        Асинхронный метод: принимает текст пользователя,
        определяет тему запроса и возвращает соответствующий ответ.

        Args:
            user_id: ID пользователя
            user_message: Сообщение пользователя

        Returns:
            Ответ от LLM
        """
        # Формируем начальное состояние для графа
        initial_state = {
            "messages": [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_message),
            ],
            "is_interview_related": None,
            "retrieved_context": None,
        }

        # Вызываем граф асинхронно
        result = await self.graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": str(user_id)}}
        )

        # Получаем последнее сообщение от AI
        ai_message = result["messages"][-1]

        # Обрабатываем случай, когда content - это список блоков (multimodal формат)
        if isinstance(ai_message.content, list):
            # Извлекаем текст из всех текстовых блоков
            return "".join(
                block.get("text", "")
                for block in ai_message.content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        else:
            # Если content - строка, возвращаем как есть
            return ai_message.content

    async def reset_context(self, user_id: str) -> None:
        """
        Очищает контекст пользователя в Redis (LangGraph checkpoint).

        Args:
            user_id: ID пользователя
        """
        thread_id = str(user_id)
        checkpointer = self.graph.checkpointer

        # Удаляем все старые чекпоинты (используем to_thread, т.к. delete_thread синхронный)
        await asyncio.to_thread(checkpointer.delete_thread, thread_id)

    async def close(self) -> None:
        """Закрывает соединения"""
        await self.db_client.close()
