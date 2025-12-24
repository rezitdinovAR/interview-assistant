import html
import json

import httpx
from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold, hcode
from app.config import settings
from app.keyboards import (
    get_cancel_menu,
    get_categories_keyboard,
    get_deep_dive_keyboard,
    get_difficulty_keyboard,
    get_main_menu,
    get_problems_list_keyboard,
)
from app.redis_client import redis_client
from app.states import LeetCodeState
from app.utils import is_looks_like_code, llm_chat, update_user_memory

router = Router()


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (active problem) ---
async def save_active_problem(user_id: str, problem_data: dict):
    await redis_client.set(
        f"user:{user_id}:active_problem", json.dumps(problem_data)
    )


async def get_active_problem(user_id: str):
    data = await redis_client.get(f"user:{user_id}:active_problem")
    return json.loads(data) if data else None


async def clear_active_problem(user_id: str):
    await redis_client.delete(f"user:{user_id}:active_problem")


# --- МЕНЮ LEETCODE ---


@router.message(F.text == "🧠 LeetCode Тренировка")
async def leetcode_entry(message: types.Message, state: FSMContext):
    """Точка входа: проверяем активную задачу или показываем категории"""
    user_id = str(message.from_user.id)
    active_problem = await get_active_problem(user_id)

    if active_problem:
        text = f"У вас есть незаконченная задача: <b>{active_problem['problem_title']}</b>."
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="▶️ Продолжить", callback_data="task:resume")
        )
        builder.row(
            InlineKeyboardButton(text="📂 Список задач", callback_data="lc:menu")
        )
        await message.answer(
            text, reply_markup=builder.as_markup(), parse_mode="HTML"
        )
    else:
        await message.answer(
            "Выберите категорию задач:", reply_markup=get_categories_keyboard()
        )


@router.callback_query(F.data == "lc:menu")
async def show_categories(callback: types.CallbackQuery):
    """Показывает список категорий (Algorithms, Pandas...)"""
    await callback.message.edit_text(
        "Выберите категорию задач:", reply_markup=get_categories_keyboard()
    )


@router.callback_query(F.data.startswith("lc:cat:"))
async def show_difficulty(callback: types.CallbackQuery):
    """Показывает выбор сложности для категории"""
    category = callback.data.split(":")[2]
    await callback.message.edit_text(
        f"Категория: <b>{category.capitalize()}</b>\nВыберите сложность:",
        reply_markup=get_difficulty_keyboard(category),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("lc:diff:"))
async def init_list(callback: types.CallbackQuery):
    """Инициализация списка (переход на первую страницу)"""
    # lc:diff:algorithms:EASY
    parts = callback.data.split(":")
    category = parts[2]
    difficulty = parts[3]

    # Перенаправляем на логику списка с offset=0
    # Просто вызываем ту же функцию, но формируем data вручную или вызываем напрямую
    # Проще всего вызвать функцию отрисовки списка
    await render_problem_list(
        callback.message, category, difficulty, 0, is_edit=True
    )


@router.callback_query(F.data.startswith("lc:list:"))
async def paginate_list(callback: types.CallbackQuery):
    """Пагинация списка"""
    # lc:list:algorithms:EASY:10
    parts = callback.data.split(":")
    category = parts[2]
    difficulty = parts[3]
    offset = int(parts[4])

    await render_problem_list(
        callback.message, category, difficulty, offset, is_edit=True
    )


