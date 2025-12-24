import asyncio
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
    get_difficulty_keyboard,
    get_main_menu,
    get_problems_list_keyboard,
)
from app.redis_client import redis_client
from app.states import LeetCodeState
from app.utils import is_looks_like_code, llm_chat, typing_loop, update_user_memory

router = Router()


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---


async def save_active_problem(user_id: str, problem_data: dict):
    await redis_client.set(
        f"user:{user_id}:active_problem", json.dumps(problem_data)
    )


async def get_active_problem(user_id: str):
    data = await redis_client.get(f"user:{user_id}:active_problem")
    return json.loads(data) if data else None


async def clear_active_problem(user_id: str):
    await redis_client.delete(f"user:{user_id}:active_problem")


# --- МЕНЮ LEETCODE И НАВИГАЦИЯ ---


@router.message(F.text == "🧠 LeetCode Тренировка")
async def leetcode_entry(message: types.Message, state: FSMContext):
    """Точка входа. Перенаправляем на логику показа категорий."""
    # Удаляем Reply клавиатуру, чтобы она не мешала Inline меню
    await message.answer(
        "Загружаю меню задач...", reply_markup=types.ReplyKeyboardRemove()
    )
    await show_categories_logic(message, is_edit=False)


@router.callback_query(F.data == "lc:menu")
async def show_categories(callback: types.CallbackQuery):
    """Возврат в меню категорий (редактирование сообщения)."""
    await show_categories_logic(callback.message, is_edit=True)


async def show_categories_logic(message: types.Message, is_edit: bool):
    """
    Отображает категории задач.
    Если есть активная задача — добавляет кнопку возврата к ней.
    """
    user_id = str(message.chat.id)
    active_problem = await get_active_problem(user_id)

    builder = InlineKeyboardBuilder()

    # 1. Если есть незаконченная задача — кнопка возврата идет первой
    if active_problem:
        title = active_problem.get("problem_title", "Задача")
        # Обрезаем слишком длинные названия для кнопки
        if len(title) > 25:
            title = title[:22] + "..."

        builder.row(
            InlineKeyboardButton(
                text=f"▶️ Вернуться: {title}", callback_data="task:resume"
            )
        )

    # 2. Стандартные категории
    categories = [
        ("Algorithms", "algorithms"),
        ("Pandas (DataFrames)", "pandas"),
        ("Database (SQL)", "database"),
    ]

    for name, slug in categories:
        builder.row(
            InlineKeyboardButton(text=f"📂 {name}", callback_data=f"lc:cat:{slug}")
        )

    text = "Выберите категорию задач:"

    if is_edit:
        await message.edit_text(text, reply_markup=builder.as_markup())
    else:
        await message.answer(text, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("lc:cat:"))
async def show_difficulty(callback: types.CallbackQuery):
    """Выбор сложности внутри категории"""
    category = callback.data.split(":")[2]
    await callback.message.edit_text(
        f"Категория: <b>{category.capitalize()}</b>\nВыберите сложность:",
        reply_markup=get_difficulty_keyboard(category),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("lc:diff:"))
async def init_list(callback: types.CallbackQuery):
    """Инициализация списка задач (первая страница)"""
    parts = callback.data.split(":")
    category = parts[2]
    difficulty = parts[3]
    await render_problem_list(
        callback.message, category, difficulty, 0, is_edit=True
    )


@router.callback_query(F.data.startswith("lc:list:"))
async def paginate_list(callback: types.CallbackQuery):
    """Пагинация списка задач"""
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
    """Загрузка и отрисовка списка задач через API"""
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


# --- ЗАПУСК ЗАДАЧИ И ПРОВЕРКА КОНФЛИКТОВ ---


