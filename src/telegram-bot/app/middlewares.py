import time
from typing import Any, Awaitable, Callable, Dict

import httpx
from aiogram import BaseMiddleware, Bot
from aiogram.types import Message
from app.config import settings
from app.redis_client import redis_client


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        # Если это не сообщение (например, callback), пропускаем проверку лимитов сообщений
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id
        admins = settings.get_admin_ids

        # Админы обходят всё
        if user_id in admins:
            return await handler(event, data)

        # Обработка команд /start для ввода инвайта (пропускаем без проверки вайтлиста)
        text = event.text or ""
        if text.startswith("/start"):
            return await handler(event, data)

        # Проверка Whitelist
        is_allowed = await redis_client.sismember("user:whitelist", str(user_id))
        if not is_allowed:
            await event.answer(
                "⛔️ У вас нет доступа. Обратитесь к администратору или введите инвайт-код."
            )
            return

        # Rate Limiting
        current_hour = int(time.time() // 3600)

        global_key = f"limit:global:{current_hour}"
        user_key = f"limit:user:{user_id}:{current_hour}"

        global_count = await redis_client.get(global_key)
        if global_count and int(global_count) >= settings.limit_bot_per_hour:
            await event.answer("⚠️ Бот сейчас перегружен. Попробуйте позже.")
            return

        personal_limit = await redis_client.get(f"limit:max:{user_id}")
        max_limit = (
            int(personal_limit) if personal_limit else settings.limit_user_per_hour
        )

        user_count = await redis_client.get(user_key)
        if user_count and int(user_count) >= max_limit:
            await event.answer(
                f"⏳ Превышен лимит запросов ({max_limit} в час). Отдохните немного."
            )
            return

        async with redis_client.pipeline() as pipe:
            pipe.incr(global_key)
            pipe.expire(global_key, 3700)
            pipe.incr(user_key)
            pipe.expire(user_key, 3700)
            await pipe.execute()

        return await handler(event, data)


class VoiceToTextMiddleware(BaseMiddleware):
    """
    Конвертирует голосовые сообщения в текст
    """

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message) or not event.voice:
            return await handler(event, data)

        bot: Bot = data["bot"]

        # Визуальная индикация
        callback_message = await bot.send_message(
            event.chat.id, "🎙 Слушаю голосовое сообщение..."
        )

        # Скачивание и транскрибация
        try:
            file_id = event.voice.file_id
            file = await bot.get_file(file_id)
            file_path = file.file_path
            voice_io = await bot.download_file(file_path)

            async with httpx.AsyncClient() as client:
                files = {"file": ("voice.ogg", voice_io, "audio/ogg")}
                resp = await client.post(
                    f"{settings.transcribe_service_url}/transcribe",
                    files=files,
                    timeout=30.0,
                )
                resp.raise_for_status()
                transcribed_text = resp.json().get("text", "")

        except Exception as e:
            print(f"Middleware Transcribe Error: {e}")
            await event.reply("😔 Не удалось распознать голосовое сообщение.")
            return

        if not transcribed_text:
            await event.reply("😔 Голосовое сообщение пустое или неразборчивое.")
            return

        await callback_message.delete()
        await event.reply(
            f'🗣 <b>Распознано:</b> "{transcribed_text}"', parse_mode="HTML"
        )

        # Подменяем текст сообщения
        try:
            object.__setattr__(event, "text", transcribed_text)
        except AttributeError:
            event.text = transcribed_text

        return await handler(event, data)
