import json

import httpx
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from app.config import settings
from app.keyboards import (
    get_cancel_menu,
    get_deep_dive_keyboard,
    get_persona_keyboard,
)
from app.redis_client import redis_client
from app.states import InterviewState

router = Router()

PERSONA_PROMPTS = {
    "friendly": "Ты - дружелюбный HR-специалист. Твоя цель - поддержать кандидата. Задавай вопросы мягко, хвали за правильные ответы. Используй эмодзи.",
    "nerd": "Ты - технический гик-сеньор. Тебя интересуют только глубокие детали, работа памяти, сложность алгоритмов и 'под капотом'. Будь дотошным.",
    "toxic": "Ты - очень строгий и токсичный тимлид. Ты не веришь в компетентность кандидата. Задавай каверзные вопросы, саркастично комментируй ошибки. Твоя цель - проверить стрессоустойчивость.",
}


async def llm_chat(user_id: str, message: str, instruction: str = "") -> str:
    """Обертка для отправки запроса в chat-service"""
    final_message = (
        f"[SYSTEM INSTRUCTION: {instruction}]\n\n{message}"
        if instruction
        else message
    )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.chat_service_url}/api/v1/chat",
                json={"user_id": user_id, "message": final_message},
                timeout=60.0,
            )
            if resp.status_code == 200:
                return resp.json().get("message")
            return "⚠️ Ошибка сервиса LLM"
    except Exception:
        return "⚠️ Сервис временно недоступен"


@router.message(F.text == "🎤 Симуляция собеседования")
async def start_interview_mode(message: types.Message, state: FSMContext):
    await state.set_state(InterviewState.setup)
    await message.answer(
        "🎭 <b>Выберите стиль собеседующего:</b>",
        reply_markup=get_persona_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(InterviewState.setup, F.data.startswith("persona:"))
async def select_persona(callback: types.CallbackQuery, state: FSMContext):
    persona_key = callback.data.split(":")[1]
    await state.update_data(persona=persona_key)

    await callback.message.edit_text(
        f"Выбран стиль: <b>{persona_key.upper()}</b>.\n\n"
        "Теперь напишите тему и уровень (например: <i>Python Middle</i>).",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(InterviewState.setup)
async def generate_plan(message: types.Message, state: FSMContext):
    if message.text == "❌ Выйти в меню":
        return

    data = await state.get_data()
    persona_key = data.get("persona", "friendly")
    persona_instruction = PERSONA_PROMPTS.get(persona_key, "")

    status_msg = await message.answer("⏳ Составляю план вопросов...")

    prompt = (
        f"Ты опытный технический интервьюер. "
        f"Составь короткий план РЕАЛЬНОГО технического интервью по теме: '{message.text}'. "
        f"Вопросы должны звучать так, как их задают на настоящем собеседовании: "
        f"просто, по делу, без академических формулировок и теории ради теории. "
        f"Проверяй практическое понимание и опыт, а не заученные определения. "
        f"Верни ТОЛЬКО сырой JSON-массив из ровно 3 строк — вопросов. "
        f"Без markdown, без пояснений, без лишнего текста. "
        f'Пример формата: ["Вопрос 1", "Вопрос 2", "Вопрос 3"]. '
        f"Используй русский язык"
    )

    response = await llm_chat("system", prompt, instruction=persona_instruction)

    try:
        clean_json = response.replace("```json", "").replace("```", "").strip()
        plan = json.loads(clean_json)

        await state.update_data(plan=plan, current_step=0, history=[])
        await state.set_state(InterviewState.in_progress)

        plan_text = "\n".join([f"{i + 1}. {q}" for i, q in enumerate(plan)])
        await status_msg.edit_text(
            f"<b>План собеседования:</b>\n{plan_text}\n\nГотовы к первому вопросу?",
            parse_mode="HTML",
        )

        await message.answer(
            f"<b>Вопрос 1:</b>\n{plan[0]}",
            parse_mode="HTML",
            reply_markup=get_cancel_menu(),
        )

    except Exception:
        await status_msg.edit_text(
            "Не удалось сгенерировать план. Попробуйте другую тему."
        )


@router.message(InterviewState.in_progress)
async def process_answer(message: types.Message, state: FSMContext):
    if message.text == "❌ Выйти в меню":
        return

    data = await state.get_data()
    plan = data["plan"]
    step = data["current_step"]
    persona_key = data.get("persona", "friendly")

    current_q = plan[step]
    user_answer = message.text

    await message.bot.send_chat_action(message.chat.id, "typing")

    eval_prompt = (
        f"Question: {current_q}\nUser Answer: {user_answer}\n"
        f"Give feedback on the answer based on your persona. Be brief (2-3 sentences)."
    )
    feedback = await llm_chat(
        str(message.from_user.id),
        eval_prompt,
        instruction=PERSONA_PROMPTS[persona_key],
    )

    await redis_client.incr(f"stats:user:{message.from_user.id}:questions")

    await message.answer(feedback, reply_markup=get_deep_dive_keyboard())

    next_step = step + 1
    if next_step < len(plan):
        await state.update_data(current_step=next_step)
        await message.answer(
            f"➡️ <b>Вопрос {next_step + 1}:</b>\n{plan[next_step]}",
            parse_mode="HTML",
        )
    else:
        await redis_client.incr(f"stats:user:{message.from_user.id}:interviews")
        await message.answer(
            "🏁 <b>Собеседование завершено!</b>\nВы отлично держались.",
            reply_markup=get_cancel_menu(),
            parse_mode="HTML",
        )
        await state.clear()
