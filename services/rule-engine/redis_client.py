import os
import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis_pool = None
client = None


async def init_redis():
    global redis_pool, client
    redis_pool = redis.ConnectionPool.from_url(REDIS_URL)
    client = redis.Redis(connection_pool=redis_pool)


async def close_redis():
    global client
    if client:
        await client.close()


async def check_velocity(entity_type: str, entity_value: str, window_seconds: int, limit: int) -> bool:
    """
    Increments the counter for a given entity and checks if it exceeds the limit.
    Uses Redis to increment and set expiration on the fly.
    """
    key = f"velocity:{entity_type}:{entity_value}"

    # We can use a simple INCR + EXPIRE if key is new.
    # A more robust sliding window could use ZSET with timestamps, but simple counter is faster.

    current_count = await client.incr(key)

    # If this is the first increment, set the expiry window
    if current_count == 1:
        await client.expire(key, window_seconds)

    return current_count > limit
