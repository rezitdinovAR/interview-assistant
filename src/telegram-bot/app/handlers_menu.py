from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from app.keyboards import get_main_menu
from app.redis_client import redis_client
from app.states import MainState

router = Router()


@router.message(Command("menu"))
@router.message(Command("start"))
@router.message(F.text == "❌ Выйти в меню")
async def cmd_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(MainState.chat)

    await redis_client.delete(f"active_request:{message.from_user.id}")

    await message.answer(
        "Вы в главном меню. Выберите режим работы:", reply_markup=get_main_menu()
    )


@router.message(F.text == "❓ Задать вопрос (RAG)")
async def switch_to_rag(message: types.Message, state: FSMContext):
    await state.set_state(MainState.chat)
    await message.answer(
        "Режим: <b>Вопрос-Ответ</b>.\n"
        "Спрашивайте что угодно по теории (Python, SQL, ML). Я поищу в базе знаний.",
        parse_mode="HTML",
    )
