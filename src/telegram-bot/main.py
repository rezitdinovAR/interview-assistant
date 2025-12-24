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
from app.middlewares import AccessMiddleware, VoiceToTextMiddleware
from app.redis_client import redis_client
from loguru import logger


async def main():
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = RedisStorage(redis_client)
    dp = Dispatcher(storage=storage)

    dp.message.outer_middleware(AccessMiddleware())
    dp.message.outer_middleware(VoiceToTextMiddleware())

    dp.include_router(admin_router)
    dp.include_router(menu_router)
    dp.include_router(profile_router)
    dp.include_router(interview_router)
    dp.include_router(leetcode_router)
    dp.include_router(common_router)
    dp.include_router(chat_router)

    static_whitelist = settings.get_whitelist_ids
    if static_whitelist:
        ids_to_add = [str(uid) for uid in static_whitelist]
        await redis_client.sadd("user:whitelist", *ids_to_add)
        logger.debug(f"Loaded {len(ids_to_add)} users to whitelist from env")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
