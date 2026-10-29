import json
import secrets
import time
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

import redis.asyncio as aioredis
from src.infrastructure.redis import get_redis_client

DEFAULT_SESSION_TTL_SECONDS = 900  # 15 minutes


class SessionData(BaseModel):
    session_id: str
    user_ref: str
    device_fingerprint: str
    created_at: float
    last_accessed_at: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionManager:
    """Manages ephemeral user sessions in Redis with device binding and sliding TTL."""

    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        self._client = redis_client

    def _get_client(self) -> aioredis.Redis:
        if self._client is not None:
            return self._client
        return get_redis_client()

    def _key(self, token: str) -> str:
        return f"session:{token}"

    async def create_session(
        self,
        user_ref: str,
        device_fingerprint: str,
        ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionData:
        """Create and persist a new user session with client device binding."""
        client = self._get_client()
        token = secrets.token_urlsafe(32)
        now = time.time()

        session = SessionData(
            session_id=token,
            user_ref=user_ref,
            device_fingerprint=device_fingerprint,
            created_at=now,
            last_accessed_at=now,
            metadata=metadata or {},
        )

        payload = session.model_dump_json()
        await client.set(self._key(token), payload, ex=ttl_seconds)
        return session

    async def get_session(self, token: str) -> Optional[SessionData]:
        """Retrieve an active session by token."""
        client = self._get_client()
        payload = await client.get(self._key(token))
        if not payload:
            return None

        try:
            data = json.loads(payload)
            return SessionData(**data)
        except Exception:
            return None

    async def refresh_session(
        self,
        token: str,
        ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    ) -> bool:
        """Sliding window renewal of active session."""
        client = self._get_client()
        key = self._key(token)
        payload = await client.get(key)
        if not payload:
            return False

        try:
            data = json.loads(payload)
            data["last_accessed_at"] = time.time()
            updated_payload = json.dumps(data)
            await client.set(key, updated_payload, ex=ttl_seconds)
            return True
        except Exception:
            return False

    async def verify_device_binding(self, token: str, device_fingerprint: str) -> bool:
        """Verify that the caller's device fingerprint matches the session binding."""
        session = await self.get_session(token)
        if session is None:
            return False
        return session.device_fingerprint == device_fingerprint

    async def revoke_session(self, token: str) -> bool:
        """Explicitly revoke / delete session."""
        client = self._get_client()
        result = await client.delete(self._key(token))
        return bool(result > 0)
