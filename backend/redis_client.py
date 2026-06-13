"""Redis connection singleton."""

import redis.asyncio as redis

from backend.config import settings

redis_client: redis.Redis = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
)


async def get_redis() -> redis.Redis:
    """FastAPI dependency — returns the shared Redis client."""
    return redis_client
