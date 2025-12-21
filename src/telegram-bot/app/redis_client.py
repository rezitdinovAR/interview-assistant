from app.config import settings
from redis.asyncio import Redis

redis_client = Redis.from_url(
    settings.redis_uri, decode_responses=True, encoding="utf-8"
)


async def get_redis():
    return redis_client
