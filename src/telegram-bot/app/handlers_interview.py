import asyncio
import json

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from app.keyboards import (
    get_cancel_menu,
    get_main_menu,
    get_persona_keyboard,
)
from app.redis_client import redis_client
from app.states import InterviewState
from app.utils import llm_chat, typing_loop

router = Router()

PERSONA_PROMPTS = {
    "friendly": "Ты - дружелюбный HR-специалист. Твоя цель - поддержать кандидата. Задавай вопросы мягко, хвали за правильные ответы. Используй эмодзи.",
    "nerd": "Ты - технический гик-сеньор. Тебя интересуют только глубокие детали, работа памяти, сложность алгоритмов и 'под капотом'. Будь дотошным.",
    "toxic": "Ты - очень строгий и токсичный тимлид. Ты не веришь в компетентность кандидата. Задавай каверзные вопросы, саркастично комментируй ошибки. Твоя цель - проверить стрессоустойчивость.",
}


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
        await state.clear()
        await message.answer(
            "Собеседование прервано.", reply_markup=get_main_menu()
        )
        return

    data = await state.get_data()
    plan = data["plan"]
    step = data["current_step"]
    current_q = plan[step]
    user_input = message.text

    # --- КЛАССИФИКАЦИЯ НАМЕРЕНИЯ ---
    classification_prompt = (
        f"Ты — классификатор интентов в диалоге собеседования.\n"
        f"Вопрос интервьюера: '{current_q}'\n"
        f"Сообщение пользователя: '{user_input}'\n\n"
        f"Определи, пытается ли пользователь ответить на вопрос (даже если неправильно) "
        f"ИЛИ он задает встречный вопрос / просит помощи / говорит, что не знает.\n"
        f'Верни JSON: {{"is_answer": true}} или {{"is_answer": false}}'
    )

    typing_task = asyncio.create_task(typing_loop(message.bot, message.chat.id))
    # Для классификации используем системный вызов
    try:
        class_resp = await llm_chat("system_classifier", classification_prompt)
        # Очистка JSON от markdown
        clean_json = class_resp.replace("```json", "").replace("```", "").strip()
        intent = json.loads(clean_json)
        is_answer = intent.get("is_answer", True)
    except Exception:
        # Если классификатор упал, считаем ответом
        is_answer = True
    finally:
        typing_task.cancel()

    # --- СЦЕНАРИЙ 1: ЭТО ВОПРОС / ПРОСЬБА ПОМОЩИ ---
    if not is_answer:
        typing_task = asyncio.create_task(
            typing_loop(message.bot, message.chat.id)
        )

        try:
            help_prompt = (
                f"Мы на собеседовании. Я задал вопрос: '{current_q}'. "
                f"Кандидат пишет: '{user_input}'. "
                f"Ответь ему в роли {data.get('persona', 'friendly')} интервьюера. "
                f"Можешь дать подсказку, объяснить термин или переформулировать вопрос. "
                f"Не давай полный правильный ответ сразу, подтолкни к мыслям."
            )

            help_response = await llm_chat(
                str(message.from_user.id),
                help_prompt,
                instruction=PERSONA_PROMPTS[data.get("persona", "friendly")],
            )

            await message.answer(help_response)
            return
        finally:
            typing_task.cancel()

    # --- СЦЕНАРИЙ 2: ЭТО ОТВЕТ НА ВОПРОС ---

    typing_task = asyncio.create_task(typing_loop(message.bot, message.chat.id))
    try:
        eval_prompt = (
            f"Question: {current_q}\nUser Answer: {user_input}\n"
            f"Give feedback on the answer based on your persona. Be brief. Do not make any questions."
        )

        feedback = await llm_chat(
            str(message.from_user.id),
            eval_prompt,
            instruction=PERSONA_PROMPTS[data.get("persona", "friendly")],
        )

        await redis_client.incr(f"stats:user:{message.from_user.id}:questions")
        await message.answer(feedback)

        next_step = step + 1
        if next_step < len(plan):
            await state.update_data(current_step=next_step)
            await message.answer(
                f"➡️ <b>Вопрос {next_step + 1}:</b>\n{plan[next_step]}",
                parse_mode="HTML",
            )
        else:
            await message.answer("🏁 Собеседование завершено!")
            await state.clear()
    finally:
        typing_task.cancel()
