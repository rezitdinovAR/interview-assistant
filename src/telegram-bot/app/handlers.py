import asyncio
import json
import re
import uuid

import httpx
from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import html_decoration as hd
from app.answers import PYTHON_DECORATORS
from app.config import settings
from app.redis_client import redis_client
from app.templates import message_to_html
from app.utils import (
    md_to_html,
    md_to_pdf_html,
    split_long_message,
    typing_loop,
    update_user_memory,
    with_typing,
)
from loguru import logger
from weasyprint import HTML

router = Router(name=__name__)

http_client = httpx.AsyncClient(timeout=60.0)


async def call_chat_service(endpoint: str, payload: dict) -> dict | None:
    try:
        response = await http_client.post(
            f"{settings.chat_service_url}{endpoint}", json=payload
        )
        response.raise_for_status()
        return response.json()
    except httpx.RequestError as e:
        logger.error(f"Ошибка сети при вызове {endpoint}: {e}")
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Ошибка API {endpoint}: {e.response.status_code}, {e.response.text}"
        )
    return None


@with_typing()
async def process_user_request(
    message: types.Message, user_text: str, state: FSMContext
):
    """Общая логика для обработки запроса"""
    typing_task = asyncio.create_task(typing_loop(message.bot, message.chat.id))

    try:
        user_id = str(message.from_user.id)
        payload = {"user_id": user_id, "message": user_text}

        if user_text.strip().lower() == "тест":
            response_data = {
                "message": PYTHON_DECORATORS,
                "follow_up_questions": [
                    "Что такое декораторы в Python?",
                    "Как использовать декораторы с аргументами?",
                    "Приведите пример встроенного декоратора",
                ],
            }
        else:
            response_data = await call_chat_service("/api/v1/chat", payload)

        if not response_data or "message" not in response_data:
            await message.answer(
                "Извини, не могу сейчас ответить. Попробуй позже."
            )
            return

        await update_user_memory(
            user_id,
            f"Запрос от пользователя: {user_text}\nОтвет ассистента: {response_data['message']}",
        )

        original_text = response_data["message"]
        answer_key = f"msg:{user_id}:{uuid.uuid4()}"

        await redis_client.set(
            answer_key, json.dumps({"text": original_text}), ex=3600
        )

        builder = InlineKeyboardBuilder()
        follow_ups = response_data.get("follow_up_questions")
        if follow_ups:
            for question in follow_ups:
                question_key = f"q:{user_id}:{uuid.uuid4()}"
                await redis_client.set(
                    question_key, json.dumps({"text": question}), ex=3600
                )
                builder.button(text=question, callback_data=question_key)

        builder.button(
            text="📄 Экспорт в PDF", callback_data=f"export_pdf:{answer_key}"
        )
        builder.adjust(1)
        keyboard = builder.as_markup()

        formatted_text = md_to_html(original_text)
        message_chunks = await split_long_message(formatted_text)

        for i, chunk in enumerate(message_chunks):
            reply_markup = keyboard if i == len(message_chunks) - 1 else None
            try:
                await message.answer(chunk, reply_markup=reply_markup)
            except TelegramBadRequest as e:
                if "can't parse entities" in str(e):
                    await message.answer(original_text, reply_markup=reply_markup)
                else:
                    raise e
            await asyncio.sleep(0.3)
    finally:
        typing_task.cancel()


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = str(message.from_user.id)
    await call_chat_service("/api/v1/reset", {"user_id": user_id})
    welcome_message = (
        f"Привет, {hd.quote(message.from_user.full_name)}!\n\n"
        "Я - твой ассистент для подготовки к собеседованиям. "
        "Задавай мне вопросы по Python, SQL, ML, DL, статистике, и я постараюсь помочь.\n\n"
        "Чтобы начать новый диалог, используй команду /reset"
    )
    await message.answer(welcome_message)


@router.message(Command("reset"))
async def cmd_reset(message: types.Message):
    user_id = str(message.from_user.id)
    result = await call_chat_service("/api/v1/reset", {"user_id": user_id})
    if result and result.get("status") == "OK":
        await message.answer(
            "Контекст диалога сброшен. Можешь задавать вопросы с чистого листа."
        )
    else:
        await message.answer(
            "Не удалось сбросить контекст. Сервис может быть недоступен."
        )


@router.message(F.text)
async def handle_text_message(message: types.Message, state: FSMContext):
    await process_user_request(message, message.text, state)


@router.callback_query(F.data.startswith("export_pdf:"))
async def handle_export_callback(callback: types.CallbackQuery, state: FSMContext):
    message_key = callback.data.split(":", 1)[1]

    await callback.answer("Готовлю PDF-файл...")

    raw_data = await redis_client.get(message_key)

    if not raw_data:
        await callback.message.answer(
            "Не удалось найти текст этого сообщения для экспорта. Возможно, он устарел."
        )
        return

    message_data = json.loads(raw_data)
    original_text = message_data["text"]

    converted_html = md_to_pdf_html(original_text)

    html_for_pdf = message_to_html(converted_html)

    pdf_bytes = HTML(string=html_for_pdf).write_pdf()

    candidate = "_".join(re.findall(r"\S+", original_text.strip())[:3])
    clean = re.sub(r"[^\w]+", "", candidate, flags=re.UNICODE)
    if not clean:
        clean = "export"
    filename = f"{clean}.pdf"

    file_to_send = BufferedInputFile(pdf_bytes, filename=filename)
    await callback.message.answer_document(file_to_send)


@router.callback_query(F.data.startswith("q:"))
async def handle_follow_up_callback(
    callback: types.CallbackQuery, state: FSMContext
):
    question_key = callback.data

    raw_data = await redis_client.get(question_key)

    if not raw_data:
        await callback.answer(
            "Не удалось найти текст вопроса. Возможно, он устарел.",
            show_alert=True,
        )
        return

    question_data = json.loads(raw_data)
    question_text = question_data["text"]

    await callback.answer()

    await callback.message.edit_reply_markup(reply_markup=None)

    await callback.message.answer(
        f"<i>Вы выбрали вопрос:</i>\n\n {hd.quote(question_text)}"
    )

    await process_user_request(callback.message, question_text, state)
