import html
import json

import httpx
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hbold, hcode
from app.config import settings
from app.keyboards import (
    get_cancel_menu,
    get_deep_dive_keyboard,
    get_problem_search_keyboard,
    get_resume_keyboard,
)
from app.redis_client import redis_client
from app.states import LeetCodeState
from app.utils import clean_code, is_looks_like_code, update_user_memory

router = Router()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---


async def save_active_problem(user_id: str, problem_data: dict):
    """Сохраняем состояние задачи, чтобы к ней можно было вернуться"""
    await redis_client.set(
        f"user:{user_id}:active_problem", json.dumps(problem_data)
    )


async def get_active_problem(user_id: str):
    data = await redis_client.get(f"user:{user_id}:active_problem")
    return json.loads(data) if data else None


async def clear_active_problem(user_id: str):
    await redis_client.delete(f"user:{user_id}:active_problem")


# --- ХЕНДЛЕРЫ ---


@router.message(F.text == "🧠 LeetCode: Рандом")
@router.message(Command("task"))
async def cmd_task_start(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)

    active_problem = await get_active_problem(user_id)

    if active_problem:
        await message.answer(
            f"У вас есть незаконченная задача: <b>{active_problem['title']}</b>.\nХотите продолжить?",
            reply_markup=get_resume_keyboard(),
            parse_mode="HTML",
        )
        return

    await start_new_random_problem(message, state)


@router.callback_query(F.data == "task:resume")
async def resume_problem(callback: types.CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    problem = await get_active_problem(user_id)

    if not problem:
        await callback.message.edit_text(
            "Не удалось восстановить задачу. Начинаем новую."
        )
        await start_new_random_problem(callback.message, state)
        return

    await state.update_data(**problem)
    await state.set_state(LeetCodeState.solving_problem)

    await callback.message.edit_text(
        f"🔄 Возвращаемся к задаче: <b>{problem['problem_title']}</b>",
        parse_mode="HTML",
    )
    # Показываем условие снова
    await callback.message.answer(
        f"{hbold(problem['problem_title'])}\n\n"
        f"Ссылка: {problem.get('problem_link', '')}\n\n"
        f"Код:\n{hcode(problem['initial_code'])}",
        reply_markup=get_cancel_menu(),
    )


@router.callback_query(F.data == "task:new")
async def new_problem_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_new_random_problem(callback.message, state)


async def start_new_random_problem(message: types.Message, state: FSMContext):
    await message.answer("🔍 Ищу случайную задачу (Easy)...")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.leetcode_service_url}/random-question",
                json={"difficulty": "EASY"},
                timeout=15.0,
            )
            resp.raise_for_status()
            problem = resp.json()

        await setup_problem_state(message, state, problem)

    except Exception as e:
        await message.answer(f"Ошибка получения задачи: {e}")


# --- ПОИСК ЗАДАЧ ---


@router.message(F.text == "🔎 LeetCode: Поиск")
async def cmd_search_start(message: types.Message, state: FSMContext):
    await state.set_state(LeetCodeState.search)
    await message.answer(
        "Введите название задачи или тему (например: <i>Two Sum</i>, <i>Stack</i>).",
        reply_markup=get_cancel_menu(),
        parse_mode="HTML",
    )


@router.message(LeetCodeState.search)
async def process_search(message: types.Message, state: FSMContext):
    if message.text == "❌ Выйти в меню":
        return

    keyword = message.text
    msg = await message.answer("🔎 Ищу...")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.leetcode_service_url}/search",
                json={"keyword": keyword},
                timeout=10.0,
            )
            results = resp.json().get("results", [])

        if not results:
            await msg.edit_text("Ничего не найдено. Попробуйте другой запрос.")
            return

        await msg.edit_text(
            f"Найдены задачи по запросу '{keyword}':",
            reply_markup=get_problem_search_keyboard(results[:5]),  # Топ 5
        )

    except Exception as e:
        await msg.edit_text(f"Ошибка поиска: {e}")


@router.callback_query(F.data.startswith("solve:"))
async def start_searched_problem(callback: types.CallbackQuery, state: FSMContext):
    slug = callback.data.split(":")[1]
    await callback.answer()
    await callback.message.edit_text("Загружаю задачу...")

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
        await callback.message.answer(f"Не удалось загрузить задачу: {e}")