@router.callback_query(F.data.startswith("solve:"))
async def start_problem_check(callback: types.CallbackQuery, state: FSMContext):
    """
    Пользователь выбрал задачу из списка.
    Проверяем, нет ли уже активной задачи.
    """
    slug = callback.data.split(":")[1]
    user_id = str(callback.from_user.id)

    active_problem = await get_active_problem(user_id)

    # Если есть активная задача И это не та же самая, которую мы выбираем
    if active_problem and active_problem.get("problem_slug") != slug:
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="⚠️ Начать новую (стереть прогресс)",
                callback_data=f"force_solve:{slug}",
            )
        )
        builder.row(
            InlineKeyboardButton(text="🔙 Отмена", callback_data="lc:menu")
        )

        await callback.message.edit_text(
            f"⚠️ <b>Внимание!</b>\n\nУ вас есть незавершенная задача: <b>{active_problem['problem_title']}</b>.\n"
            f"Если вы начнете новую задачу, прогресс текущей будет потерян.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Если конфликтов нет — загружаем задачу
    await load_and_start_problem(callback, slug, state)


@router.callback_query(F.data.startswith("force_solve:"))
async def force_start_problem(callback: types.CallbackQuery, state: FSMContext):
    """
    Пользователь подтвердил сброс старой задачи.
    """
    slug = callback.data.split(":")[1]
    user_id = str(callback.from_user.id)

    # Сбрасываем старую
    await clear_active_problem(user_id)
    await state.clear()

    # Загружаем новую
    await load_and_start_problem(callback, slug, state)


async def load_and_start_problem(
    callback: types.CallbackQuery, slug: str, state: FSMContext
):
    """Общая логика загрузки задачи с API и установки стейта"""
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


# --- ВОССТАНОВЛЕНИЕ (RESUME) ЗАДАЧИ ---


@router.callback_query(F.data == "task:resume")
async def resume_problem(callback: types.CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    problem = await get_active_problem(user_id)

    if not problem:
        await callback.answer("Не удалось найти активную задачу.", show_alert=True)
        # Возвращаем в меню категорий
        await show_categories(callback)
        return

    await state.update_data(**problem)
    await state.set_state(LeetCodeState.solving_problem)

    # Удаляем меню выбора, чтобы не засорять чат, и отправляем новое сообщение с Reply-кнопкой
    await callback.message.delete()

    await callback.message.answer(
        f"🔄 Возвращаемся к задаче: <b>{problem['problem_title']}</b>\n"
        f"Ссылка: {problem.get('problem_link', '')}\n\n"
        f"Код:\n{hcode(problem['initial_code'])}",
        reply_markup=get_cancel_menu(),
        parse_mode="HTML",
    )


# --- НАСТРОЙКА СТЕЙТА (ОБЩАЯ) ---


async def setup_problem_state(
    message: types.Message, state: FSMContext, problem: dict
):
    user_id = str(message.chat.id)  # Используем chat.id для надежности в message
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

    # Если мы пришли из callback (inline), то нам нужно отправить НОВОЕ сообщение с Reply клавиатурой
    # Если мы редактируем message, то Reply клавиатура не появится.
    # Поэтому всегда делаем send_message.
    if isinstance(message, types.Message):
        # Если message был отредактирован (через edit_text), он все еще Message, но лучше удалить старое "Загружаю..."
        # Однако, удалять сообщение, на которое пользователь нажал, может быть плохим UX (дергается экран).
        # Просто отправим новое вниз.
        pass

    await message.bot.send_message(
        chat_id=message.chat.id, text=text, reply_markup=get_cancel_menu()
    )


# --- ПРОВЕРКА РЕШЕНИЯ ---


@router.message(LeetCodeState.solving_problem)
async def process_solution(message: types.Message, state: FSMContext):
    """
    Обработка текста/голоса с решением или вопросом.
    """
    if message.text == "❌ Выйти в меню":
        await message.answer("Выход в меню...", reply_markup=get_main_menu())
        await state.clear()
        # Активная задача в Redis остается (не вызываем clear_active_problem),
        # чтобы пользователь мог вернуться позже через кнопку "Resume".
        return

    user_text = message.text or ""
    data = await state.get_data()
    problem_title = data.get("problem_title")

    # --- ЭВРИСТИКА: КОД ИЛИ ВОПРОС? ---
    if not is_looks_like_code(user_text):
        typing_task = asyncio.create_task(
            typing_loop(message.bot, message.chat.id)
        )
        try:
            prompt = (
                f"Пользователь решает задачу LeetCode: '{problem_title}'. "
                f"Текущий контекст задачи: {data.get('problem_link')}. "
                f"Вопрос пользователя: '{user_text}'. "
                f"Дай подсказку или объясни тему, но НЕ пиши полное решение кода, если тебя прямо не попросили."
            )

            answer = await llm_chat(str(message.from_user.id), prompt)

            await update_user_memory(
                str(message.from_user.id),
                f"Задал вопрос по задаче {problem_title}: {user_text}",
            )
            await message.answer(
                f"🤖 <b>Подсказка:</b>\n\n{answer}", parse_mode="HTML"
            )
            return
        finally:
            typing_task.cancel()

    # --- ПРОВЕРКА КОДА ---
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
        generated_tests = await llm_chat("system_test_gen", llm_test_gen_prompt)
        # Очистка от markdown
        generated_tests = (
            generated_tests.replace("```python", "").replace("```", "").strip()
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

            # Задача решена успешно, удаляем из активных
            await clear_active_problem(user_id)

            await update_user_memory(
                user_id,
                f"Пользователь успешно решил задачу '{problem_title}'. Код был верным.",
            )
            await msg.edit_text(
                f"✅ {hbold('Решение принято!')}\n\nВсе тесты пройдены"
            )
            await state.clear()
            # Можно вернуть главное меню
            await message.answer(
                "Выберите действие:", reply_markup=get_main_menu()
            )

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
            hint = await llm_chat(str(message.from_user.id), analysis_prompt)

            await update_user_memory(
                str(message.from_user.id),
                f"Пользователь не смог решить задачу '{problem_title}'. Ошибка: {error_msg}.",
            )
            await message.answer(hint)

    except Exception as e:
        await msg.edit_text(f"Произошла ошибка проверки: {e}")
