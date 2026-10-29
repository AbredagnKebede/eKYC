import os
import time
import pytest

from src.infrastructure.redis import (
    REDIS_URL,
    get_redis_client,
    check_redis_health,
    close_redis_pool,
)
from src.infrastructure.rate_limiter import SlidingWindowRateLimiter
from src.infrastructure.session import SessionManager, SessionData

# Real database boundary attribution
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")


@pytest.mark.asyncio
async def test_real_redis_connectivity_and_ping() -> None:
    assert "redis://" in REDIS_URL
    assert "postgresql" in DATABASE_URL
    client = get_redis_client()
    try:
        pong = await client.ping()
        assert pong is True
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_real_redis_session_lifecycle_and_device_binding() -> None:
    client = get_redis_client()
    manager = SessionManager(redis_client=client)

    token_ref = "test_user_session_token_1"
    device_fp = "android_device_fingerprint_secure_uuid"

    try:
        # 1. Create Session
        created = await manager.create_session(
            user_ref="usr_habtam_001",
            device_fingerprint=device_fp,
            ttl_seconds=30,
            metadata={"bank": "bank_awash"},
        )
        assert created.user_ref == "usr_habtam_001"
        assert created.device_fingerprint == device_fp
        assert created.metadata["bank"] == "bank_awash"

        # 2. Retrieve Session
        retrieved = await manager.get_session(created.session_id)
        assert retrieved.user_ref == "usr_habtam_001"
        assert retrieved.session_id == created.session_id
        assert retrieved.user_ref == "usr_habtam_001"

        # 3. Verify Device Binding (matching vs non-matching device)
        valid_binding = await manager.verify_device_binding(created.session_id, device_fp)
        assert valid_binding is True

        invalid_binding = await manager.verify_device_binding(created.session_id, "rogue_device_fp_malicious")
        assert invalid_binding is False

        # 4. Refresh Session
        refreshed = await manager.refresh_session(created.session_id, ttl_seconds=60)
        assert refreshed is True

        # 5. Revoke Session
        revoked = await manager.revoke_session(created.session_id)
        assert revoked is True

        post_revoke = await manager.get_session(created.session_id)
        assert post_revoke is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_real_redis_sliding_window_rate_limiting() -> None:
    client = get_redis_client()
    limiter = SlidingWindowRateLimiter(redis_client=client)
    test_key = "test_device_addis_rate_limit"

    try:
        await limiter.reset(test_key)

        # First 3 requests must be allowed under max_requests=3
        r1, count1 = await limiter.is_allowed(test_key, max_requests=3, window_seconds=10)
        assert r1 is True
        assert count1 == 1

        r2, count2 = await limiter.is_allowed(test_key, max_requests=3, window_seconds=10)
        assert r2 is True
        assert count2 == 2

        r3, count3 = await limiter.is_allowed(test_key, max_requests=3, window_seconds=10)
        assert r3 is True
        assert count3 == 3

        # 4th request exceeds max_requests=3, must be rejected
        r4, count4 = await limiter.is_allowed(test_key, max_requests=3, window_seconds=10)
        assert r4 is False
        assert count4 == 4

        # Test failure counter tracking (AS-03 lockout support)
        f1 = await limiter.record_failure(test_key, window_seconds=10)
        assert f1 == 1

        f2 = await limiter.record_failure(test_key, window_seconds=10)
        assert f2 == 2

        current_f = await limiter.get_failure_count(test_key, window_seconds=10)
        assert current_f == 2

        await limiter.reset(test_key)
        reset_f = await limiter.get_failure_count(test_key, window_seconds=10)
        assert reset_f == 0
    finally:
        await client.aclose()
