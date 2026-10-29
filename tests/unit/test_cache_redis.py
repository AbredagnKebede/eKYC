import time
import pytest

from src.infrastructure.session import SessionData, SessionManager
from src.infrastructure.rate_limiter import SlidingWindowRateLimiter
from src.infrastructure.redis import REDIS_URL


def test_session_data_model_serialization() -> None:
    now = time.time()
    session = SessionData(
        session_id="token_abc_12345",
        user_ref="usr_778899",
        device_fingerprint="device_android_xyz",
        created_at=now,
        last_accessed_at=now,
        metadata={"preferred_language": "am", "bank_choice": "bank_awash"},
    )
    assert session.session_id == "token_abc_12345"
    assert session.user_ref == "usr_778899"
    assert session.device_fingerprint == "device_android_xyz"
    assert session.created_at == now
    assert session.metadata["preferred_language"] == "am"
    assert session.metadata["bank_choice"] == "bank_awash"

    dumped_json = session.model_dump_json()
    reconstructed = SessionData.model_validate_json(dumped_json)
    assert reconstructed.session_id == "token_abc_12345"
    assert reconstructed.user_ref == "usr_778899"
    assert reconstructed.device_fingerprint == "device_android_xyz"
    assert reconstructed.metadata["preferred_language"] == "am"


def test_session_manager_key_formatting() -> None:
    manager = SessionManager()
    formatted = manager._key("test_token_999")
    assert formatted == "session:test_token_999"


def test_redis_default_url_configuration() -> None:
    assert "redis://" in REDIS_URL
    assert "6379" in REDIS_URL
