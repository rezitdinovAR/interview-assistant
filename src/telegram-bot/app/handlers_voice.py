import httpx
from aiogram import Bot, F, Router, types
from aiogram.fsm.context import FSMContext
from app.config import settings
from app.handlers import process_user_request
from app.handlers_interview import process_answer as interview_answer
from app.handlers_leetcode import process_solution as leetcode_solution
from app.states import InterviewState, LeetCodeState

router = Router()


async def transcribe_voice(bot: Bot, voice: types.Voice) -> str:
    file_id = voice.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path

    voice_io = await bot.download_file(file_path)

    # Отправляем в сервис
    async with httpx.AsyncClient() as client:
        files = {"file": ("voice.ogg", voice_io, "audio/ogg")}
        try:
            resp = await client.post(
                f"{settings.transcribe_service_url}/transcribe",
                files=files,
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json().get("text", "")
        except Exception as e:
            print(f"Transcribe error: {e}")
            return ""


@router.message(F.voice)
async def handle_voice_message(
    message: types.Message, state: FSMContext, bot: Bot
):
    processing_msg = await message.reply("👂 Слушаю...")

    text = await transcribe_voice(bot, message.voice)

    await processing_msg.delete()

    if not text:
        await message.reply("Не удалось распознать речь.")
        return

    message = message.model_copy(update={"text": text})

    # Визуально показываем пользователю, что мы услышали
    await message.answer(f'🗣 <i>Распознано:</i> "{text}"', parse_mode="HTML")

    # Теперь нужно понять, в каком мы состоянии, и вызвать нужную функцию
    current_state = await state.get_state()

    if current_state == InterviewState.in_progress:
        # Вызываем хендлер ответа на интервью
        await interview_answer(message, state)

    elif current_state == LeetCodeState.solving_problem:
        # Вызываем хендлер решения
        await leetcode_solution(message, state)

    else:
        # Обычный чат
        await process_user_request(message, text, state)
