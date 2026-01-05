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


def get_deep_dive_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔍 Подробнее", callback_data="dive:details"),
        InlineKeyboardButton(text="👶 Объясни проще", callback_data="dive:simple"),
    )
    return builder.as_markup()


# --- LEETCODE KEYBOARDS ---


def get_categories_keyboard():
    builder = InlineKeyboardBuilder()
    categories = [
        ("Algorithms", "algorithms"),
        ("Pandas (DataFrames)", "pandas"),
        ("Database (SQL)", "database"),
    ]

    for name, slug in categories:
        builder.row(
            InlineKeyboardButton(text=f"📂 {name}", callback_data=f"lc:cat:{slug}")
        )

    return builder.as_markup()


def get_difficulty_keyboard(category: str):
    """Шаг 2: Выбор сложности для выбранной категории"""
    builder = InlineKeyboardBuilder()
    diffs = ["EASY", "MEDIUM", "HARD"]

    for d in diffs:
        if d == "EASY":
            d_display = f"😉 {d}"
        elif d == "MEDIUM":
            d_display = f"😮 {d}"
        elif d == "HARD":
            d_display = f"😈 {d}"
        else:
            d_display = f"❓ {d}"

        builder.row(
            InlineKeyboardButton(
                text=d_display, callback_data=f"lc:diff:{category}:{d}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="lc:menu")
    )
    return builder.as_markup()


def get_problems_list_keyboard(
    problems: list, offset: int, total: int, category: str, difficulty: str
):
    builder = InlineKeyboardBuilder()

    # Кнопки задач
    for p in problems:
        icon = "(Premium)" if p.get("paidOnly") else ""
        title = p["title"][:30] + "..." if len(p["title"]) > 30 else p["title"]
        text = f"{icon} {title}"
        builder.row(
            InlineKeyboardButton(
                text=text, callback_data=f"solve:{p['titleSlug']}"
            )
        )

    nav_buttons = []
    if offset > 0:
        prev_offset = max(0, offset - 10)
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"lc:list:{category}:{difficulty}:{prev_offset}",
            )
        )

    if offset + 10 < total:
        next_offset = offset + 10
        nav_buttons.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"lc:list:{category}:{difficulty}:{next_offset}",
            )
        )

    builder.row(*nav_buttons)
    builder.row(
        InlineKeyboardButton(
            text="🔙 К выбору сложности", callback_data=f"lc:cat:{category}"
        )
    )

    return builder.as_markup()


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
        )
    )
    return builder.as_markup()


def get_resume_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="▶️ Продолжить текущую", callback_data="task:resume"
        )
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Выбрать новую", callback_data="lc:menu")
    )
    return builder.as_markup()
