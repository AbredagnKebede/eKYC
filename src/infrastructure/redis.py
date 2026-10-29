import os
from typing import Optional
import redis.asyncio as aioredis

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

_redis_pool: Optional[aioredis.ConnectionPool] = None


def get_redis_pool() -> aioredis.ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            REDIS_URL,
            max_connections=20,
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
        )
    return _redis_pool


def get_redis_client() -> aioredis.Redis:
    pool = get_redis_pool()
    return aioredis.Redis(connection_pool=pool)


async def check_redis_health() -> bool:
    client = get_redis_client()
    try:
        pong = await client.ping()
        return bool(pong)
    except Exception:
        return False
    finally:
        await client.aclose()


async def close_redis_pool() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
