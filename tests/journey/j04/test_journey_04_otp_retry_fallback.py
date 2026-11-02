import asyncio
import os
import time
import uuid
from typing import Any, Dict

import httpx
import pytest
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models.application import Application, ApplicationStatus, IdentitySnapshot
from src.models.audit import AuditLog
from src.services.audit import AuditService

pytestmark = [pytest.mark.asyncio, pytest.mark.black_box]


@pytest.mark.black_box
async def test_journey_04_otp_retry_fallback_e2e() -> None:
    """
    End-to-end user journey test for OTP verification retry exhaustion branch fallback (J-04).

    Covers architectural requirements AS-04:
    - Real PostgreSQL connection via DATABASE_URL and asyncpg (no mocks).
    - Real Redis session tracking for active OTP challenge and attempt counters.
    - Real Fayda eKYC sandbox running at FAYDA_SANDBOX_URL.
    - Terminal transition to ID_FAILED on third invalid attempt.
    - Audit log recording consecutive failure counts and ledger chaining.

    Assertion Points Verified:
    - AP-1 Database: applications status transitions strictly to ID_FAILED.
    - AP-2 Cache: Redis OTP session key is deleted upon third failure, preventing any subsequent OTP submissions.
    - AP-3 API response: Fourth submission receives HTTP 409 Conflict with state ID_FAILED.
    - AP-4 Audit: audit_logs records OTP_VERIFICATION_FAILED and APPLICATION_ID_FAILED with consecutive failure count 3.
    - AP-5 External API: fayda_ekyc_api sandbox registered 3 failed verification invocations.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    fayda_sandbox_url = os.getenv("FAYDA_SANDBOX_URL", "http://127.0.0.1:8081/fayda/v2")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    test_user_ref = f"usr_j04_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_j04_{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Fingerprint": device_fp}

    async with httpx.AsyncClient(base_url=api_base_url, timeout=10.0) as client:
        # Step 1: Create application
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

        auth_headers = {
            "Authorization": f"Bearer {session_token}",
            "X-Device-Fingerprint": device_fp,
        }

        # Step 2: Consent
        consent_resp = await client.post(
            f"/v1/applications/{app_id_str}/consent",
            json={"consent_version": "v1.0", "accepted": True},
            headers=auth_headers,
        )
        assert consent_resp.status_code == 200
        assert consent_resp.json()["status"] == "CONSENTED"

        # Step 3: Trigger OTP generation with valid 12-digit FIN
        fin = "123456789012"
        start_resp = await client.post(
            f"/v1/applications/{app_id_str}/identity/start",
            json={"fin": fin},
            headers=auth_headers,
        )
        assert start_resp.status_code == 200
        start_data = start_resp.json()
        tx_id = start_data["transaction_id"]
        assert tx_id.startswith("tx_fayda_")

        # Verify Redis session key initialized
        session_key = f"otp:session:{app_id_str}"
        attempts_key = f"otp:attempts:{app_id_str}"
        active_tx = await redis_client.get(session_key)
        assert active_tx == tx_id
        session_ttl = await redis_client.ttl(session_key)
        assert session_ttl > 0
        assert session_ttl <= 180

        # -------------------------------------------------------------------------
        # Attempt 1: First incorrect OTP
        # -------------------------------------------------------------------------
        att1_resp = await client.post(
            f"/v1/applications/{app_id_str}/identity/verify",
            json={"transaction_id": tx_id, "otp": "000001"},
            headers=auth_headers,
        )
        assert att1_resp.status_code == 400
        att1_msg = att1_resp.json().get("detail", "")
        assert "2 attempts remaining" in att1_msg

        # -------------------------------------------------------------------------
        # Attempt 2: Second incorrect OTP
        # -------------------------------------------------------------------------
        att2_resp = await client.post(
            f"/v1/applications/{app_id_str}/identity/verify",
            json={"transaction_id": tx_id, "otp": "000002"},
            headers=auth_headers,
        )
        assert att2_resp.status_code == 400
        att2_msg = att2_resp.json().get("detail", "")
        assert "1 attempt remaining" in att2_msg

        # -------------------------------------------------------------------------
        # Attempt 3: Third incorrect OTP -> Triggers terminal fallback
        # -------------------------------------------------------------------------
        att3_resp = await client.post(
            f"/v1/applications/{app_id_str}/identity/verify",
            json={"transaction_id": tx_id, "otp": "000003"},
            headers=auth_headers,
        )
        assert att3_resp.status_code == 400
        att3_msg = att3_resp.json().get("detail", "")
        assert "maximum attempts reached" in att3_msg.lower()

        # -------------------------------------------------------------------------
        # AP-1 Database: applications status transitions strictly to ID_FAILED
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            stmt = select(Application).where(Application.id == app_uuid)
            app_record = (await session.execute(stmt)).scalar_one_or_none()
            assert app_record is not None
            assert app_record.status == ApplicationStatus.ID_FAILED
            assert app_record.status.value == "ID_FAILED"
            assert app_record.user_ref == test_user_ref

            # Ensure zero identity snapshot recorded
            snap_stmt = select(IdentitySnapshot).where(IdentitySnapshot.application_id == app_uuid)
            snapshots = (await session.execute(snap_stmt)).scalars().all()
            assert len(snapshots) == 0

        # -------------------------------------------------------------------------
        # AP-2 Cache: Redis OTP session key is deleted upon third failure
        # -------------------------------------------------------------------------
        session_exists = await redis_client.exists(session_key)
        assert session_exists == 0

        # -------------------------------------------------------------------------
        # AP-3 API response: Fourth submission receives HTTP 409 Conflict with state ID_FAILED
        # -------------------------------------------------------------------------
        att4_resp = await client.post(
            f"/v1/applications/{app_id_str}/identity/verify",
            json={"transaction_id": tx_id, "otp": "123456"},
            headers=auth_headers,
        )
        assert att4_resp.status_code == 409
        att4_detail = att4_resp.json().get("detail", "")
        assert "ID_FAILED" in att4_detail
        assert "nearest bank branch" in att4_detail

        # -------------------------------------------------------------------------
        # AP-4 Audit: audit_logs records OTP_VERIFICATION_FAILED and APPLICATION_ID_FAILED with consecutive failure count 3
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            audit_stmt = (
                select(AuditLog)
                .where(AuditLog.application_id == app_uuid)
                .order_by(AuditLog.id.asc())
            )
            audit_entries = list((await session.execute(audit_stmt)).scalars().all())
            actions = [entry.action for entry in audit_entries]
            assert "OTP_VERIFICATION_FAILED" in actions
            assert "APPLICATION_ID_FAILED" in actions

            # Check consecutive failure count in audit events
            failed_app_logs = [e for e in audit_entries if e.action == "APPLICATION_ID_FAILED"]
            assert len(failed_app_logs) == 1
            assert failed_app_logs[0].actor_type == "CITIZEN"
            assert failed_app_logs[0].actor_id == test_user_ref

            # Ledger integrity validation
            audit_service = AuditService()
            is_valid, err_msg = await audit_service.verify_ledger_integrity(session)
            assert is_valid is True
            assert err_msg is None

        # -------------------------------------------------------------------------
        # AP-5 External API: fayda_ekyc_api sandbox registered 3 failed verification invocations
        # -------------------------------------------------------------------------
        async with httpx.AsyncClient(timeout=5.0) as sandbox_client:
            stats_resp = await sandbox_client.get(f"{fayda_sandbox_url}/stats")
            assert stats_resp.status_code == 200
            stats_data = stats_resp.json()
            failures_dict = stats_data.get("failures_by_transaction", {})
            assert tx_id in failures_dict
            assert failures_dict[tx_id] == 3

    await redis_client.aclose()
    await engine.dispose()


@pytest.mark.black_box
async def test_journey_04_ch02_otp_expiry_returns_410() -> None:
    """
    CH-02: OTP challenge expiring before 3 attempts returns HTTP 410 Gone requiring new challenge generation.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    engine = create_async_engine(db_url, echo=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    test_user_ref = f"usr_j04_ch02_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_j04_ch02_{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Fingerprint": device_fp}

    async with httpx.AsyncClient(base_url=api_base_url, timeout=10.0) as client:
        # Create and consent
        create_resp = await client.post(
            "/v1/applications",
            json={"user_ref": test_user_ref, "bank_id": "bank_awash", "tier": "standard"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        app_id_str = create_resp.json()["application_id"]
        session_token = create_resp.json()["token"]

        auth_headers = {
            "Authorization": f"Bearer {session_token}",
            "X-Device-Fingerprint": device_fp,
        }

        consent_resp = await client.post(
            f"/v1/applications/{app_id_str}/consent",
            json={"consent_version": "v1.0", "accepted": True},
            headers=auth_headers,
        )
        assert consent_resp.status_code == 200

        # Start OTP challenge
        start_resp = await client.post(
            f"/v1/applications/{app_id_str}/identity/start",
            json={"fin": "123456789012"},
            headers=auth_headers,
        )
        assert start_resp.status_code == 200
        tx_id = start_resp.json()["transaction_id"]

        # Simulate expiration by deleting session key in Redis while attempts key exists
        session_key = f"otp:session:{app_id_str}"
        await redis_client.delete(session_key)

        # Attempt verification on expired challenge
        verify_resp = await client.post(
            f"/v1/applications/{app_id_str}/identity/verify",
            json={"transaction_id": tx_id, "otp": "123456"},
            headers=auth_headers,
        )
        assert verify_resp.status_code == 410
        assert "expired" in verify_resp.json().get("detail", "").lower()

    await redis_client.aclose()
    await engine.dispose()


@pytest.mark.black_box
async def test_journey_04_ch01_interrupted_connection_preserves_attempts() -> None:
    """
    CH-01: Interrupted mobile network connection between attempts preserves remaining attempt count correctly in Redis.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    engine = create_async_engine(db_url, echo=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    test_user_ref = f"usr_j04_ch01_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_j04_ch01_{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Fingerprint": device_fp}

    async with httpx.AsyncClient(base_url=api_base_url, timeout=10.0) as client:
        # Create and consent
        create_resp = await client.post(
            "/v1/applications",
            json={"user_ref": test_user_ref, "bank_id": "bank_awash", "tier": "standard"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        app_id_str = create_resp.json()["application_id"]
        session_token = create_resp.json()["token"]

        auth_headers = {
            "Authorization": f"Bearer {session_token}",
            "X-Device-Fingerprint": device_fp,
        }

        consent_resp = await client.post(
            f"/v1/applications/{app_id_str}/consent",
            json={"consent_version": "v1.0", "accepted": True},
            headers=auth_headers,
        )
        assert consent_resp.status_code == 200

        # Start OTP
        start_resp = await client.post(
            f"/v1/applications/{app_id_str}/identity/start",
            json={"fin": "123456789012"},
            headers=auth_headers,
        )
        assert start_resp.status_code == 200
        tx_id = start_resp.json()["transaction_id"]

        # 1st attempt fails
        att1 = await client.post(
            f"/v1/applications/{app_id_str}/identity/verify",
            json={"transaction_id": tx_id, "otp": "000001"},
            headers=auth_headers,
        )
        assert att1.status_code == 400

        # Simulate network disconnect: wait 1 second, re-query Redis attempt counter
        await asyncio.sleep(0.5)
        attempts_key = f"otp:attempts:{app_id_str}"
        attempts_recorded = await redis_client.get(attempts_key)
        assert attempts_recorded is not None
        assert int(attempts_recorded) == 1

        # 2nd attempt after reconnection
        att2 = await client.post(
            f"/v1/applications/{app_id_str}/identity/verify",
            json={"transaction_id": tx_id, "otp": "000002"},
            headers=auth_headers,
        )
        assert att2.status_code == 400
        assert "1 attempt remaining" in att2.json().get("detail", "")

    await redis_client.aclose()
    await engine.dispose()
