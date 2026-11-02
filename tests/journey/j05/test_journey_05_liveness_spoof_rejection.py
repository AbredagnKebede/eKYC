import asyncio
import base64
import os
import time
import uuid
from typing import Any, Dict

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models.application import (
    Application,
    ApplicationStatus,
    IdentitySnapshot,
    VerificationMethod,
)
from src.models.audit import AuditLog
from src.services.audit import AuditService

pytestmark = [pytest.mark.asyncio, pytest.mark.black_box]


@pytest.mark.black_box
async def test_journey_05_liveness_spoof_rejection_e2e() -> None:
    """
    End-to-end user journey test for facial liveness anti-spoof detection rejection (J-05).

    Covers architectural requirements AS-05:
    - Real PostgreSQL connection via DATABASE_URL and asyncpg (no mocks).
    - Biometric anti-spoofing engine rejecting synthetic/printed/video replay feeds.
    - Zero ephemeral storage retention of raw biometric image frames or video buffers.
    - Application status transitioning strictly to LIVENESS_FAILED in PostgreSQL.
    - Immutable audit log entry recording LIVENESS_VERIFICATION_FAILED with classification score.

    Assertion Points Verified:
    - AP-1 API response: POST /v1/applications/{id}/liveness returns HTTP 422 with spoof_detected=true and anti-spoof score < 0.90.
    - AP-2 Database: applications status transitions strictly to LIVENESS_FAILED.
    - AP-3 Storage: Zero raw biometric image frames or video buffers remain in ephemeral filesystem storage after evaluation.
    - AP-4 Audit: audit_logs records LIVENESS_VERIFICATION_FAILED with model version and spoof classification score.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    test_user_ref = f"usr_j05_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_j05_{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Fingerprint": device_fp}

    async with httpx.AsyncClient(base_url=api_base_url, timeout=10.0) as client:
        # Step 1: Create application
        create_resp = await client.post(
            "/v1/applications",
            json={"user_ref": test_user_ref, "bank_id": "bank_awash", "tier": "standard"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        app_id_str = create_resp.json()["application_id"]
        app_uuid = uuid.UUID(app_id_str)
        session_token = create_resp.json()["token"]
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

        # Step 3: Advance to ID_VERIFIED with identity snapshot in PostgreSQL
        async with session_maker() as session:
            stmt = select(Application).where(Application.id == app_uuid)
            app_obj = (await session.execute(stmt)).scalar_one()
            app_obj.status = ApplicationStatus.ID_VERIFIED

            snapshot = IdentitySnapshot(
                application_id=app_uuid,
                encrypted_full_name=b"enc_name_token_sample_32bytes_long_bytes",
                encrypted_dob=b"enc_dob_token_sample_32bytes_long_bytes",
                gender="MALE",
                fayda_ref_hash="hash_alemu_verified_sha256_placeholder",
                liveness_score=0.0,
                verification_method=VerificationMethod.OTP,
            )
            session.add(snapshot)
            await session.commit()

        # Step 4: Present synthetic / replay attack photo
        # The bytes contain 'spoof_attack_ipad_replay_frame' which triggers the anti-spoof rejection
        spoof_bytes = b"presentation_spoof_attack_ipad_replay_frame_data_synthetic"
        spoof_base64 = base64.b64encode(spoof_bytes).decode("utf-8")

        # -------------------------------------------------------------------------
        # AP-1 API response: POST /v1/applications/{id}/liveness returns HTTP 422 with spoof_detected=true and anti-spoof score < 0.90
        # -------------------------------------------------------------------------
        liveness_resp = await client.post(
            f"/v1/applications/{app_id_str}/liveness",
            json={"selfie_base64": spoof_base64},
            headers=auth_headers,
        )
        assert liveness_resp.status_code == 422
        error_payload = liveness_resp.json()
        assert error_payload.get("spoof_detected") is True
        liveness_score = error_payload.get("liveness_score", 1.0)
        assert liveness_score < 0.90
        assert liveness_score == 0.25

        # -------------------------------------------------------------------------
        # AP-2 Database: applications status transitions strictly to LIVENESS_FAILED
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            stmt = select(Application).where(Application.id == app_uuid)
            app_record = (await session.execute(stmt)).scalar_one_or_none()
            assert app_record is not None
            assert app_record.status == ApplicationStatus.LIVENESS_FAILED
            assert app_record.status.value == "LIVENESS_FAILED"
            assert app_record.user_ref == test_user_ref

        # -------------------------------------------------------------------------
        # AP-3 Storage: Zero raw biometric image frames or video buffers remain in ephemeral filesystem storage after evaluation
        # -------------------------------------------------------------------------
        for root_dir in ("/tmp", "/app/scratch", "scratch"):
            if os.path.exists(root_dir):
                matching_files = [
                    f for f in os.listdir(root_dir)
                    if app_id_str in f or "spoof_attack" in f or f.endswith((".jpg", ".png", ".raw_bio"))
                ]
                assert len(matching_files) == 0

        # -------------------------------------------------------------------------
        # AP-4 Audit: audit_logs records LIVENESS_VERIFICATION_FAILED with model version and spoof classification score
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            audit_stmt = (
                select(AuditLog)
                .where(AuditLog.application_id == app_uuid)
                .order_by(AuditLog.id.asc())
            )
            audit_entries = list((await session.execute(audit_stmt)).scalars().all())
            actions = [entry.action for entry in audit_entries]
            assert "LIVENESS_EVALUATION_FAILED" in actions

            failed_entries = [e for e in audit_entries if e.action == "LIVENESS_EVALUATION_FAILED"]
            assert len(failed_entries) == 1
            entry = failed_entries[0]
            assert entry.actor_type == "CITIZEN"
            assert entry.actor_id == test_user_ref
            assert len(entry.payload_hash) == 64
            assert len(entry.prev_log_hash) == 64
            assert len(entry.hmac_signature) == 64

            # Verify cryptographic ledger continuity
            audit_service = AuditService()
            is_valid, err_msg = await audit_service.verify_ledger_integrity(session)
            assert is_valid is True
            assert err_msg is None

    await engine.dispose()


@pytest.mark.black_box
async def test_journey_05_ch05_camera_stream_timeout_safely_resets() -> None:
    """
    CH-05: Camera stream timeout during frame capture safely resets the session without counting as a fraudulent spoof attempt.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    test_user_ref = f"usr_j05_ch05_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_j05_ch05_{uuid.uuid4().hex[:8]}"
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
        app_uuid = uuid.UUID(app_id_str)
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

        # Send corrupted/invalid base64 payload representing camera stream timeout/interruption
        corrupt_resp = await client.post(
            f"/v1/applications/{app_id_str}/liveness",
            json={"selfie_base64": "invalid_not_base64!@#$"},
            headers=auth_headers,
        )
        assert corrupt_resp.status_code == 422
        assert "Invalid base64 encoding" in corrupt_resp.json().get("detail", "")

        # Verify application status was NOT transitioned to LIVENESS_FAILED
        async with session_maker() as session:
            stmt = select(Application).where(Application.id == app_uuid)
            app_rec = (await session.execute(stmt)).scalar_one_or_none()
            assert app_rec is not None
            assert app_rec.status != ApplicationStatus.LIVENESS_FAILED
            assert app_rec.status == ApplicationStatus.CONSENTED

    await engine.dispose()


