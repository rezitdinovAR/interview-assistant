from aiogram import F, Router, types
from app.redis_client import redis_client

router = Router()


def get_rank(problems: int, interviews: int, questions: int) -> str:
    score = problems * 2 + interviews * 5 + 0.5 * questions
    if score < 10:
        return "Intern 🐣"
    if score < 20:
        return "Junior 👶"
    if score < 50:
        return "Middle 😈"
    if score < 100:
        return "Senior 🦁"
    return "Tech Lead 👑"


@router.message(F.text == "👤 Мой профиль")
async def cmd_profile(message: types.Message):
    user_id = str(message.from_user.id)

    async with redis_client.pipeline() as pipe:
        pipe.get(f"stats:user:{user_id}:problems")
        pipe.get(f"stats:user:{user_id}:interviews")
        pipe.get(f"stats:user:{user_id}:questions")
        results = await pipe.execute()

    problems = int(results[0]) if results[0] else 0
    interviews = int(results[1]) if results[1] else 0
    questions = int(results[2]) if results[2] else 0

    rank = get_rank(problems, interviews, questions)

    text = (
        f"👤 <b>Профиль кандидата:</b> {message.from_user.full_name}\n\n"
        f"🏆 <b>Ранг:</b> {rank}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🧠 <b>LeetCode задач:</b> {problems}\n"
        f"🎤 <b>Интервью пройдено:</b> {interviews}\n"
        f"💬 <b>Вопросов разобрано:</b> {questions}\n\n"
        f"<i>Продолжай тренироваться, чтобы повысить ранг!</i>"
    )

    await message.answer(text, parse_mode="HTML")
