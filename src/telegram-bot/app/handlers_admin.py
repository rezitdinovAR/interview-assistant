import statistics
import uuid

from aiogram import Router, types
from aiogram.filters import Command
from app.config import settings
from app.keyboards import get_main_menu
from app.redis_client import redis_client

router = Router()


@router.message(Command("create_invite"))
async def create_invite(message: types.Message):
    if message.from_user.id not in settings.get_admin_ids:
        return

    code = str(uuid.uuid4())[:8]
    await redis_client.set(f"invite:{code}", "active", ex=3600)
    await message.answer(
        f"🎫 Инвайт-код: <code>{code}</code>\n(действителен 1 час)"
    )


@router.message(Command("revoke_invite"))
async def revoke_invite(message: types.Message):
    if message.from_user.id not in settings.get_admin_ids:
        return

    try:
        _, code = message.text.split()
        deleted = await redis_client.delete(f"invite:{code}")
        if deleted:
            await message.answer(f"✅ Инвайт-код <code>{code}</code> отозван")
        else:
            await message.answer(f"❌ Инвайт-код <code>{code}</code> не найден")
    except Exception:
        await message.answer("Ошибка. Требуемый формат: /revoke_invite CODE")


@router.message(Command("view_limits"))
async def view_limits(message: types.Message):
    if message.from_user.id not in settings.get_admin_ids:
        return

    keys = await redis_client.keys("limit:max:*")
    if not keys:
        await message.answer("Лимиты не установлены.")
        return

    response_lines = ["📊 Текущие лимиты пользователей:"]
    for key in keys:
        user_id = key.decode().split(":")[-1]
        limit = await redis_client.get(key)
        response_lines.append(
            f"• User ID {user_id}: {limit.decode()} запросов/час"
        )

    await message.answer("\n".join(response_lines))


@router.message(Command("get_list_codes"))
async def get_list_codes(message: types.Message):
    if message.from_user.id not in settings.get_admin_ids:
        return

    keys = await redis_client.keys("list_codes:user:*")
    if not keys:
        await message.answer("Нет сохраненных списков кодов")
        return

    response_lines = ["🗂 Сохраненные списки кодов пользователей:"]
    for key in keys:
        user_id = key.decode().split(":")[-1]
        codes = await redis_client.lrange(key, 0, -1)
        codes_str = ", ".join(code.decode() for code in codes)
        response_lines.append(f"• User ID {user_id}: {codes_str}")

    await message.answer("\n".join(response_lines))


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

    # Если пользователь уже имеет доступ
    if is_whitelisted or is_admin:
        if len(args) == 1:
            await send_welcome_message(message)
            return

    # Обработка инвайт-кода
    if len(args) > 1:
        code = args[1]
        status = await redis_client.get(f"invite:{code}")
        if status == "active":
            await redis_client.sadd("user:whitelist", str(user_id))
            await redis_client.delete(f"invite:{code}")

            await send_welcome_message(message)
        else:
            await message.answer("⛔️ Неверный или истекший код приглашения")
    else:
        await message.answer(
            "🔒 <b>Это закрытый бот.</b>\n\n"
            "Для доступа введите: <code>/start &lt;код_приглашения&gt;</code>",
            parse_mode="HTML",
        )


async def send_welcome_message(message: types.Message):
    """Отдельная функция для красивого приветствия"""
    text = (
        f"<b>Добро пожаловать, {message.from_user.first_name}</b>\n\n"
        "Я - твой AI-помощник для подготовки к DL собеседованиям\n\n"
        "<b>Что я умею:</b>\n"
        "🧠 <b>LeetCode Тренировка</b> — решай задачи, получай подсказки и разбор ошибок.\n"
        "🎤 <b>Симуляция интервью</b> — выбери роль (от доброго HR до токсичного сеньора) и пройди собеседование голосом.\n"
        "📚 <b>База знаний (RAG)</b> — задавай любые вопросы по теории (Python, SQL, ML) в свободном режиме.\n\n"
        "💡 <b>Лайфхак:</b> Я понимаю голосовые сообщения в <u>любом</u> меню. Лень писать код или ответ? Просто скажи!\n\n"
        "👇 <b>Нажми кнопку в меню, чтобы начать</b>"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu())


@router.message(Command("metrics"))
async def show_metrics(message: types.Message):
    if message.from_user.id not in settings.get_admin_ids:
        return

    metrics_map = {
        "metrics:chat": "💬 Chat Response",
        "metrics:voice": "🎤 Voice Transcribe",
        "metrics:code_exec": "⚙️ Code Execution",
    }

    report = ["📊 <b>Live Performance Metrics (Last 100 rq)</b>\n"]

    for key, label in metrics_map.items():
        # Получаем список значений из Redis
        raw_values = await redis_client.lrange(key, 0, -1)

        if not raw_values:
            report.append(f"{label}: <i>No data</i>")
            continue

        # Конвертируем байты в float
        values = [float(v) for v in raw_values]

        avg_val = statistics.mean(values)
        max_val = max(values)
        min_val = min(values)

        report.append(
            f"<b>{label}:</b>\n"
            f"  • Avg: <code>{avg_val:.3f}s</code>\n"
            f"  • Min: <code>{min_val:.3f}s</code>\n"
            f"  • Max: <code>{max_val:.3f}s</code>"
        )

    await message.answer("\n".join(report), parse_mode="HTML")
