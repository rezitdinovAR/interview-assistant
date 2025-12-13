import asyncio
from typing import Dict, Any
from pathlib import Path

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.checkpoint.redis import RedisSaver
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.messages.utils import trim_messages, count_tokens_approximately

from api.core.config import settings
from api.services.db_client import DBServiceClient


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
        self.graph = self._init_graph()

    def _init_model(self) -> ChatGoogleGenerativeAI:
        """Создаёт подключение к модели Google Gemini"""
        kwargs = {
            "model": settings.google_model,
            "api_key": settings.google_api_key,
        }

        # Добавляем proxy если указан
        if settings.proxy_url:
            kwargs["client_args"] = {"proxy": settings.proxy_url}
        print(kwargs)
        model = ChatGoogleGenerativeAI(**kwargs)
        return model

    def _init_graph(self) -> StateGraph:
        """Создаёт граф для хранения сообщений с Redis-чекпоинтом"""
        checkpointer = RedisSaver(settings.redis_uri)
        checkpointer.setup()

        builder = StateGraph(MessagesState)
        builder.add_node("call_model", self._call_model)
        builder.add_edge(START, "call_model")

        return builder.compile(checkpointer=checkpointer)

    def _load_system_prompt(self) -> str:
        """Загружает system prompt из файла или использует по умолчанию"""
        if settings.system_prompt_path:
            prompt_path = Path(settings.system_prompt_path)
            if prompt_path.exists():
                return prompt_path.read_text(encoding="utf-8").strip()

        # Prompt по умолчанию
        return """Ты - интеллектуальный ассистент для подготовки к собеседованиям.

Твоя задача - помогать пользователям готовиться к техническим собеседованиям,
отвечая на их вопросы на основе предоставленного контекста.

Правила работы:
1. Всегда используй информацию из предоставленного контекста для формирования ответа
2. Если в контексте недостаточно информации, честно скажи об этом
3. Давай структурированные и понятные ответы
4. Используй примеры кода, когда это уместно
5. Будь дружелюбным и поддерживающим"""

    def _call_model(self, state: MessagesState) -> Dict[str, Any]:
        """Вызывается графом LangGraph при каждом шаге"""
        trimmed_messages = trim_messages(
            state["messages"],
            strategy="last",
            token_counter=count_tokens_approximately,
            max_tokens=self.max_tokens,
            start_on="human",
            end_on=("human", "tool"),
            include_system=True
        )

        response = self.model.invoke(trimmed_messages)
        return {"messages": trimmed_messages + [response]}

    async def _invoke_graph(self, user_id: str, new_messages: list) -> Dict[str, Any]:
        """Вызывает граф в отдельном потоке"""
        return await asyncio.to_thread(
            self.graph.invoke,
            {"messages": self.initial_state["messages"] + new_messages},
            config={"configurable": {"thread_id": str(user_id)}},
        )

    async def _augment_with_context(self, user_message: str) -> str:
        """
        Дополняет сообщение пользователя контекстом из RAG

        Args:
            user_message: Исходное сообщение пользователя

        Returns:
            Дополненное сообщение с контекстом
        """
        try:
            documents = await self.db_client.retrieve_documents(
                query=user_message,
                top_k=self.top_k_documents
            )

            if not documents:
                return user_message

            # Формируем контекст из документов
            context = "\n\n".join([
                f"Документ {i+1}:\n{doc}"
                for i, doc in enumerate(documents)
            ])

            # Дополняем исходное сообщение контекстом
            augmented_message = f"""Контекст для ответа:
{context}

Вопрос пользователя: {user_message}

Пожалуйста, ответь на вопрос, используя информацию из контекста выше."""

            return augmented_message

        except Exception as e:
            # Если не удалось получить контекст, возвращаем исходное сообщение
            print(f"Warning: Error retrieving context: {e}")
            return user_message

    async def ask(self, user_id: str, user_message: str) -> str:
        """
        Асинхронный метод: принимает текст пользователя,
        дополняет его контекстом из RAG, возвращает ответ LLM.

        Args:
            user_id: ID пользователя
            user_message: Сообщение пользователя

        Returns:
            Ответ от LLM
        """
        # Дополняем сообщение контекстом из RAG
        augmented_message = await self._augment_with_context(user_message)

        # Создаем сообщение для LLM
        new_message = HumanMessage(content=augmented_message)

        # Получаем ответ от графа
        result = await self._invoke_graph(user_id, [new_message])

        return result["messages"][-1].content

    async def reset_context(self, user_id: str) -> None:
        """
        Очищает контекст пользователя в Redis (LangGraph checkpoint).

        Args:
            user_id: ID пользователя
        """
        thread_id = str(user_id)
        checkpointer = self.graph.checkpointer

        # Удаляем все старые чекпоинты
        await asyncio.to_thread(checkpointer.delete_thread, thread_id)

    async def close(self) -> None:
        """Закрывает соединения"""
        await self.db_client.close()