# --- ОБЩАЯ ЛОГИКА ЗАПУСКА ЗАДАЧИ ---


async def setup_problem_state(
    message: types.Message, state: FSMContext, problem: dict
):
    """Инициализирует стейт, сохраняет в Redis и показывает задачу"""
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
        f"{hbold(problem['title'])}\n\n"
        f"Ссылка: {problem['link']}\n\n"
        f"Отправьте решение (код функции) в ответ на это сообщение.\n"
        f"Шаблон:\n{hcode(problem['initial_code'])}"
    )
    target_chat = message.chat.id
    await message.bot.send_message(
        chat_id=target_chat, text=text, reply_markup=get_cancel_menu()
    )


# --- ПРОВЕРКА РЕШЕНИЯ ---


@router.message(LeetCodeState.solving_problem)
async def process_solution(message: types.Message, state: FSMContext):
    if message.text == "❌ Выйти в меню":
        return

    raw_text = message.text
    user_code = clean_code(raw_text)
    data = await state.get_data()
    problem_title = data.get("problem_title")
    problem_slug = data.get("problem_slug")

    if not is_looks_like_code(user_code):
        await message.bot.send_chat_action(message.chat.id, "typing")

        async with httpx.AsyncClient() as client:
            prompt = f"User is solving LeetCode '{problem_title}'. Question: '{raw_text}'. Hint only."
            resp = await client.post(
                f"{settings.chat_service_url}/api/v1/chat",
                json={"user_id": str(message.from_user.id), "message": prompt},
                timeout=60.0,
            )
            answer = resp.json().get("message")

        await update_user_memory(
            str(message.from_user.id),
            f"Пользователь задал вопрос по задаче '{problem_title}': {raw_text}. Ответ ассистента: {answer}",
        )

        await message.answer(answer)
        return

    # Проверка кода
    problem_content = data.get("problem_content")
    msg = await message.answer("⏳ Проверяю решение...")

    async def ask_llm_local(prompt):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.chat_service_url}/api/v1/chat",
                json={"user_id": "system_test_gen", "message": prompt},
                timeout=60.0,
            )
            return resp.json().get("message")

    llm_test_gen_prompt = (
        f"You are a QA engineer. Generate Python assertions for LeetCode problem '{problem_title}'.\n"
        f"Description: {problem_content}\n"
        f"Signature: {data.get('initial_code')}\n"
        f"RULES: Extract examples from description. Generate ONLY raw python code. NO 'if __name__'."
        f"Assert format: assert sol.func(inp) == exp, f'Exp {{exp}}, got {{sol.func(inp)}}'"
    )

    try:
        generated_tests = await ask_llm_local(llm_test_gen_prompt)
        generated_tests = generated_tests.replace("```python", "").replace(
            "```", ""
        )

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.leetcode_service_url}/execute",
                json={"code": user_code, "test_code": generated_tests},
                timeout=10.0,
            )
            exec_result = resp.json()

        if exec_result.get("success"):
            user_id = str(message.from_user.id)
            # Счетчик задач
            await redis_client.incr(f"stats:user:{user_id}:problems")
            # История решенных
            await redis_client.sadd(f"history:user:{user_id}:solved", problem_slug)
            # Удаляем из "активных", так как решена
            await clear_active_problem(user_id)

            await update_user_memory(
                str(message.from_user.id),
                f"Пользователь успешно решил задачу '{problem_title}' (тема: LeetCode Easy). Код был верным.",
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

            # Анализ ошибки через LLM
            analysis_prompt = f"Problem: {problem_title}\nCode:\n{user_code}\nError:\n{error_msg}\nExplain the error and give a hint."
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{settings.chat_service_url}/api/v1/chat",
                    json={
                        "user_id": str(message.from_user.id),
                        "message": analysis_prompt,
                    },
                    timeout=60.0,
                )
                hint = resp.json().get("message")

            await update_user_memory(
                str(message.from_user.id),
                f"Пользователь не смог решить задачу '{problem_title}'. Ошибка: {error_msg}. Возможно, есть пробелы в этой теме.",
            )

            await message.answer(hint)

    except Exception as e:
        await msg.edit_text(f"Произошла ошибка: {e}")
