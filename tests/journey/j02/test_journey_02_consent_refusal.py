import asyncio
import os
import time
import uuid
from typing import Any, Dict

import httpx
import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models.application import Application, ApplicationStatus, IdentitySnapshot
from src.models.audit import AuditLog
from src.security.hash_chain import compute_payload_hash
from src.services.audit import AuditService

pytestmark = [pytest.mark.asyncio, pytest.mark.black_box]


@pytest.mark.black_box
async def test_journey_02_consent_refusal_e2e() -> None:
    """
    End-to-end user journey test for citizen consent refusal and safe flow cancellation (J-02).

    Covers architectural requirements AS-02:
    - Real PostgreSQL database connection via DATABASE_URL and asyncpg driver (no mocks).
    - Session cancellation and zero PII persistence.
    - Audit event logging with client device fingerprint.
    - Security guard blocking identity verification without consent.

    Assertion Points Verified:
    - AP-1 Database: applications record transitions directly to status='CANCELLED'
    - AP-2 Database: identity_snapshots has 0 rows for this application ID
    - AP-3 Audit: audit_logs records a single CONSENT_REFUSED event with actor and device metadata
    - AP-4 API response: POST /v1/applications/{id}/identity/start returns HTTP 403 Forbidden with CONSENT_REQUIRED
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
    jwt_secret = os.getenv("JWT_SECRET_KEY", "dev-insecure-jwt-secret-replace-in-prod")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    test_user_ref = f"usr_j02_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Fingerprint": device_fp}

    async with httpx.AsyncClient(base_url=api_base_url, timeout=10.0) as client:
        # -------------------------------------------------------------------------
        # Step 1: User selects Dashen Bank from bank discovery catalog
        # -------------------------------------------------------------------------
        create_resp = await client.post(
            "/v1/applications",
            json={"user_ref": test_user_ref, "bank_id": "bank_awash", "tier": "standard"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        create_data = create_resp.json()
        assert create_data["status"] == "DRAFT"
        app_id_str = create_data["application_id"]
        app_uuid = uuid.UUID(app_id_str)
        session_token = create_data["token"]
        assert len(session_token) > 20

        client.headers.update({
            "Authorization": f"Bearer {session_token}",
            "X-Device-Fingerprint": device_fp,
        })

        # -------------------------------------------------------------------------
        # CH-01: Expired session token during consent review rejects further actions with HTTP 401
        # -------------------------------------------------------------------------
        expired_payload = {
            "sub": test_user_ref,
            "device_fingerprint": device_fp,
            "iat": int(time.time()) - 7200,
            "exp": int(time.time()) - 3600,
        }
        expired_token = jwt.encode(expired_payload, jwt_secret, algorithm="HS256")
        expired_resp = await client.post(
            f"/v1/applications/{app_id_str}/consent",
            json={"accepted": False, "device_fingerprint": device_fp},
            headers={"Authorization": f"Bearer {expired_token}", "X-Device-Fingerprint": device_fp},
        )
        assert expired_resp.status_code == 401
        assert "expired" in expired_resp.json().get("detail", "").lower()

        # -------------------------------------------------------------------------
        # Steps 2-4: User views consent screen and taps "Decline and Exit"
        # -------------------------------------------------------------------------
        refusal_resp = await client.post(
            f"/v1/applications/{app_id_str}/consent",
            json={"accepted": False, "device_fingerprint": device_fp, "ip_address": "127.0.0.1"},
            headers={"Authorization": f"Bearer {session_token}", "X-Device-Fingerprint": device_fp},
        )
        assert refusal_resp.status_code == 200
        refusal_data = refusal_resp.json()
        assert refusal_data["status"] == "CANCELLED"
        assert refusal_data["application_id"] == app_id_str

        # -------------------------------------------------------------------------
        # AP-1 Database: applications record transitions directly to status='CANCELLED'
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            app_stmt = select(Application).where(Application.id == app_uuid)
            app_record = (await session.execute(app_stmt)).scalar_one_or_none()
            assert app_record is not None
            assert app_record.status == ApplicationStatus.CANCELLED
            assert app_record.status.value == "CANCELLED"
            assert app_record.user_ref == test_user_ref
            assert app_record.bank_id == "bank_awash"

        # -------------------------------------------------------------------------
        # AP-2 Database: identity_snapshots has 0 rows for this application ID
        # Zero personal demographic data, biometric artifacts, or identifiers stored
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            snapshot_stmt = select(IdentitySnapshot).where(IdentitySnapshot.application_id == app_uuid)
            snapshot_records = (await session.execute(snapshot_stmt)).scalars().all()
            assert len(snapshot_records) == 0

        # -------------------------------------------------------------------------
        # AP-3 Audit: audit_logs records a single CONSENT_REFUSED event with actor and device metadata
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            audit_stmt = select(AuditLog).where(AuditLog.application_id == app_uuid)
            audit_records = (await session.execute(audit_stmt)).scalars().all()
            consent_refused_records = [rec for rec in audit_records if rec.action == "CONSENT_REFUSED"]
            assert len(consent_refused_records) == 1
            audit_event = consent_refused_records[0]
            assert audit_event.action == "CONSENT_REFUSED"
            assert audit_event.actor_type == "CUSTOMER"
            assert audit_event.actor_id == test_user_ref
            assert audit_event.payload_hash is not None
            assert len(audit_event.payload_hash) == 64
            expected_payload_hash = compute_payload_hash({"ip_address": "127.0.0.1", "device_fingerprint": device_fp})
            assert audit_event.payload_hash == expected_payload_hash
            assert len(audit_event.prev_log_hash) == 64
            assert len(audit_event.hmac_signature) == 64

            # Verify cryptographic ledger hash integrity
            audit_service = AuditService()
            is_valid, err_msg = await audit_service.verify_ledger_integrity(session)
            assert is_valid is True
            assert err_msg is None

        # -------------------------------------------------------------------------
        # AP-4 API response: POST /v1/applications/{id}/identity/start returns HTTP 403 Forbidden with CONSENT_REQUIRED
        # -------------------------------------------------------------------------
        identity_start_resp = await client.post(
            f"/v1/applications/{app_id_str}/identity/start",
            json={"fin": "123456789012"},
            headers={"Authorization": f"Bearer {session_token}", "X-Device-Fingerprint": device_fp},
        )
        assert identity_start_resp.status_code == 403
        error_detail = identity_start_resp.json().get("detail", "")
        assert "CONSENT_REQUIRED" in error_detail

    await engine.dispose()


@pytest.mark.black_box
async def test_journey_02_concurrent_duplicate_cancellation_ch06() -> None:
    """
    CH-06: Concurrent duplicate cancellation requests resolve deterministically to CANCELLED
    without database lock collision or race condition errors.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    test_user_ref = f"usr_j02_ch06_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Fingerprint": device_fp}

    async with httpx.AsyncClient(base_url=api_base_url, timeout=10.0) as client:
        # Create draft application
        create_resp = await client.post(
            "/v1/applications",
            json={"user_ref": test_user_ref, "bank_id": "bank_awash", "tier": "standard"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        app_id_str = create_resp.json()["application_id"]
        app_uuid = uuid.UUID(app_id_str)
        session_token = create_resp.json()["token"]

        auth_headers = {
            "Authorization": f"Bearer {session_token}",
            "X-Device-Fingerprint": device_fp,
        }

        # Issue 5 concurrent cancellation calls
        async def cancel_call() -> httpx.Response:
            return await client.post(
                f"/v1/applications/{app_id_str}/consent",
                json={"accepted": False, "device_fingerprint": device_fp},
                headers=auth_headers,
            )

        responses = await asyncio.gather(*(cancel_call() for _ in range(5)))
        for resp in responses:
            assert resp.status_code == 200
            resp_data = resp.json()
            assert resp_data["status"] == "CANCELLED"
            assert resp_data["application_id"] == app_id_str

        # Verify database settled cleanly to CANCELLED
        async with session_maker() as session:
            stmt = select(Application).where(Application.id == app_uuid)
            app = (await session.execute(stmt)).scalar_one_or_none()
            assert app is not None
            assert app.status == ApplicationStatus.CANCELLED
            assert app.status.value == "CANCELLED"

    await engine.dispose()
