import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from app.config import settings
from app.handlers import router as chat_router
from app.handlers_admin import router as admin_router
from app.handlers_common import router as common_router
from app.handlers_interview import router as interview_router
from app.handlers_leetcode import router as leetcode_router
from app.handlers_menu import router as menu_router
from app.handlers_profile import router as profile_router
from app.middlewares import AccessMiddleware
from app.redis_client import redis_client
from app.handlers_voice import router as voice_router

async def main():
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = RedisStorage(redis_client)
    dp = Dispatcher(storage=storage)

    dp.message.outer_middleware(AccessMiddleware())

    dp.include_router(admin_router)
    dp.include_router(menu_router)
    dp.include_router(profile_router)
    dp.include_router(interview_router)
    dp.include_router(leetcode_router)
    dp.include_router(voice_router)
    dp.include_router(common_router)
    dp.include_router(chat_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
