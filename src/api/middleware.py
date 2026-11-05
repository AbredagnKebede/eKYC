import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

import jwt
from fastapi import Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from src.infrastructure.rate_limiter import SlidingWindowRateLimiter
from src.infrastructure.redis import get_redis_client

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-insecure-jwt-secret-replace-in-prod")
JWT_ALGORITHM = "HS256"
DEFAULT_TOKEN_EXPIRE_MINUTES = 15

security_bearer = HTTPBearer(auto_error=False)


def create_access_token(
    user_ref: str,
    device_fingerprint: str,
    expires_delta: Optional[timedelta] = None,
    secret_key: Optional[str] = None,
    extra_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Creates an HMAC-SHA256 signed JWT session token bound to a client device fingerprint."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=DEFAULT_TOKEN_EXPIRE_MINUTES))
    payload: Dict[str, Any] = {
        "sub": user_ref,
        "device_fingerprint": device_fingerprint,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)

    key = secret_key or JWT_SECRET_KEY
    return jwt.encode(payload, key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, secret_key: Optional[str] = None) -> Dict[str, Any]:
    """Decodes and validates JWT claims with signature and expiration checking."""
    key = secret_key or JWT_SECRET_KEY
    try:
        payload = jwt.decode(token, key, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired. Please authenticate again.",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token credentials.",
        ) from exc


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    x_device_fingerprint: Optional[str] = Header(None, alias="X-Device-Fingerprint"),
) -> Dict[str, Any]:
    """FastAPI dependency validating JWT bearer token and enforcing device fingerprint binding."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_access_token(credentials.credentials)

    # Device fingerprint is required and must match the token binding (§6.1)
    token_fingerprint = claims.get("device_fingerprint")
    if not x_device_fingerprint:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Device-Fingerprint header required for device-bound sessions.",
        )
    if not token_fingerprint or not secrets.compare_digest(
        str(token_fingerprint), str(x_device_fingerprint)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device binding mismatch: token is bound to a different client device.",
        )

    claims["_raw_token"] = credentials.credentials
    return claims


def assert_application_scope(claims: Dict[str, Any], application_id: str) -> None:
    """Legacy soft check: preferred application_id in JWT may differ for passport multi-app.

    Prefer assert_owns_application after loading the Application row.
    """
    # Kept for backwards compatibility; ownership is enforced via assert_owns_application.
    _ = (claims, application_id)


def assert_owns_application(claims: Dict[str, Any], user_ref: str) -> None:
    """Passport model: any application belonging to the JWT subject is accessible."""
    subject = str(claims.get("sub") or "")
    if not subject or not secrets.compare_digest(subject, str(user_ref)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is not authorized for this applicant profile.",
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces OWASP secure transport headers on all outgoing HTTP responses."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforces sliding-window request throttling backed by Redis."""

    def __init__(
        self,
        app: Any,
        rate_limiter: Optional[SlidingWindowRateLimiter] = None,
        max_requests: int = 120,
        window_seconds: int = 60,
    ) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter or SlidingWindowRateLimiter()
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Response:
        path = request.url.path
        if path.startswith("/health") or path.startswith("/docs") or path.startswith("/openapi.json"):
            return await call_next(request)

        # Identify client by device fingerprint or client IP
        client_key = (
            request.headers.get("X-Device-Fingerprint")
            or request.headers.get("X-Forwarded-For")
            or (request.client.host if request.client else "unknown-client")
        )

        try:
            allowed, current_count = await self.rate_limiter.is_allowed(
                key=f"api:{client_key}",
                max_requests=self.max_requests,
                window_seconds=self.window_seconds,
            )
            if not allowed:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "type": "https://errors.ekyc.et/RATE_LIMIT_EXCEEDED",
                        "title": "Rate Limit Exceeded",
                        "status": 429,
                        "detail": f"Request limit of {self.max_requests} requests per {self.window_seconds}s exceeded.",
                        "instance": request.url.path,
                    },
                    headers={"Retry-After": str(self.window_seconds)},
                )
        except Exception:
            # If Redis is temporarily unreachable, do not hard-block nominal user traffic
            pass

        return await call_next(request)