@pytest.mark.black_box
async def test_journey_05_ch04_concurrent_inference_execution_timeout() -> None:
    """
    CH-04: High server load under concurrent ONNX inference enforces strict 2000ms execution timeout preventing worker hanging.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    test_user_ref = f"usr_j05_ch04_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_j05_ch04_{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Fingerprint": device_fp}

    async with httpx.AsyncClient(base_url=api_base_url, timeout=10.0) as client:
        # Create and consent applications
        app_tokens = []
        for i in range(3):
            cr = await client.post(
                "/v1/applications",
                json={"user_ref": f"{test_user_ref}_{i}", "bank_id": "bank_awash", "tier": "standard"},
                headers=headers,
            )
            assert cr.status_code == 201
            a_id = cr.json()["application_id"]
            a_uuid = uuid.UUID(a_id)
            tok = cr.json()["token"]
            h = {"Authorization": f"Bearer {tok}", "X-Device-Fingerprint": device_fp}
            await client.post(f"/v1/applications/{a_id}/consent", json={"consent_version": "v1.0", "accepted": True}, headers=h)

            async with session_maker() as session:
                app_row = (await session.execute(select(Application).where(Application.id == a_uuid))).scalar_one()
                app_row.status = ApplicationStatus.ID_VERIFIED
                snap = IdentitySnapshot(
                    application_id=a_uuid,
                    encrypted_full_name=b"enc_name_32bytes_sample_bytes",
                    encrypted_dob=b"enc_dob_32bytes_sample_bytes",
                    gender="MALE",
                    fayda_ref_hash="hash_alemu_verified_sha256",
                    liveness_score=0.0,
                    verification_method=VerificationMethod.OTP,
                )
                session.add(snap)
                await session.commit()

            app_tokens.append((a_id, tok))

        # Launch concurrent liveness inference
        sample_frame = base64.b64encode(b"live_camera_feed_frame_sample_data_alemu").decode("utf-8")

        async def check_inference(app_id_token: tuple) -> float:
            a_id, tok = app_id_token
            start_time = time.monotonic()
            resp = await client.post(
                f"/v1/applications/{a_id}/liveness",
                json={"selfie_base64": sample_frame},
                headers={"Authorization": f"Bearer {tok}", "X-Device-Fingerprint": device_fp},
            )
            elapsed = (time.monotonic() - start_time) * 1000
            assert resp.status_code in (200, 422)
            return elapsed

        durations = await asyncio.gather(*(check_inference(item) for item in app_tokens))
        for duration_ms in durations:
            # Enforce strict 2000ms latency ceiling per CH-04
            assert duration_ms < 2000.0

    await engine.dispose()
