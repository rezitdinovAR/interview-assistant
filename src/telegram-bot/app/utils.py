import ast
import asyncio
import re
import time
from functools import wraps

import httpx
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from app.config import settings
from app.redis_client import redis_client
from loguru import logger
from markdown_it import MarkdownIt

http_client = httpx.AsyncClient(timeout=60.0)


async def llm_chat(user_id: str, message: str, instruction: str = "") -> str:
    """Обертка для отправки запроса в chat-service"""
    final_message = (
        f"[SYSTEM INSTRUCTION: {instruction}]\n\n{message}"
        if instruction
        else message
    )

    try:
        resp = await http_client.post(
            f"{settings.chat_service_url}/api/v1/chat",
            json={"user_id": user_id, "message": final_message},
            timeout=60.0,
        )

        if resp.status_code == 200:
            return resp.json().get("message")
        return f"⚠️ Ошибка сервиса LLM: {resp.status_code}"
    except Exception as e:
        logger.error(f"LLM Chat error: {e}")
        return "⚠️ Сервис временно недоступен"


async def update_user_memory(user_id: str, text: str):
    """Фоновая задача для обновления памяти"""
    try:
        await http_client.post(
            f"{settings.chat_service_url}/api/v1/profile/update",
            json={"user_id": user_id, "activity_description": text},
        )
    except Exception as e:
        logger.error(f"Failed to update memory: {e}")


def clean_code(text: str) -> str:
    """Очищает текст от md ```python ... ```"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def is_looks_like_code(text: str) -> bool:
    """
    Эвристика: проверяем, похоже ли это на Python код.
    """
    keywords = [
        "def ",
        "class ",
        "import ",
        "return ",
        "print(",
        "if ",
        "for ",
        "while ",
    ]
    if len(text) < 10:
        return False

    # Если это просто текст вопроса - False
    if not any(k in text for k in keywords):
        return False

    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return any(k in text for k in keywords)


md = MarkdownIt("commonmark", {"html": True})


def md_to_pdf_html(text: str) -> str:
    return md.render(text)


def md_to_html(text: str) -> str:
    def replace_code_blocks(match):
        code = match.group(2)
        escaped_code = (
            code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f"<pre><code>{escaped_code}</code></pre>"

    pattern = re.compile(r"```(\w*)\n(.*?)\n```", re.DOTALL)
    text = pattern.sub(replace_code_blocks, text)

    html = md.render(text)

    html = html.replace("<strong>", "<b>").replace("</strong>", "</b>")
    html = html.replace("<em>", "<i>").replace("</em>", "</i>")

    for h in range(1, 7):
        html = html.replace(f"<h{h}>", "<b>").replace(f"</h{h}>", "</b>\n")

    html = html.replace("<ul>", "").replace("</ul>", "\n")
    html = html.replace("<ol>", "").replace("</ol>", "\n")
    html = html.replace("<li>", "• ").replace("</li>", "\n")
    html = html.replace("<p>", "").replace("</p>", "\n")
    html = html.replace("<br>", "\n").replace("<br/>", "\n")

    for tag in ["section", "article", "header", "footer", "div"]:
        html = html.replace(f"<{tag}>", "").replace(f"</{tag}>", "")

    return html.strip()


async def split_long_message(text: str, max_length: int = 4096) -> list[str]:
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    paragraphs = text.split("\n\n")

    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) + 2 > max_length:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = ""

        while len(paragraph) > max_length:
            split_pos = paragraph.rfind("\n", 0, max_length)
            if split_pos == -1:
                split_pos = max_length
            chunks.append(paragraph[:split_pos])
            paragraph = paragraph[split_pos:].lstrip()

        if current_chunk:
            current_chunk += "\n\n" + paragraph
        else:
            current_chunk = paragraph

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


async def typing_loop(bot, chat_id: int, interval: float = 4.0):
    try:
        while True:
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass


def with_typing(interval: float = 4.0):
    def decorator(func):
        @wraps(func)
        async def wrapper(
            message: Message, user_text: str, state: FSMContext, *args, **kwargs
        ):
            typing_task = asyncio.create_task(
                typing_loop(message.bot, message.chat.id, interval)
            )
            try:
                return await func(message, user_text, state, *args, **kwargs)
            finally:
                typing_task.cancel()

        return wrapper

    return decorator


def track_latency(metric_name: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                execution_time = time.perf_counter() - start_time
                asyncio.create_task(_save_metric(metric_name, execution_time))

        return wrapper

    return decorator


async def _save_metric(name: str, value: float):
    key = f"metrics:{name}"

    await redis_client.lpush(key, value)
    await redis_client.ltrim(key, 0, 99)
