from aiogram.fsm.state import State, StatesGroup


class MainState(StatesGroup):
    chat = State()  # Обычный режим (Free Chat + RAG)


class LeetCodeState(StatesGroup):
    menu = State()  # Выбор типа задачи
    solving_problem = State()  # Ждем код решения


class InterviewState(StatesGroup):
    setup = State()  # Выбор темы (Python, ML, SQL)
    in_progress = State()  # Процесс собеседования
    feedback = State()  # Финальный фидбек
