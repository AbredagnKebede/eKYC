import base64
import hashlib
import hmac
import os
import re
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# 256-bit (32 bytes) master key for AES-GCM
DEFAULT_DEV_KEY = b"ekyc_master_aes256_dev_key_32b!!"
FIN_SALT_DEFAULT = "ekyc_fin_salt_2026_ethiopia_nidp_secure"


def get_encryption_key() -> bytes:
    """Retrieve 32-byte AES key from PII_ENCRYPTION_KEY or return dev fallback."""
    env_key = os.getenv("PII_ENCRYPTION_KEY")
    if not env_key:
        return DEFAULT_DEV_KEY

    # Try base64 decoding
    try:
        decoded = base64.b64decode(env_key)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass

    raw_bytes = env_key.encode("utf-8")
    if len(raw_bytes) == 32:
        return raw_bytes

    # Derive 32 bytes via SHA-256 if arbitrary string is provided
    return hashlib.sha256(raw_bytes).digest()


def get_fin_salt() -> str:
    """Retrieve secret salt for Fayda FIN/FAN hashing."""
    return os.getenv("FIN_HASH_SALT", FIN_SALT_DEFAULT)


def hash_fin(fin: str, salt: Optional[str] = None) -> str:
    """
    Hash 12-digit Fayda FIN/FAN using salted HMAC-SHA256 (ADR-006 zero-retention).
    Never stores or retains raw national ID numbers in plaintext.
    """
    clean_fin = str(fin).strip()
    if not re.fullmatch(r"\d{12}", clean_fin):
        raise ValueError("Fayda FIN must be exactly 12 numeric digits.")

    active_salt = salt if salt is not None else get_fin_salt()
    hasher = hmac.new(
        active_salt.encode("utf-8"),
        clean_fin.encode("utf-8"),
        hashlib.sha256,
    )
    return hasher.hexdigest()


def encrypt_bytes(data: bytes, key: Optional[bytes] = None) -> bytes:
    """
    Encrypt plaintext bytes using AES-256-GCM.
    Returns: 12-byte nonce prepended to authenticated ciphertext.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError(f"Data must be bytes, got {type(data)}")

    active_key = key if key is not None else get_encryption_key()
    aesgcm = AESGCM(active_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, bytes(data), associated_data=None)
    return nonce + ciphertext


def decrypt_bytes(envelope: bytes, key: Optional[bytes] = None) -> bytes:
    """
    Decrypt envelope (12-byte nonce + ciphertext + 16-byte tag) using AES-256-GCM.
    """
    if not isinstance(envelope, (bytes, bytearray)):
        raise TypeError(f"Envelope must be bytes, got {type(envelope)}")
    if len(envelope) < 28:
        raise ValueError("Invalid ciphertext envelope: insufficient length.")

    active_key = key if key is not None else get_encryption_key()
    nonce = envelope[:12]
    ciphertext = envelope[12:]
    aesgcm = AESGCM(active_key)
    return aesgcm.decrypt(nonce, ciphertext, associated_data=None)


def encrypt_str(text: str, key: Optional[bytes] = None) -> bytes:
    """Encrypt a string to AES-256-GCM bytes envelope."""
    return encrypt_bytes(text.encode("utf-8"), key=key)


def decrypt_str(envelope: bytes, key: Optional[bytes] = None) -> str:
    """Decrypt AES-256-GCM bytes envelope to UTF-8 string."""
    return decrypt_bytes(envelope, key=key).decode("utf-8")


def encrypt_demographics(
    demographics: Dict[str, Any], key: Optional[bytes] = None
) -> Tuple[bytes, bytes, str]:
    """
    Extract and encrypt demographic attributes for IdentitySnapshot persistence.
    Returns (encrypted_full_name, encrypted_dob, gender).
    """
    full_name = str(demographics.get("full_name", ""))
    dob = str(demographics.get("date_of_birth", ""))
    gender = str(demographics.get("gender", "UNKNOWN")).upper()

    enc_name = encrypt_str(full_name, key=key)
    enc_dob = encrypt_str(dob, key=key)
    return enc_name, enc_dob, gender


def decrypt_demographics(
    encrypted_full_name: bytes,
    encrypted_dob: bytes,
    gender: str,
    key: Optional[bytes] = None,
) -> Dict[str, str]:
    """
    Decrypt stored demographic byte arrays into plaintext dictionary.
    """
    full_name = decrypt_str(encrypted_full_name, key=key)
    dob = decrypt_str(encrypted_dob, key=key)
    return {
        "full_name": full_name,
        "date_of_birth": dob,
        "gender": gender,
    }
