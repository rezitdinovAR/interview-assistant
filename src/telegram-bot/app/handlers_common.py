import httpx
from aiogram import F, Router, types
from app.config import settings

router = Router()


@router.callback_query(F.data.startswith("dive:"))
async def deep_dive_callback(callback: types.CallbackQuery):
    action = callback.data.split(":")[1]
    user_id = str(callback.from_user.id)

    await callback.answer("Генерирую объяснение...")
    await callback.message.bot.send_chat_action(callback.message.chat.id, "typing")

    if action == "details":
        prompt = "Объясни предыдущий ответ подробнее. Приведи примеры кода, если уместно. Расскажи о нюансах."
    elif action == "simple":
        prompt = "Объясни предыдущий ответ очень простым языком, используя аналогии из реальной жизни (ELI5)."
    else:
        prompt = "Расскажи подробнее."

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.chat_service_url}/api/v1/chat",
                json={"user_id": user_id, "message": prompt},
                timeout=60.0,
            )
            answer = resp.json().get("message", "Ошибка.")

            await callback.message.reply(
                f"🧠 <b>Deep Dive:</b>\n\n{answer}", parse_mode="HTML"
            )
    except Exception:
        await callback.message.answer("Не удалось получить объяснение.")
