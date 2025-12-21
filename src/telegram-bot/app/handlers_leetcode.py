import html

import httpx
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hbold, hcode
from app.config import settings
from app.keyboards import get_cancel_menu, get_deep_dive_keyboard
from app.redis_client import redis_client
from app.states import LeetCodeState
from app.utils import clean_code, is_looks_like_code

router = Router()


async def fetch_random_problem(difficulty: str = "EASY"):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.leetcode_service_url}/random-question",
            json={"difficulty": difficulty},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def execute_code(user_code: str, test_code: str = ""):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.leetcode_service_url}/execute",
            json={"code": user_code, "test_code": test_code},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


async def ask_llm(user_id: str, prompt: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.chat_service_url}/api/v1/chat",
            json={"user_id": user_id, "message": prompt},
            timeout=60.0,
        )
        if resp.status_code == 200:
            return resp.json().get("message")
        return "Ошибка LLM сервиса."


@router.message(F.text == "🧠 LeetCode Тренировка")
async def start_leetcode_mode(message: types.Message, state: FSMContext):
    await state.set_state(LeetCodeState.menu)
    await message.answer(
        "Режим: <b>LeetCode</b>.\nНажмите /task чтобы получить задачу.",
        reply_markup=get_cancel_menu(),
    )


@router.message(Command("task"))
async def cmd_task(message: types.Message, state: FSMContext):
    await message.answer("🔍 Ищу задачу...")

    try:
        problem = await fetch_random_problem("EASY")
    except Exception as e:
        await message.answer(f"Ошибка получения задачи: {e}")
        return

    await state.update_data(
        problem_title=problem["title"],
        problem_slug=problem["slug"],
        problem_content=problem["content_html"],
        initial_code=problem["initial_code"],
    )

    await state.set_state(LeetCodeState.solving_problem)

    text = (
        f"{hbold(problem['title'])}\n\n"
        f"Ссылка: {problem['link']}\n\n"
        f"Отправьте решение (код функции) в ответ на это сообщение.\n"
        f"Шаблон:\n{hcode(problem['initial_code'])}"
    )
    await message.answer(text)


@router.message(LeetCodeState.solving_problem)
async def process_solution(message: types.Message, state: FSMContext):
    if message.text == "❌ Выйти в меню":
        return

    raw_text = message.text
    user_code = clean_code(raw_text)
    data = await state.get_data()
    problem_title = data.get("problem_title")

    if not is_looks_like_code(user_code):
        await message.bot.send_chat_action(message.chat.id, "typing")

        prompt = (
            f"User is currently solving LeetCode problem '{problem_title}'. "
            f"User asks: '{raw_text}'. "
            f"Provide a helpful hint or explanation without giving the full code solution."
        )

        answer = await ask_llm(str(message.from_user.id), prompt)
        await message.answer(answer)
        return

    problem_content = data.get("problem_content")
    msg = await message.answer("⏳ Проверяю решение...")

    llm_test_gen_prompt = (
        f"Generate ONLY python assertions code (no explanations, no markdown blocks) "
        f"to test a function for the LeetCode problem '{problem_title}'. "
        f"The user function signature is similar to this: {data.get('initial_code')}. "
        f"Problem description: {problem_content}. "
        f"Do NOT wrap code in 'if __name__'. "
        f"Write assertions like: assert sol.func(args) == expected, f'Expected {{expected}}, got {{sol.func(args)}}'"
    )

    try:
        generated_tests = await ask_llm("system_test_gen", llm_test_gen_prompt)
        generated_tests = generated_tests.replace("```python", "").replace(
            "```", ""
        )

        exec_result = await execute_code(user_code, generated_tests)

        if exec_result.get("success"):
            await redis_client.incr(f"stats:user:{message.from_user.id}:problems")
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
                    f"❌ <b>Синтаксическая ошибка</b>\n\n"
                    f"Код даже не запустился. Проверьте отступы и скобки:\n"
                    f"<pre>{html.escape(error_msg)}</pre>",
                    parse_mode="HTML",
                )
                return

            await msg.edit_text(
                f"❌ {hbold(f'Ошибка выполнения: {html.escape(error_msg)}')}\n\nАнализирую..."
            )

            analysis_prompt = (
                f"Пользователь решает задачу '{problem_title}'.\n"
                f"Код пользователя:\n```python\n{user_code}\n```\n"
                f"Ошибка при выполнении:\n{error_msg}\n\n"
                f"Подскажи, в чем ошибка, но не пиши сразу правильное решение. Дай наводку."
            )

            llm_help = await ask_llm(str(message.from_user.id), analysis_prompt)
            await message.answer(llm_help)

    except Exception as e:
        await msg.edit_text(f"Произошла ошибка при проверке: {e}")
