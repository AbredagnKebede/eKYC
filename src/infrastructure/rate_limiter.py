import time
import uuid
from typing import Tuple
import redis.asyncio as aioredis

from src.infrastructure.redis import get_redis_client


class SlidingWindowRateLimiter:
    """Sliding-window rate limiter implemented with Redis sorted sets (zset)."""

    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        self._client = redis_client

    def _get_client(self) -> aioredis.Redis:
        if self._client is not None:
            return self._client
        return get_redis_client()

    async def is_allowed(
        self,
        key: str,
        max_requests: int = 5,
        window_seconds: int = 60,
    ) -> Tuple[bool, int]:
        """
        Check if request is allowed under the sliding window limit.
        Returns:
            (allowed: bool, current_count: int)
        """
        client = self._get_client()
        redis_key = f"rate_limit:{key}"
        now = time.time()
        window_start = now - window_seconds
        unique_member = f"{now}:{uuid.uuid4().hex[:8]}"

        pipe = client.pipeline(transaction=True)
        # 1. Remove timestamps older than the sliding window
        pipe.zremrangebyscore(redis_key, 0, window_start)
        # 2. Add current timestamp
        pipe.zadd(redis_key, {unique_member: now})
        # 3. Count remaining requests in current window
        pipe.zcard(redis_key)
        # 4. Refresh key expiration
        pipe.expire(redis_key, window_seconds + 1)

        results = await pipe.execute()
        current_count = int(results[2])

        if current_count > max_requests:
            return False, current_count
        return True, current_count

    async def record_failure(
        self,
        key: str,
        window_seconds: int = 600,
    ) -> int:
        """
        Records a failed attempt (e.g. invalid Fayda format or wrong OTP).
        Returns the updated count of failures in the active window.
        """
        client = self._get_client()
        redis_key = f"failure_count:{key}"
        now = time.time()
        window_start = now - window_seconds
        member = f"{now}:{uuid.uuid4().hex[:6]}"

        pipe = client.pipeline(transaction=True)
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zadd(redis_key, {member: now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, window_seconds + 1)

        results = await pipe.execute()
        return int(results[2])

    async def get_failure_count(
        self,
        key: str,
        window_seconds: int = 600,
    ) -> int:
        """Get the count of failures in the current window."""
        client = self._get_client()
        redis_key = f"failure_count:{key}"
        now = time.time()
        window_start = now - window_seconds

        pipe = client.pipeline(transaction=True)
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        results = await pipe.execute()
        return int(results[1])

    async def reset(self, key: str) -> None:
        """Reset rate limiter and failure counters for a key."""
        client = self._get_client()
        await client.delete(f"rate_limit:{key}", f"failure_count:{key}")
