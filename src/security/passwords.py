"""Password hashing helpers for bank staff (PBKDF2)."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets


def hash_password(password: str, *, iterations: int = 200_000) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iters_s, salt, digest = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iters_s)
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return hmac.compare_digest(candidate, digest)


def default_staff_password() -> str:
    return os.getenv("BANK_PORTAL_BOOTSTRAP_PASSWORD", "ChangeMeBankPortal1!")
