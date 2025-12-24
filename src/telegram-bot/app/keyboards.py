from aiogram.types import InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🧠 LeetCode Тренировка"),
                KeyboardButton(text="🎤 Симуляция собеседования"),
            ],
            [
                KeyboardButton(text="❓ Задать вопрос (RAG)"),
                KeyboardButton(text="👤 Мой профиль"),
            ],
        ],
        resize_keyboard=True,
        persistent=True,
    )


def get_cancel_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Выйти в меню")]], resize_keyboard=True
    )


def get_persona_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="😇 HR-феечка (Soft)", callback_data="persona:friendly"
        ),
        InlineKeyboardButton(
            text="🤓 Нерд (Deep Tech)", callback_data="persona:nerd"
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="😈 Токсик-лид (Hard)", callback_data="persona:toxic"
        ),
    )
    return builder.as_markup()


def get_deep_dive_keyboard():
    """Кнопки под ответом бота"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔍 Подробнее", callback_data="dive:details"),
        InlineKeyboardButton(text="👶 Объясни проще", callback_data="dive:simple"),
    )
    return builder.as_markup()


def get_resume_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="▶️ Продолжить текущую", callback_data="task:resume"
        ),
        InlineKeyboardButton(text="🔄 Новая задача", callback_data="task:new"),
    )
    return builder.as_markup()


def get_problem_search_keyboard(problems):
    """Генерирует кнопки с результатами поиска"""
    builder = InlineKeyboardBuilder()
    for p in problems:
        builder.row(
            InlineKeyboardButton(
                text=f"{p['title']} ({p['difficulty']})",
                callback_data=f"solve:{p['titleSlug']}",
            )
        )
    builder.adjust(1)
    return builder.as_markup()
