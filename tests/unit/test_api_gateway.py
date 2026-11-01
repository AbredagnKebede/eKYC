import base64
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.main import app, create_app
from src.api.middleware import (
    create_access_token,
    decode_access_token,
    require_auth,
)
from src.models.application import Application, ApplicationStatus, BankSubmission, IdentitySnapshot
from src.services.bank_adapter import BankNotFoundError, BankSchemaValidationError
from src.services.identity import (
    FaydaVerificationError,
    IdentityNotFoundError,
    LivenessVerificationError,
)
from src.services.onboarding import ApplicationNotFoundError, StateTransitionError

client = TestClient(app)


# ---- 1. Authentication & Middleware Tests ----
def test_create_and_decode_access_token() -> None:
    user_ref = "usr_test_123"
    device_fp = "device_fp_abc"
    token = create_access_token(user_ref=user_ref, device_fingerprint=device_fp)
    payload = decode_access_token(token)

    assert payload["sub"] == "usr_test_123"
    assert payload["device_fingerprint"] == "device_fp_abc"
    assert "exp" in payload
    assert "iat" in payload


def test_decode_access_token_expired() -> None:
    token = create_access_token(
        user_ref="usr_expired",
        device_fingerprint="dev_fp",
        expires_delta=timedelta(seconds=-10),
    )
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_decode_access_token_invalid_signature() -> None:
    token = create_access_token(
        user_ref="usr_tampered",
        device_fingerprint="dev_fp",
        secret_key="secret-key-a",
    )
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token, secret_key="secret-key-b")
    assert exc_info.value.status_code == 401
    assert "invalid" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_require_auth_missing_credentials() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_auth(credentials=None, x_device_fingerprint="fp1")
    assert exc_info.value.status_code == 401
    assert "Missing Authorization" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_auth_device_binding_mismatch() -> None:
    token = create_access_token(user_ref="usr_1", device_fingerprint="fp_original")
    credentials = MagicMock()
    credentials.credentials = token

    with pytest.raises(HTTPException) as exc_info:
        await require_auth(credentials=credentials, x_device_fingerprint="fp_different")
    assert exc_info.value.status_code == 403
    assert "Device binding mismatch" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_auth_success() -> None:
    token = create_access_token(user_ref="usr_valid", device_fingerprint="fp_match")
    credentials = MagicMock()
    credentials.credentials = token

    claims = await require_auth(credentials=credentials, x_device_fingerprint="fp_match")
    assert claims["sub"] == "usr_valid"
    assert claims["device_fingerprint"] == "fp_match"


def test_security_headers_present() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["x-xss-protection"] == "1; mode=block"
    assert "max-age=31536000" in resp.headers["strict-transport-security"]


