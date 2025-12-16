import asyncio
import re
from functools import wraps

from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from markdown_it import MarkdownIt

md = MarkdownIt("commonmark", {"html": True})


def md_to_pdf_html(text: str) -> str:
    """Конвертирует Markdown в HTML, подходящий для PDF"""
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
        open_tag = f"<h{h}>"
        close_tag = f"</h{h}>"
        html = html.replace(open_tag, "<b>").replace(close_tag, "</b>\n")

    html = html.replace("<ul>", "").replace("</ul>", "\n")
    html = html.replace("<ol>", "").replace("</ol>", "\n")
    html = html.replace("<li>", "• ").replace("</li>", "\n")

    html = html.replace("<p>", "").replace("</p>", "\n")

    html = (
        html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    )

    for tag in ["section", "article", "header", "footer", "div"]:
        html = html.replace(f"<{tag}>", "").replace(f"</{tag}>", "")

    return html.strip()


async def split_long_message(text: str, max_length: int = 4096) -> list[str]:
    """
    Разбивает длинное сообщение на части
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_chunk = ""
    paragraphs = text.split("\n\n")

    for paragraph in paragraphs:
        # Если абзац + текущая часть превышают лимит, сохраняем текущую часть
        if len(current_chunk) + len(paragraph) + 2 > max_length:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = ""

        # Если сам абзац слишком длинный, его нужно принудительно разбить
        while len(paragraph) > max_length:
            split_pos = paragraph.rfind("\n", 0, max_length)
            if split_pos == -1:
                split_pos = max_length

            chunks.append(paragraph[:split_pos])
            paragraph = paragraph[split_pos:].lstrip()

        # Добавляем абзац + остаток к текущей части
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
    """
    Декоратор для установки и удержания статуса "печатает..."
    """

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