async def render_problem_list(
    message: types.Message,
    category: str,
    difficulty: str,
    offset: int,
    is_edit: bool = True,
):
    """Общая функция отрисовки списка"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.leetcode_service_url}/list",
                json={
                    "limit": 10,
                    "skip": offset,
                    "difficulty": difficulty,
                    "category": category,
                },
                timeout=10.0,
            )
            data = resp.json()

        questions = [q for q in data["questions"] if not q.get("paidOnly")]
        total = data["total"]

        text = f"📂 <b>{category.capitalize()}</b> | 📊 <b>{difficulty}</b>\nПоказано {offset}-{offset + len(questions)} из {total}"
        kb = get_problems_list_keyboard(
            questions, offset, total, category, difficulty
        )

        if is_edit:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        err_text = f"Ошибка загрузки списка: {e}"
        if is_edit:
            await message.edit_text(err_text)
        else:
            await message.answer(err_text)


# --- ЗАПУСК ЗАДАЧИ ИЗ СПИСКА ---


@router.callback_query(F.data.startswith("solve:"))
async def start_problem_from_list(
    callback: types.CallbackQuery, state: FSMContext
):
    slug = callback.data.split(":")[1]
    await callback.answer()
    await callback.message.edit_text("⏳ Загружаю задачу...")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.leetcode_service_url}/problem",
                json={"slug": slug},
                timeout=15.0,
            )
            resp.raise_for_status()
            problem = resp.json()

        await setup_problem_state(callback.message, state, problem)

    except Exception as e:
        await callback.message.edit_text(f"Не удалось загрузить задачу: {e}")


# --- RESUME TASK ---


@router.callback_query(F.data == "task:resume")
async def resume_problem(callback: types.CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    problem = await get_active_problem(user_id)
    if not problem:
        await callback.message.edit_text("Не удалось восстановить задачу.")
        # Возвращаем в меню категорий
        await show_categories(callback)
        return
    await state.update_data(**problem)
    await state.set_state(LeetCodeState.solving_problem)

    await callback.message.edit_text(
        f"🔄 Возвращаемся к задаче: <b>{problem['problem_title']}</b>",
        parse_mode="HTML",
    )
    await callback.message.answer(
        f"{hbold(problem['problem_title'])}\n\nСсылка: {problem.get('problem_link', '')}\n\nКод:\n{hcode(problem['initial_code'])}",
        reply_markup=get_cancel_menu(),
    )


# --- ОБЩАЯ ЛОГИКА СТЕЙТА ---


async def setup_problem_state(
    message: types.Message, state: FSMContext, problem: dict
):
    user_id = str(message.from_user.id)
    state_data = {
        "problem_title": problem["title"],
        "problem_slug": problem["slug"],
        "problem_content": problem["content_html"],
        "initial_code": problem["initial_code"],
        "problem_link": problem["link"],
    }
    await state.update_data(**state_data)
    await state.set_state(LeetCodeState.solving_problem)
    await save_active_problem(user_id, state_data)

    text = (
        f"{hbold(problem['title'])}\n\nСсылка: {problem['link']}\n\n"
        f"Отправьте решение (код функции) в ответ на это сообщение.\nШаблон:\n{hcode(problem['initial_code'])}"
    )
    # Если вызываем из callback (message был edit), то нужно отправлять новое сообщение, а не редактировать
    # Поэтому просто send_message всегда безопаснее для старта задачи
    await message.bot.send_message(
        chat_id=message.chat.id, text=text, reply_markup=get_cancel_menu()
    )


# --- ПРОВЕРКА РЕШЕНИЯ ---


@router.message(LeetCodeState.solving_problem)
async def process_solution(message: types.Message, state: FSMContext):
    if message.text == "❌ Выйти в меню":
        await message.answer("Выход в меню...", reply_markup=get_main_menu())
        await state.clear()
        return

    user_text = message.text or ""
    data = await state.get_data()
    problem_title = data.get("problem_title")

    # --- ЭВРИСТИКА: КОД ИЛИ ВОПРОС? ---
    if not is_looks_like_code(user_text):
        await message.bot.send_chat_action(message.chat.id, "typing")
        prompt = (
            f"Пользователь решает задачу LeetCode: '{problem_title}'. "
            f"Текущий контекст задачи: {data.get('problem_link')}. "
            f"Вопрос пользователя: '{user_text}'. "
            f"Дай подсказку или объясни тему, но НЕ пиши полное решение кода, если тебя прямо не попросили."
        )
        # ИСПРАВЛЕНО: используем llm_chat
        answer = await llm_chat(str(message.from_user.id), prompt)

        await update_user_memory(
            str(message.from_user.id),
            f"Задал вопрос по задаче {problem_title}: {user_text}",
        )
        await message.answer(
            f"🤖 <b>Подсказка:</b>\n\n{answer}", parse_mode="HTML"
        )
        return

    # Проверка кода
    problem_content = data.get("problem_content")
    msg = await message.answer("⏳ Проверяю решение...")

    llm_test_gen_prompt = (
        f"You are a QA engineer. Generate Python assertions for LeetCode problem '{problem_title}'.\n"
        f"Description: {problem_content}\n"
        f"Signature: {data.get('initial_code')}\n"
        f"RULES: Extract examples from description. Generate ONLY raw python code. NO 'if __name__'."
        f"Assert format: assert sol.func(inp) == exp, f'Exp {{exp}}, got {{sol.func(inp)}}'"
    )

    try:
        # ИСПРАВЛЕНО: используем llm_chat
        generated_tests = await llm_chat("system_test_gen", llm_test_gen_prompt)
        generated_tests = generated_tests.replace("```python", "").replace(
            "```", ""
        )

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.leetcode_service_url}/execute",
                json={"code": user_text, "test_code": generated_tests},
                timeout=10.0,
            )
            exec_result = resp.json()

        if exec_result.get("success"):
            user_id = str(message.from_user.id)
            await redis_client.incr(f"stats:user:{user_id}:problems")
            await redis_client.sadd(
                f"history:user:{user_id}:solved", data.get("problem_slug")
            )
            await clear_active_problem(user_id)
            await update_user_memory(
                user_id,
                f"Пользователь успешно решил задачу '{problem_title}'. Код был верным.",
            )
            await msg.edit_text(
                f"✅ {hbold('Решение принято!')}\n\nВсе тесты пройдены."
            )
            await message.answer(
                "Хотите разобрать решение?", reply_markup=get_deep_dive_keyboard()
            )
            await state.clear()
        else:
            error_msg = exec_result.get("error") or exec_result.get("output")
            stage = exec_result.get("stage", "runtime")

            if stage == "linting":
                await msg.edit_text(
                    f"❌ <b>Синтаксическая ошибка</b>\n<pre>{html.escape(error_msg)}</pre>",
                    parse_mode="HTML",
                )
                return

            await msg.edit_text(
                f"❌ {hbold(f'Ошибка выполнения: {html.escape(error_msg)}')}\n\nАнализирую..."
            )

            analysis_prompt = f"Problem: {problem_title}\nCode:\n{user_text}\nError:\n{error_msg}\nExplain the error and give a hint."
            # ИСПРАВЛЕНО: используем llm_chat
            hint = await llm_chat(str(message.from_user.id), analysis_prompt)

            await update_user_memory(
                str(message.from_user.id),
                f"Пользователь не смог решить задачу '{problem_title}'. Ошибка: {error_msg}.",
            )
            await message.answer(hint)

    except Exception as e:
        await msg.edit_text(f"Произошла ошибка: {e}")
