import uuid

from aiogram import Router, types
from aiogram.filters import Command
from app.config import settings
from app.redis_client import redis_client

router = Router()


@router.message(Command("create_invite"))
async def create_invite(message: types.Message):
    if message.from_user.id not in settings.get_admin_ids:
        return

    code = str(uuid.uuid4())[:8]
    await redis_client.set(f"invite:{code}", "active", ex=86400 * 7)
    await message.answer(
        f"🎫 Инвайт-код: <code>{code}</code>\n(действителен 7 дней)"
    )


@router.message(Command("set_limit"))
async def set_limit(message: types.Message):
    if message.from_user.id not in settings.get_admin_ids:
        return

    try:
        _, target_id, limit = message.text.split()
        await redis_client.set(f"limit:max:{target_id}", int(limit))
        await message.answer(
            f"✅ Лимит для ID {target_id} установлен на {limit} запросов/час."
        )
    except Exception:
        await message.answer("Ошибка. Требуемый формат: /set_limit USER_ID LIMIT")


@router.message(Command("start"))
async def process_invite(message: types.Message):
    args = message.text.split()
    user_id = message.from_user.id

    is_whitelisted = await redis_client.sismember("user:whitelist", str(user_id))
    is_admin = user_id in settings.get_admin_ids

    if is_whitelisted or is_admin:
        if len(args) == 1:
            await message.answer(
                "С возвращением! Нажмите /menu для выбора режима."
            )
            return

    if len(args) > 1:
        code = args[1]
        status = await redis_client.get(f"invite:{code}")
        if status == "active":
            await redis_client.sadd("user:whitelist", str(user_id))
            await redis_client.delete(f"invite:{code}")
            await message.answer("Доступ получен! Нажмите /menu для начала")
        else:
            await message.answer("Неверный или истекший код")
    else:
        await message.answer(
            "Привет! Это закрытый бот.\nВведите /start &lt;код_приглашения&gt; для доступа."
        )
