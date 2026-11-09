"""Shared platform-operator JWT dependency (no route imports)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.middleware import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def require_platform_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing Authorization Bearer token.")
    claims = decode_access_token(credentials.credentials)
    if claims.get("portal_scope") != "platform":
        raise HTTPException(status_code=403, detail="Not a platform operator token.")
    if claims.get("role") != "PLATFORM_OPERATOR":
        raise HTTPException(status_code=403, detail="Insufficient platform role.")
    return claims