# ---- 2. Bank Discovery API Routes ----
def test_list_partner_banks() -> None:
    resp = client.get("/v1/banks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    bank = next((b for b in data if b["bank_id"] == "bank_awash"), None)
    assert bank is not None
    assert bank["bank_name"] == "Awash Bank"
    assert "standard" in bank["supported_tiers"]
    assert "monthly_income_etb" in bank["dynamic_schema"]["properties"]


def test_get_partner_bank_found() -> None:
    resp = client.get("/v1/banks/bank_awash")
    assert resp.status_code == 200
    data = resp.json()
    assert data["bank_id"] == "bank_awash"
    assert data["bank_name"] == "Awash Bank"
    assert data["operational_status"] == "OPERATIONAL"


def test_get_partner_bank_not_found() -> None:
    resp = client.get("/v1/banks/bank_unknown_999")
    assert resp.status_code == 404
    data = resp.json()
    assert data["status"] == 404
    assert "not found" in data["detail"].lower()


# ---- 3. Applications Lifecycle API Routes ----
@pytest.mark.asyncio
async def test_create_application_success() -> None:
    mock_app = Application(
        id=uuid.uuid4(),
        user_ref="usr_alice",
        bank_id="bank_awash",
        tier="standard",
        status=ApplicationStatus.DRAFT,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    with patch("src.api.routes.applications._onboarding_service.create_application", AsyncMock(return_value=mock_app)):
        resp = client.post(
            "/v1/applications",
            json={"user_ref": "usr_alice", "bank_id": "bank_awash", "tier": "standard"},
            headers={"X-Device-Fingerprint": "fp_alice"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["application_id"] == str(mock_app.id)
        assert data["status"] == "DRAFT"
        assert "token" in data
        assert len(data["token"]) > 20


def test_create_application_invalid_bank() -> None:
    resp = client.post(
        "/v1/applications",
        json={"user_ref": "usr_bob", "bank_id": "bank_invalid", "tier": "standard"},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_application_details_success() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_detail",
        bank_id="bank_awash",
        tier="standard",
        status=ApplicationStatus.ACCOUNT_OPENED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    sub = BankSubmission(
        id=uuid.uuid4(),
        application_id=app_id,
        bank_id="bank_awash",
        account_number="1000123456789",
        bank_reference="AW-REF-9988",
    )
    mock_app.submissions = [sub]

    with patch("src.api.routes.applications._onboarding_service.get_application", AsyncMock(return_value=mock_app)):
        resp = client.get(f"/v1/applications/{app_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["application_id"] == str(app_id)
        assert data["status"] == "ACCOUNT_OPENED"
        assert data["account_number"] == "1000123456789"
        assert data["bank_reference"] == "AW-REF-9988"


@pytest.mark.asyncio
async def test_get_application_not_found() -> None:
    app_id = uuid.uuid4()
    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(side_effect=ApplicationNotFoundError(app_id)),
    ):
        resp = client.get(f"/v1/applications/{app_id}")
        assert resp.status_code == 404
        assert resp.json()["status"] == 404


@pytest.mark.asyncio
async def test_record_consent_accepted() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_consent",
        bank_id="bank_awash",
        status=ApplicationStatus.CONSENTED,
        consents=[],
    )

    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(return_value=mock_app),
    ), patch(
        "src.api.routes.applications._onboarding_service.record_consent",
        AsyncMock(return_value=mock_app),
    ):
        resp = client.post(
            f"/v1/applications/{app_id}/consent",
            json={"consent_version": "v1.0", "accepted": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["application_id"] == str(app_id)
        assert data["status"] == "CONSENTED"


@pytest.mark.asyncio
async def test_record_consent_refused_cancelled() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_refused",
        bank_id="bank_awash",
        status=ApplicationStatus.DRAFT,
    )

    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(return_value=mock_app),
    ), patch(
        "src.api.routes.applications._onboarding_service.audit_service.record_event",
        AsyncMock(),
    ):
        resp = client.post(
            f"/v1/applications/{app_id}/consent",
            json={"accepted": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["application_id"] == str(app_id)
        assert data["status"] == "CANCELLED"
        assert mock_app.status == ApplicationStatus.CANCELLED


@pytest.mark.asyncio
async def test_identity_start_consent_required() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_start",
        bank_id="bank_awash",
        status=ApplicationStatus.DRAFT,  # Not CONSENTED
    )

    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(return_value=mock_app),
    ):
        resp = client.post(
            f"/v1/applications/{app_id}/identity/start",
            json={"fin": "123456789012"},
        )
        assert resp.status_code == 403
        assert "CONSENT_REQUIRED" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_identity_start_invalid_fin_format() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_invalid_fin",
        bank_id="bank_awash",
        status=ApplicationStatus.CONSENTED,
    )

    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(return_value=mock_app),
    ):
        resp = client.post(
            f"/v1/applications/{app_id}/identity/start",
            json={"fin": "12345ABC"},  # Malformed FIN
            headers={"X-Device-Fingerprint": "fp_malformed_test"},
        )
        assert resp.status_code == 422
        assert "12 numeric digits" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_identity_start_success() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_valid_start",
        bank_id="bank_awash",
        status=ApplicationStatus.CONSENTED,
    )

    challenge_data = {"transaction_id": "tx_fayda_12345", "expires_in": 300}

    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(return_value=mock_app),
    ), patch(
        "src.api.routes.applications._identity_service.start_fayda_verification",
        AsyncMock(return_value=challenge_data),
    ):
        resp = client.post(
            f"/v1/applications/{app_id}/identity/start",
            json={"fin": "123456789012"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["transaction_id"] == "tx_fayda_12345"
        assert data["expires_in"] == 300


@pytest.mark.asyncio
async def test_identity_verify_success() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_ver",
        bank_id="bank_awash",
        status=ApplicationStatus.CONSENTED,
    )
    mock_snapshot = IdentitySnapshot(
        application_id=app_id,
        encrypted_full_name=b"enc_name",
        encrypted_dob=b"enc_dob",
        gender="MALE",
        fayda_ref_hash="hash_123",
        verified_at=datetime.now(timezone.utc),
    )

    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(return_value=mock_app),
    ), patch(
        "src.api.routes.applications._identity_service.verify_fayda_otp",
        AsyncMock(return_value=mock_snapshot),
    ):
        resp = client.post(
            f"/v1/applications/{app_id}/identity/verify",
            json={"transaction_id": "tx_123", "otp": "654321"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["application_id"] == str(app_id)
        assert data["status"] == "ID_VERIFIED"


@pytest.mark.asyncio
async def test_identity_verify_id_failed_state() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_failed",
        bank_id="bank_awash",
        status=ApplicationStatus.ID_FAILED,
    )

    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(return_value=mock_app),
    ):
        resp = client.post(
            f"/v1/applications/{app_id}/identity/verify",
            json={"transaction_id": "tx_999", "otp": "000000"},
        )
        assert resp.status_code == 409
        assert "ID_FAILED" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_liveness_verify_success() -> None:
    app_id = uuid.uuid4()
    selfie_b64 = base64.b64encode(b"live_selfie_bytes").decode()

    liveness_return = {
        "status": "LIVENESS_PASSED",
        "liveness_score": 0.97,
        "face_match_score": 0.94,
        "application_id": str(app_id),
    }

    with patch(
        "src.api.routes.applications._identity_service.verify_liveness_and_face",
        AsyncMock(return_value=liveness_return),
    ):
        resp = client.post(
            f"/v1/applications/{app_id}/liveness",
            json={"selfie_base64": selfie_b64},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "LIVENESS_PASSED"
        assert data["liveness_score"] == 0.97
        assert data["face_match_score"] == 0.94


@pytest.mark.asyncio
async def test_liveness_verify_spoof_rejection() -> None:
    app_id = uuid.uuid4()
    selfie_b64 = base64.b64encode(b"spoof_photo_bytes").decode()

    with patch(
        "src.api.routes.applications._identity_service.verify_liveness_and_face",
        AsyncMock(side_effect=LivenessVerificationError("Spoof replay detected", liveness_score=0.45, match_score=0.72)),
    ):
        resp = client.post(
            f"/v1/applications/{app_id}/liveness",
            json={"selfie_base64": selfie_b64},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["spoof_detected"] is True
        assert data["liveness_score"] == 0.45


@pytest.mark.asyncio
async def test_save_dynamic_fields_invalid_schema() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_fields",
        bank_id="bank_awash",
        status=ApplicationStatus.LIVENESS_PASSED,
    )

    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(return_value=mock_app),
    ):
        # Missing required monthly_income_etb, occupation, source_of_funds
        resp = client.put(
            f"/v1/applications/{app_id}/details",
            json={"dynamic_fields": {"random_field": "bad_data"}},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["status"] == 400
        assert "dynamic schema validation failed" in data["title"].lower()


@pytest.mark.asyncio
async def test_save_dynamic_fields_success() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_dyn_ok",
        bank_id="bank_awash",
        status=ApplicationStatus.DATA_COMPLETE,
    )
    valid_fields = {
        "monthly_income_etb": 50000,
        "occupation": "Surgeon",
        "source_of_funds": "Salary",
    }

    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(return_value=mock_app),
    ), patch(
        "src.api.routes.applications._onboarding_service.save_dynamic_fields",
        AsyncMock(return_value=mock_app),
    ):
        resp = client.put(
            f"/v1/applications/{app_id}/details",
            json={"dynamic_fields": valid_fields},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["application_id"] == str(app_id)
        assert data["status"] == "DATA_COMPLETE"
        assert data["dynamic_fields"]["monthly_income_etb"] == 50000


@pytest.mark.asyncio
async def test_submit_application_success() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_sub",
        bank_id="bank_awash",
        status=ApplicationStatus.SUBMITTED_TO_BANK,
        idempotency_hash="idem_12345",
    )

    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(return_value=mock_app),
    ), patch(
        "src.api.routes.applications._onboarding_service.submit_application",
        AsyncMock(return_value=mock_app),
    ):
        resp = client.post(
            f"/v1/applications/{app_id}/submit",
            json={"signature": "digital_signature_hash_xyz"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["application_id"] == str(app_id)
        assert data["status"] == "SUBMITTED_TO_BANK"
        assert data["idempotency_hash"] == "idem_12345"


# ---- 4. Bank CBS Webhook Callback Tests (J-08) ----
@pytest.mark.asyncio
async def test_bank_webhook_missing_signature() -> None:
    app_id = uuid.uuid4()
    resp = client.post(
        "/v1/webhooks/bank/bank_awash",
        json={"application_id": str(app_id), "status": "ACCOUNT_OPENED"},
    )
    assert resp.status_code == 401
    assert "missing" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bank_webhook_invalid_signature() -> None:
    app_id = uuid.uuid4()
    resp = client.post(
        "/v1/webhooks/bank/bank_awash",
        json={"application_id": str(app_id), "status": "ACCOUNT_OPENED"},
        headers={"X-Signature-SHA256": "tampered_bad_signature"},
    )
    assert resp.status_code == 401
    assert "invalid" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bank_webhook_valid_signature_success() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_webhook",
        bank_id="bank_awash",
        status=ApplicationStatus.SUBMITTED_TO_BANK,
        submissions=[],
    )

    payload_dict = {
        "application_id": str(app_id),
        "status": "ACCOUNT_OPENED",
        "account_number": "1000987654321",
        "bank_reference": "AW-CBS-9988",
    }
    import json
    raw_body = json.dumps(payload_dict).encode("utf-8")
    bank_key = os.getenv("BANK_API_KEY", "dev-bank-key")
    signature = hmac.new(bank_key.encode(), raw_body, hashlib.sha256).hexdigest()

    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(return_value=mock_app),
    ), patch(
        "src.api.routes.applications._onboarding_service.update_bank_status",
        AsyncMock(return_value=mock_app),
    ), patch(
        "src.api.routes.applications._onboarding_service.audit_service.record_event",
        AsyncMock(),
    ):
        resp = client.post(
            "/v1/webhooks/bank/bank_awash",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": signature,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "acknowledged"
        assert data["application_id"] == str(app_id)


@pytest.mark.asyncio
async def test_bank_webhook_idempotent_duplicate() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_webhook_dup",
        bank_id="bank_awash",
        status=ApplicationStatus.ACCOUNT_OPENED,
    )
    sub = BankSubmission(
        id=uuid.uuid4(),
        application_id=app_id,
        bank_id="bank_awash",
        account_number="1000987654321",
    )
    mock_app.submissions = [sub]

    payload_dict = {
        "application_id": str(app_id),
        "status": "ACCOUNT_OPENED",
        "account_number": "1000987654321",
    }
    import json
    raw_body = json.dumps(payload_dict).encode("utf-8")
    bank_key = os.getenv("BANK_API_KEY", "dev-bank-key")
    signature = hmac.new(bank_key.encode(), raw_body, hashlib.sha256).hexdigest()

    with patch(
        "src.api.routes.applications._onboarding_service.get_application",
        AsyncMock(return_value=mock_app),
    ):
        resp = client.post(
            "/v1/webhooks/bank/bank_awash",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": signature,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "acknowledged"
        assert data["idempotent"] is True


def test_health_live_endpoint() -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
    assert resp.json()["service"] == "ekyc-api-gateway"


@pytest.mark.asyncio
async def test_health_ready_degraded_when_db_fails() -> None:
    with patch("src.api.main.async_session_factory") as mock_session_factory, patch("src.api.main.get_redis_client") as mock_redis:
        mock_session_factory.side_effect = RuntimeError("Database unreachable")
        mock_redis_inst = AsyncMock()
        mock_redis_inst.ping.return_value = True
        mock_redis.return_value = mock_redis_inst

        resp = client.get("/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["components"]["database"] == "disconnected"
        assert data["components"]["redis"] == "connected"


@pytest.mark.asyncio
async def test_identity_start_lockout_after_multiple_failures() -> None:
    app_id = uuid.uuid4()
    mock_app = Application(
        id=app_id,
        user_ref="usr_lockout",
        bank_id="bank_awash",
        status=ApplicationStatus.CONSENTED,
    )

    mock_redis = AsyncMock()
    mock_redis.incr.return_value = 6  # Exceeded limit
    mock_redis.get.return_value = "6"

    from src.api.routes.applications import get_redis_dep
    app.dependency_overrides[get_redis_dep] = lambda: mock_redis

    try:
        with patch(
            "src.api.routes.applications._onboarding_service.get_application",
            AsyncMock(return_value=mock_app),
        ):
            resp = client.post(
                f"/v1/applications/{app_id}/identity/start",
                json={"fin": "bad_fin"},
            )
            assert resp.status_code == 429
            assert resp.headers["Retry-After"] == "900"
            assert "temporarily locked" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_redis_dep, None)
        from src.infrastructure.redis import close_redis_pool
        await close_redis_pool()


@pytest.mark.asyncio
async def test_lifespan_startup_and_teardown() -> None:
    from src.api.main import lifespan
    test_app = create_app()
    with patch("src.api.main.get_redis_client") as mock_get_redis:
        mock_redis = AsyncMock()
        mock_get_redis.return_value = mock_redis
        async with lifespan(test_app):
            pass
        mock_redis.aclose.assert_awaited_once()

