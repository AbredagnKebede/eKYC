import hashlib
import hmac
import pytest

from src.security.hash_chain import (
    GENESIS_HASH,
    canonical_json,
    compute_chain_hash,
    compute_hmac_seal,
    compute_payload_hash,
    verify_single_seal,
)


def test_genesis_hash_constant() -> None:
    assert len(GENESIS_HASH) == 64
    assert GENESIS_HASH == "0" * 64


def test_canonical_json_ordering() -> None:
    dict1 = {"b": 2, "a": 1, "c": 3}
    dict2 = {"a": 1, "c": 3, "b": 2}
    s1 = canonical_json(dict1)
    s2 = canonical_json(dict2)
    assert s1 == s2
    assert s1 == '{"a":1,"b":2,"c":3}'


def test_compute_payload_hash_deterministic() -> None:
    payload = {"action": "CONSENT_ACCEPTED", "version": "1.0"}
    h1 = compute_payload_hash(payload)
    h2 = compute_payload_hash({"version": "1.0", "action": "CONSENT_ACCEPTED"})
    assert len(h1) == 64
    assert h1 == h2
    assert h1 == hashlib.sha256(b'{"action":"CONSENT_ACCEPTED","version":"1.0"}').hexdigest()


def test_chain_hash_computation() -> None:
    prev_hash = GENESIS_HASH
    chain_hash = compute_chain_hash(
        prev_log_hash=prev_hash,
        log_id=1,
        timestamp_iso="2026-10-29T12:00:00Z",
        actor_type="CUSTOMER",
        actor_id="dev_user_01",
        action="LOGIN",
        application_id="app_uuid_123",
        payload_hash="dummy_payload_hash_456",
    )
    assert len(chain_hash) == 64
    expected_raw = f"{prev_hash}:1:2026-10-29T12:00:00Z:CUSTOMER:dev_user_01:LOGIN:app_uuid_123:dummy_payload_hash_456"
    assert chain_hash == hashlib.sha256(expected_raw.encode("utf-8")).hexdigest()


def test_hmac_seal_verification() -> None:
    chain_hash = "abc123chainhash456789"
    secret = "test-secret-salt-key-999"
    seal = compute_hmac_seal(chain_hash, secret)
    assert len(seal) == 64
    assert verify_single_seal(chain_hash, seal, secret) is True
    assert verify_single_seal("tampered_hash", seal, secret) is False
    assert verify_single_seal(chain_hash, "tampered_seal", secret) is False
