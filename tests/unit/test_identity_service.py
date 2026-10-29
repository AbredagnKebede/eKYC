import os
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.models.application import Application, ApplicationStatus, IdentitySnapshot, VerificationMethod
from src.security.encryption import (
    decrypt_bytes,
    decrypt_demographics,
    decrypt_str,
    encrypt_bytes,
    encrypt_demographics,
    encrypt_str,
    get_encryption_key,
    hash_fin,
)
from src.security.liveness import (
    FaceMatchResult,
    LivenessEngine,
    LivenessResult,
    cosine_similarity,
)
from src.services.identity import (
    IdentityError,
    IdentityNotFoundError,
    IdentityService,
    InvalidStateError,
    LivenessVerificationError,
)


def test_encryption_roundtrip_bytes_and_string() -> None:
    secret_text = "Citizen Demographic Confidential Data 2026"
    encrypted = encrypt_str(secret_text)
    assert isinstance(encrypted, bytes)
    assert len(encrypted) == len(secret_text) + 28  # 12-byte nonce + ciphertext + 16-byte tag
    assert secret_text.encode("utf-8") not in encrypted

    decrypted = decrypt_str(encrypted)
    assert decrypted == secret_text


def test_encryption_tamper_detection() -> None:
    original = b"Tamper-proof payload"
    envelope = bytearray(encrypt_bytes(original))
    # Modify last byte (part of auth tag)
    envelope[-1] ^= 0xFF

    with pytest.raises(Exception):
        decrypt_bytes(bytes(envelope))


def test_encryption_key_derivation_and_fallback() -> None:
    key1 = get_encryption_key()
    assert isinstance(key1, bytes)
    assert len(key1) == 32

    # Custom 32-byte key
    custom_key = b"01234567890123456789012345678901"
    enc = encrypt_str("Hello", key=custom_key)
    dec = decrypt_str(enc, key=custom_key)
    assert dec == "Hello"


def test_demographics_encryption_and_decryption_structure() -> None:
    demographics = {
        "full_name": "Almaz Ayana Dibaba",
        "date_of_birth": "1994-08-22",
        "gender": "FEMALE",
    }
    enc_name, enc_dob, gender = encrypt_demographics(demographics)
    assert isinstance(enc_name, bytes)
    assert isinstance(enc_dob, bytes)
    assert gender == "FEMALE"
    assert b"Almaz" not in enc_name
    assert b"1994" not in enc_dob

    decrypted = decrypt_demographics(enc_name, enc_dob, gender)
    assert decrypted["full_name"] == "Almaz Ayana Dibaba"
    assert decrypted["date_of_birth"] == "1994-08-22"
    assert decrypted["gender"] == "FEMALE"


def test_salted_fin_hashing_zero_retention() -> None:
    fin = "123456789012"
    h1 = hash_fin(fin)
    assert len(h1) == 64
    assert h1 != fin

    # Deterministic with same salt
    h2 = hash_fin(fin)
    assert h1 == h2

    # Different salt produces distinct cryptographic output
    h_custom_salt = hash_fin(fin, salt="different_salt_1234")
    assert h_custom_salt != h1
    assert len(h_custom_salt) == 64

    # Invalid FIN format rejected
    with pytest.raises(ValueError):
        hash_fin("1234")
    with pytest.raises(ValueError):
        hash_fin("nonnumericfin")


def test_liveness_engine_live_and_spoof_detection() -> None:
    engine = LivenessEngine()

    # 1. Compliant live camera feed
    live_frames = b"camera_frame_live_dynamic_features_1234567890abcdef" * 3
    live_res = engine.evaluate_liveness(live_frames)
    assert live_res.is_live is True
    assert live_res.liveness_score >= 0.90
    assert len(live_res.reasons) == 0

    # 2. Spoof attack presentation
    spoof_frames = b"synthetic_spoof_attack_presentation_sample_data"
    spoof_res = engine.evaluate_liveness(spoof_frames)
    assert spoof_res.is_live is False
    assert spoof_res.liveness_score < 0.90
    assert "presentation attack" in spoof_res.reasons[0].lower()

    # 3. Static image with zero variance
    static_frames = b"0" * 40
    static_res = engine.evaluate_liveness(static_frames)
    assert static_res.is_live is False
    assert static_res.liveness_score < 0.90
    assert "zero variance" in static_res.reasons[0].lower()

    # 4. Empty frames
    empty_res = engine.evaluate_liveness(b"")
    assert empty_res.is_live is False
    assert empty_res.liveness_score == 0.0


def test_face_comparison_match_and_mismatch() -> None:
    engine = LivenessEngine()

    selfie = b"alemu_live_highres_selfie_feed_data"
    fayda_photo = b"fayda_id_photo_alemu_citizen_archive_sample"

    match_res = engine.compare_faces(selfie, fayda_photo)
    assert match_res.is_match is True
    assert match_res.similarity_score >= 0.82
    assert "verified" in match_res.details.lower()

    # Impostor attempt
    impostor_selfie = b"impostor_trying_to_bypass_kyc"
    impostor_res = engine.compare_faces(impostor_selfie, fayda_photo)
    assert impostor_res.is_match is False
    assert impostor_res.similarity_score < 0.82
    assert "different individuals" in impostor_res.details.lower()

    # Missing inputs
    empty_res = engine.compare_faces(b"", fayda_photo)
    assert empty_res.is_match is False
    assert empty_res.similarity_score == 0.0


