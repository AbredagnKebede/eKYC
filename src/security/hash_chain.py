import hashlib
import hmac
import json
import os
from typing import Any, Dict, Optional

HMAC_SALT_KEY = os.getenv("HMAC_SALT_KEY", "dev-insecure-hmac-salt-replace-in-prod")
GENESIS_HASH = "0" * 64


def canonical_json(data: Dict[str, Any]) -> str:
    """Serializes a dictionary into a deterministic, canonical JSON string."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def compute_payload_hash(payload: Dict[str, Any] | str) -> str:
    """Computes SHA-256 hash of payload."""
    if isinstance(payload, dict):
        raw = canonical_json(payload)
    else:
        raw = str(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_chain_hash(
    prev_log_hash: str,
    log_id: int | str,
    timestamp_iso: str,
    actor_type: str,
    actor_id: str,
    action: str,
    application_id: Optional[str],
    payload_hash: str,
) -> str:
    """
    Computes cryptographic SHA-256 link connecting sequential audit entries.
    """
    app_str = str(application_id) if application_id is not None else "NONE"
    components = [
        prev_log_hash,
        str(log_id),
        timestamp_iso,
        actor_type,
        actor_id,
        action,
        app_str,
        payload_hash,
    ]
    raw_chain = ":".join(components)
    return hashlib.sha256(raw_chain.encode("utf-8")).hexdigest()


def compute_hmac_seal(chain_hash: str, secret_key: Optional[str] = None) -> str:
    """
    Generates HMAC-SHA256 seal for an audit row using the environment secret key.
    """
    key = (secret_key or HMAC_SALT_KEY).encode("utf-8")
    return hmac.new(key, chain_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_single_seal(chain_hash: str, signature: str, secret_key: Optional[str] = None) -> bool:
    """Verifies that the HMAC seal matches the expected signature."""
    expected = compute_hmac_seal(chain_hash, secret_key)
    return hmac.compare_digest(expected, signature)
