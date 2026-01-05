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


# --- Вспомогательные функции сохранения ---
async def save_interview_session(user_id: str, data: dict):
    """Сохраняет сессию интервью в Redis на 24 часа"""
    await redis_client.set(
        f"user:{user_id}:active_interview", json.dumps(data, ensure_ascii=False), ex=86400
    )


async def get_interview_session(user_id: str) -> dict | None:
    """Получает сохраненную сессию интервью"""
    raw_session = await redis_client.get(f"user:{user_id}:active_interview")
    return json.loads(raw_session) if raw_session else None


async def clear_interview_session(user_id: str):
    """Удаляет сохраненную сессию интервью"""
    await redis_client.delete(f"user:{user_id}:active_interview")


# --- Обработчики ---
@router.message(F.text == "🎤 Симуляция собеседования")
async def start_interview_mode(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    session = await get_interview_session(user_id)

    if session:
        # Есть незавершенное интервью
        kb = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text=f"▶️ Продолжить: {session['topic']}",
                        callback_data="int:resume",
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="🆕 Начать новое", callback_data="int:new"
                    )
                ],
            ]
        )
        await message.answer(
            "У тебя есть незавершенное интервью. Что сделаем?", reply_markup=kb
        )
    else:
        await start_new_setup(message, state)


@router.callback_query(F.data == "int:resume")
async def resume_interview(callback: types.CallbackQuery, state: FSMContext):
    """Возобновление прерванного интервью"""
    user_id = str(callback.from_user.id)
    session = await get_interview_session(user_id)

    if not session:
        await callback.answer("❌ Сессия устарела", show_alert=True)
        await callback.message.edit_text("Сессия не найдена. Начните новое интервью.")
        return

    await state.set_data(session)
    await state.set_state(InterviewState.in_progress)

    current_q = session["plan"][session["current_step"]]
    await callback.message.edit_text(
        f"🔄 Возвращаемся к теме: <b>{session['topic']}</b>\n\n"
        f"<b>Вопрос {session['current_step'] + 1}:</b>\n{current_q}",
        parse_mode="HTML",
    )
    await callback.message.answer(
        "Продолжаем интервью!", reply_markup=get_cancel_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "int:new")
async def force_new_interview(callback: types.CallbackQuery, state: FSMContext):
    """Начать новое интервью, отменив старое"""
    await clear_interview_session(str(callback.from_user.id))
    await start_new_setup(callback.message, state, is_edit=True)
    await callback.answer()


async def start_new_setup(message, state, is_edit=False):
    """Начало настройки нового интервью"""
    await state.set_state(InterviewState.setup)
    text = "🎭 <b>Выберите стиль собеседующего:</b>"
    if is_edit:
        await message.edit_text(
            text, reply_markup=get_persona_keyboard(), parse_mode="HTML"
        )
    else:
        await message.answer(
            text, reply_markup=get_persona_keyboard(), parse_mode="HTML"
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
        await state.clear()
        await message.answer("Возвращаемся в меню.", reply_markup=get_main_menu())
        return

    data = await state.get_data()
    persona_key = data.get("persona", "friendly")
    persona_instruction = PERSONA_PROMPTS.get(persona_key, "")
    topic = message.text
    user_id = str(message.from_user.id)

    status_msg = await message.answer("⏳ Составляю план вопросов...")

    prompt = (
        f"Ты опытный технический интервьюер. "
        f"Составь короткий план РЕАЛЬНОГО технического интервью по теме: '{topic}'. "
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

        # Сохраняем начальную сессию
        session_data = {
            "topic": topic,
            "persona": persona_key,
            "plan": plan,
            "current_step": 0,
            "history": [],
        }

        await state.update_data(**session_data)
        await state.set_state(InterviewState.in_progress)
        await save_interview_session(user_id, session_data)

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

    except Exception as e:
        await status_msg.edit_text(
            f"Не удалось сгенерировать план. Попробуйте другую тему.\nОшибка: {str(e)}"
        )


@router.message(InterviewState.in_progress)
async def process_answer(message: types.Message, state: FSMContext):
    if message.text == "❌ Выйти в меню":
        # НЕ удаляем сессию из Redis, чтобы можно было вернуться
        await state.clear()
        await message.answer(
            "Собеседование приостановлено. Ты можешь вернуться к нему позже.",
            reply_markup=get_main_menu(),
        )
        return

    data = await state.get_data()
    plan = data["plan"]
    step = data["current_step"]
    current_q = plan[step]
    user_input = message.text
    user_id = str(message.from_user.id)

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
        typing_task = asyncio.create_task(typing_loop(message.bot, message.chat.id))

        try:
            help_prompt = (
                f"Мы на собеседовании. Я задал вопрос: '{current_q}'. "
                f"Кандидат пишет: '{user_input}'. "
                f"Ответь ему в роли {data.get('persona', 'friendly')} интервьюера. "
                f"Можешь дать подсказку, объяснить термин или переформулировать вопрос. "
                f"Не давай полный правильный ответ сразу, подтолкни к мыслям."
            )

            help_response = await llm_chat(
                user_id,
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
            user_id,
            eval_prompt,
            instruction=PERSONA_PROMPTS[data.get("persona", "friendly")],
        )

        await redis_client.incr(f"stats:user:{message.from_user.id}:questions")

        # Обновляем историю
        new_history = data.get("history", [])
        new_history.append({"q": current_q, "a": user_input})

        next_step = step + 1

        if next_step < len(plan):
            # Продолжаем интервью
            new_data = {**data, "current_step": next_step, "history": new_history}
            await state.update_data(current_step=next_step, history=new_history)
            await save_interview_session(user_id, new_data)

            await message.answer(feedback)
            await message.answer(
                f"➡️ <b>Вопрос {next_step + 1}:</b>\n{plan[next_step]}",
                parse_mode="HTML",
            )
        else:
            # ФИНАЛ: Саммари и Рекомендации
            await message.answer(f"{feedback}\n\n🏁 Собеседование окончено!")

            # Формируем итоговый отчет
            await message.answer("📊 Формирую итоговый отчет...")

            summary_prompt = (
                f"Ты провел техническое собеседование по теме '{data['topic']}'. "
                f"Вот полная история вопросов и ответов кандидата:\n\n"
                f"{json.dumps(new_history, ensure_ascii=False, indent=2)}\n\n"
                f"Дай подробный итоговый отчет:\n"
                f"1. Оценка по 10-бальной шкале (с обоснованием)\n"
                f"2. Две сильные стороны кандидата\n"
                f"3. Две темы для дальнейшего изучения\n\n"
                f"Отвечай в стиле выбранной персоны ({data['persona']}). "
                f"Используй эмодзи и форматирование для наглядности."
            )

            report = await llm_chat(
                user_id,
                summary_prompt,
                instruction=PERSONA_PROMPTS[data.get("persona", "friendly")],
            )

            await message.answer(f"📊 <b>ИТОГОВЫЙ ОТЧЕТ:</b>\n\n{report}", parse_mode="HTML")

            # Удаляем сессию и возвращаем в меню
            await clear_interview_session(user_id)
            await state.clear()
            await message.answer("Возвращаемся в меню.", reply_markup=get_main_menu())

    finally:
        typing_task.cancel()