def test_biometric_purge_zero_retention() -> None:
    buf = bytearray(b"sensitive_biometric_face_vector")
    LivenessEngine.purge_biometric_data(buf)
    assert all(b == 0 for b in buf)


@pytest.mark.asyncio
async def test_identity_service_invalid_state_rejection() -> None:
    mock_fayda = MagicMock()
    mock_audit = MagicMock()
    service = IdentityService(fayda_client=mock_fayda, audit_service=mock_audit)

    mock_app = Application(
        id=uuid.uuid4(),
        user_ref="usr_test_123",
        bank_id="awash",
        status=ApplicationStatus.CANCELLED,
        expires_at=datetime.now(timezone.utc),
    )

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_app
    mock_session.execute.return_value = mock_res

    with pytest.raises(InvalidStateError) as exc_info:
        await service.start_fayda_verification(mock_app.id, "123456789012", mock_session)

    assert "Cannot initiate Fayda verification in status" in str(exc_info.value)
    assert mock_fayda.generate_otp.call_count == 0


@pytest.mark.asyncio
async def test_identity_service_liveness_failure_handling() -> None:
    mock_fayda = MagicMock()
    mock_audit = AsyncMock()
    mock_engine = MagicMock()
    mock_engine.evaluate_liveness.return_value = LivenessResult(
        is_live=False, liveness_score=0.30, reasons=["Spoof detected"]
    )
    mock_engine.compare_faces.return_value = FaceMatchResult(
        is_match=False, similarity_score=0.40, details="Failed match"
    )

    service = IdentityService(
        fayda_client=mock_fayda,
        liveness_engine=mock_engine,
        audit_service=mock_audit,
    )

    mock_app = Application(
        id=uuid.uuid4(),
        user_ref="usr_test_123",
        bank_id="awash",
        status=ApplicationStatus.ID_VERIFIED,
        expires_at=datetime.now(timezone.utc),
    )
    mock_snapshot = IdentitySnapshot(
        application_id=mock_app.id,
        encrypted_full_name=b"enc_name",
        encrypted_dob=b"enc_dob",
        gender="MALE",
        fayda_ref_hash="hash123",
    )

    mock_session = AsyncMock()
    mock_res_app = MagicMock()
    mock_res_app.scalar_one_or_none.return_value = mock_app
    mock_res_snap = MagicMock()
    mock_res_snap.scalar_one_or_none.return_value = mock_snapshot
    mock_session.execute.side_effect = [mock_res_app, mock_res_snap]

    with pytest.raises(LivenessVerificationError) as exc_info:
        await service.verify_liveness_and_face(
            mock_app.id,
            b"fake_selfie_bytes",
            b"fayda_photo",
            session=mock_session,
        )

    assert exc_info.value.liveness_score == 0.30
    assert mock_app.status == ApplicationStatus.LIVENESS_FAILED
    assert mock_audit.record_event.call_count == 1
    assert mock_session.commit.call_count == 1


def test_encryption_env_key_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    import base64

    # 1. Base64 32-byte key
    b64_key = base64.b64encode(b"01234567890123456789012345678901").decode("utf-8")
    monkeypatch.setenv("PII_ENCRYPTION_KEY", b64_key)
    k1 = get_encryption_key()
    assert len(k1) == 32
    assert k1 == b"01234567890123456789012345678901"

    # 2. Arbitrary string (SHA-256 derivation)
    monkeypatch.setenv("PII_ENCRYPTION_KEY", "arbitrary_secret_passphrase_for_testing")
    k2 = get_encryption_key()
    assert len(k2) == 32

    # 3. Invalid types in encrypt_bytes and decrypt_bytes
    with pytest.raises(TypeError):
        encrypt_bytes("not bytes")  # type: ignore
    with pytest.raises(TypeError):
        decrypt_bytes("not bytes")  # type: ignore
    with pytest.raises(ValueError):
        decrypt_bytes(b"short")


def test_liveness_low_resolution_frame() -> None:
    engine = LivenessEngine()
    res = engine.evaluate_liveness(b"short123")
    assert res.is_live is False
    assert res.liveness_score == 0.10
    assert "below minimum" in res.reasons[0].lower()


@pytest.mark.asyncio
async def test_identity_service_not_found_scenarios() -> None:
    service = IdentityService()
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_res

    missing_id = uuid.uuid4()
    with pytest.raises(IdentityNotFoundError):
        await service.start_fayda_verification(missing_id, "123456789012", mock_session)

    with pytest.raises(IdentityNotFoundError):
        await service.get_decrypted_demographics(missing_id, mock_session)

