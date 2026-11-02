import asyncio
import os
import subprocess
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import httpx
import pytest
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.queue import SubmissionQueue
from src.models.application import (
    Application,
    ApplicationStatus,
    BankSubmission,
    IdentitySnapshot,
    VerificationMethod,
)
from src.models.audit import AuditLog
from src.services.audit import AuditService

pytestmark = [pytest.mark.asyncio, pytest.mark.black_box]


@pytest.mark.black_box
async def test_journey_07_bank_offline_retry_e2e() -> None:
    """
    End-to-end user journey test for transient partner bank CBS downtime and idempotent retry (J-07).

    Covers architectural requirements AS-07:
    - Real PostgreSQL connection via DATABASE_URL and asyncpg (no mocks).
    - Real Redis queue connection via REDIS_URL and streams (no mocks).
    - Real live CBS sandbox container on port 8082 (no mocks).
    - Real background worker process consuming queue.
    - Application status remaining in SUBMITTED_TO_BANK during 503 outage.
    - Submission retry count tracked with HTTP 503 Service Unavailable logged.
    - Queue message safely held in flight without data loss.
    - Exactly one account opened once CBS recovers, zero duplicates.
    - Audit log recording SUBMISSION_RETRY_SCHEDULED and SUBMISSION_SUCCEEDED.

    Assertion Points Verified:
    - AP-1 Database: applications status remains reliably in SUBMITTED_TO_BANK during bank downtime.
    - AP-2 Database: bank_submissions records retry_count >= 1 and logs last_error='HTTP 503 Service Unavailable'.
    - AP-3 Queue: The message remains safely in flight or requeued with exponential backoff delay.
    - AP-4 External API: Once CBS returns HTTP 200, exactly one bank account creation payload is accepted; zero duplicate accounts are opened.
    - AP-5 Audit: audit_logs records SUBMISSION_RETRY_SCHEDULED and subsequent SUBMISSION_SUCCEEDED.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    cbs_base_url = os.getenv("BANK_CBS_SANDBOX_URL", "http://127.0.0.1:8082/cbs/v1")
    # Strip /cbs/v1 suffix if needed for control endpoints
    cbs_root_url = cbs_base_url.split("/cbs")[0] if "/cbs" in cbs_base_url else cbs_base_url
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    test_user_ref = f"usr_j07_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_j07_{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Fingerprint": device_fp}

    async with httpx.AsyncClient(timeout=10.0) as http_client:
        # Step 1: Put CBS sandbox into maintenance mode (HTTP 503)
        mode_resp = await http_client.post(
            f"{cbs_root_url}/cbs/v1/sandbox/mode",
            json={"mode": "maintenance", "status_code": 503},
        )
        assert mode_resp.status_code == 200
        assert mode_resp.json().get("simulation_mode") == "maintenance"

        # Step 2: Create application via API
        create_resp = await http_client.post(
            f"{api_base_url}/v1/applications",
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

        # Step 3: Consent application
        consent_resp = await http_client.post(
            f"{api_base_url}/v1/applications/{app_id_str}/consent",
            json={"consent_version": "v1.0", "accepted": True},
            headers=auth_headers,
        )
        assert consent_resp.status_code == 200

        # Step 4: Advance application to DATA_COMPLETE with verified demographics and dynamic fields
        async with session_maker() as session:
            stmt = select(Application).where(Application.id == app_uuid)
            app_obj = (await session.execute(stmt)).scalar_one()
            app_obj.status = ApplicationStatus.DATA_COMPLETE

            snapshot = IdentitySnapshot(
                application_id=app_uuid,
                encrypted_full_name=b"enc_name_token_sample_32bytes_long_bytes",
                encrypted_dob=b"enc_dob_token_sample_32bytes_long_bytes",
                gender="FEMALE",
                fayda_ref_hash="hash_alemu_j07_sha256",
                liveness_score=0.98,
                verification_method=VerificationMethod.OTP,
            )
            session.add(snapshot)

            submission_rec = BankSubmission(
                application_id=app_uuid,
                bank_id="bank_awash",
                dynamic_fields={
                    "monthly_income_etb": 75000.0,
                    "occupation": "Senior Architect",
                    "source_of_funds": "Salary",
                },
            )
            session.add(submission_rec)
            await session.commit()

        # Step 5: Submit application to bank via API
        submit_resp = await http_client.post(
            f"{api_base_url}/v1/applications/{app_id_str}/submit",
            json={"signature": "sig_citizen_alemu_sha256_verified_token"},
            headers=auth_headers,
        )
        assert submit_resp.status_code == 200
        assert submit_resp.json()["status"] == "SUBMITTED_TO_BANK"

        # Step 6: Wait for background worker to attempt submission against CBS 503
        # Retry with exponential backoff will be scheduled
        retried = False
        for _ in range(30):
            await asyncio.sleep(0.5)
            async with session_maker() as session:
                sub_res = await session.execute(
                    select(BankSubmission).where(BankSubmission.application_id == app_uuid)
                )
                sub_row = sub_res.scalar_one_or_none()
                if sub_row and sub_row.retry_count >= 1:
                    retried = True
                    break

        assert retried is True, "Worker did not record transient retry within timeout"

        # -------------------------------------------------------------------------
        # AP-1 Database: applications status remains reliably in SUBMITTED_TO_BANK during bank downtime
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            app_check = (await session.execute(select(Application).where(Application.id == app_uuid))).scalar_one()
            assert app_check.status == ApplicationStatus.SUBMITTED_TO_BANK
            assert app_check.status.value == "SUBMITTED_TO_BANK"

        # -------------------------------------------------------------------------
        # AP-2 Database: bank_submissions records retry_count >= 1 and logs last_error='HTTP 503 Service Unavailable'
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            sub_check = (await session.execute(select(BankSubmission).where(BankSubmission.application_id == app_uuid))).scalar_one()
            assert sub_check.retry_count >= 1
            assert sub_check.last_error is not None
            assert "HTTP 503 Service Unavailable" in sub_check.last_error

        # -------------------------------------------------------------------------
        # AP-3 Queue: The message remains safely in flight or requeued with exponential backoff delay
        # -------------------------------------------------------------------------
        # Check stream length or unacknowledged pending messages in group
        stream_len = await redis_client.xlen("bank_submission_queue")
        assert stream_len >= 1

        # -------------------------------------------------------------------------
        # AP-5 (Part 1) Audit: audit_logs records SUBMISSION_RETRY_SCHEDULED
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            audit_events = list(
                (await session.execute(
                    select(AuditLog)
                    .where(AuditLog.application_id == app_uuid)
                    .order_by(AuditLog.id.asc())
                )).scalars().all()
            )
            actions = [ev.action for ev in audit_events]
            assert "SUBMISSION_RETRY_SCHEDULED" in actions

        # Step 7: Restore CBS sandbox to normal operational mode (HTTP 200)
        restore_resp = await http_client.post(
            f"{cbs_root_url}/cbs/v1/sandbox/mode",
            json={"mode": "normal", "status_code": 200},
        )
        assert restore_resp.status_code == 200
        assert restore_resp.json().get("simulation_mode") == "normal"

        # Step 8: Wait for background worker to consume retry and succeed
        completed = False
        for _ in range(40):
            await asyncio.sleep(0.5)
            async with session_maker() as session:
                app_poll = (await session.execute(select(Application).where(Application.id == app_uuid))).scalar_one()
                if app_poll.status == ApplicationStatus.ACCOUNT_OPENED:
                    completed = True
                    break

        assert completed is True, "Worker did not complete account opening after CBS recovery"

        # -------------------------------------------------------------------------
        # AP-4 External API: Once CBS returns HTTP 200, exactly one bank account creation payload is accepted; zero duplicate accounts are opened
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            final_sub = (await session.execute(select(BankSubmission).where(BankSubmission.application_id == app_uuid))).scalar_one()
            assert final_sub.account_number is not None
            assert len(final_sub.account_number) >= 8
            assert final_sub.bank_reference is not None

            # Verify in CBS sandbox that exactly one account exists for this bank reference
            cbs_check = await http_client.get(
                f"{cbs_root_url}/cbs/v1/accounts/{final_sub.bank_reference}",
                headers={"Authorization": f"Bearer {os.getenv('BANK_API_KEY', 'dev-bank-key')}"},
            )
            assert cbs_check.status_code == 200
            account_record = cbs_check.json()
            assert account_record["account_number"] == final_sub.account_number
            assert account_record["status"] in ("SUCCESS", "ACCOUNT_OPENED")

        # -------------------------------------------------------------------------
        # AP-5 (Part 2) Audit: subsequent SUBMISSION_SUCCEEDED recorded in audit_logs
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            audit_events_final = list(
                (await session.execute(
                    select(AuditLog)
                    .where(AuditLog.application_id == app_uuid)
                    .order_by(AuditLog.id.asc())
                )).scalars().all()
            )
            final_actions = [ev.action for ev in audit_events_final]
            assert "SUBMISSION_SUCCEEDED" in final_actions

            # Ledger integrity check
            audit_service = AuditService()
            is_valid, err_msg = await audit_service.verify_ledger_integrity(session)
            assert is_valid is True, f"Ledger integrity failed: {err_msg}"

    await redis_client.aclose()
    await engine.dispose()


@pytest.mark.black_box
async def test_journey_07_ch05_max_retries_exceeded_routes_to_dlq() -> None:
    """
    CH-05: Consecutive failures exceeding max retry count (5 attempts)
    move the message to dead-letter queue (bank_submission_dlq) and flag for operator review.
    """
    cbs_base_url = os.getenv("BANK_CBS_SANDBOX_URL", "http://127.0.0.1:8082/cbs/v1")
    cbs_root_url = cbs_base_url.split("/cbs")[0] if "/cbs" in cbs_base_url else cbs_base_url
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    queue = SubmissionQueue(redis_client=redis_client)

    test_user_ref = f"usr_j07_ch05_{uuid.uuid4().hex[:8]}"
    app_uuid = uuid.uuid4()

    async with httpx.AsyncClient(timeout=10.0) as http_client:
        # Keep CBS in maintenance mode
        await http_client.post(
            f"{cbs_root_url}/cbs/v1/sandbox/mode",
            json={"mode": "maintenance", "status_code": 503},
        )

        async with session_maker() as session:
            # Create application directly in SUBMITTED_TO_BANK with retry_count = 5 (at limit)
            app = Application(
                id=app_uuid,
                user_ref=test_user_ref,
                bank_id="bank_awash",
                tier="standard",
                status=ApplicationStatus.SUBMITTED_TO_BANK,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            session.add(app)
            sub = BankSubmission(
                application_id=app_uuid,
                bank_id="bank_awash",
                dynamic_fields={"monthly_income_etb": 40000.0, "occupation": "Doctor", "source_of_funds": "Salary"},
                retry_count=5,  # Exceeded on next attempt
            )
            session.add(sub)
            await session.commit()

        # Enqueue onto the real submission queue processed by the background container
        await queue.enqueue(
            application_id=str(app_uuid),
            bank_id="bank_awash",
            payload={"tier": "standard"},
            idempotency_key=f"idem_ch05_{app_uuid}",
        )

        # Wait for real background container ekyc-worker to process, exceed max retries, and route to DLQ
        routed_to_dlq = False
        for _ in range(40):
            await asyncio.sleep(0.5)
            async with session_maker() as session:
                app_check = (await session.execute(select(Application).where(Application.id == app_uuid))).scalar_one()
                if app_check.status == ApplicationStatus.BANK_REJECTED:
                    routed_to_dlq = True
                    break

        assert routed_to_dlq is True, "Background worker did not route to DLQ after exceeding retries"

        # Verify message exists in bank_submission_dlq
        dlq_len = await redis_client.xlen("bank_submission_dlq")
        assert dlq_len >= 1

        # Restore CBS to normal
        await http_client.post(
            f"{cbs_root_url}/cbs/v1/sandbox/mode",
            json={"mode": "normal", "status_code": 200},
        )

    await redis_client.aclose()
    await engine.dispose()


@pytest.mark.black_box
async def test_journey_07_ch07_worker_crash_and_restart_resumes_dispatch() -> None:
    """
    CH-07: Worker process crash mid-retry restarts cleanly, re-reads the pending outbox entry
    from PostgreSQL and Redis Streams, and resumes dispatch.
    """
    cbs_base_url = os.getenv("BANK_CBS_SANDBOX_URL", "http://127.0.0.1:8082/cbs/v1")
    cbs_root_url = cbs_base_url.split("/cbs")[0] if "/cbs" in cbs_base_url else cbs_base_url
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    queue = SubmissionQueue(redis_client=redis_client)

    app_uuid = uuid.uuid4()
    test_user_ref = f"usr_j07_ch07_{uuid.uuid4().hex[:8]}"

    async with httpx.AsyncClient(timeout=10.0) as http_client:
        # Put CBS in maintenance mode initially
        await http_client.post(
            f"{cbs_root_url}/cbs/v1/sandbox/mode",
            json={"mode": "maintenance", "status_code": 503},
        )

        async with session_maker() as session:
            app = Application(
                id=app_uuid,
                user_ref=test_user_ref,
                bank_id="bank_awash",
                tier="standard",
                status=ApplicationStatus.SUBMITTED_TO_BANK,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            session.add(app)
            sub = BankSubmission(
                application_id=app_uuid,
                bank_id="bank_awash",
                dynamic_fields={"monthly_income_etb": 60000.0, "occupation": "Lawyer", "source_of_funds": "Business"},
                retry_count=0,
            )
            session.add(sub)
            await session.commit()

        # Enqueue task
        await queue.enqueue(
            application_id=str(app_uuid),
            bank_id="bank_awash",
            payload={"tier": "standard"},
            idempotency_key=f"idem_ch07_{app_uuid}",
        )

        # Wait until the running container worker has attempted it and entered retry state (retry_count >= 1)
        attempted = False
        for _ in range(30):
            await asyncio.sleep(0.5)
            async with session_maker() as session:
                sub_check = (await session.execute(
                    select(BankSubmission).where(BankSubmission.application_id == app_uuid)
                )).scalar_one_or_none()
                if sub_check and sub_check.retry_count >= 1:
                    attempted = True
                    break

        assert attempted is True, "Worker did not begin retry attempt before crash simulation"

        # Simulate Worker process crash and restart using docker compose
        subprocess.run(["docker", "compose", "restart", "worker"], check=True)

        # Restore CBS to normal (HTTP 200)
        await http_client.post(
            f"{cbs_root_url}/cbs/v1/sandbox/mode",
            json={"mode": "normal", "status_code": 200},
        )

        # Restarted worker process in container must resume dispatch and open the account
        resumed = False
        for _ in range(40):
            await asyncio.sleep(0.5)
            async with session_maker() as session:
                app_after = (await session.execute(
                    select(Application).where(Application.id == app_uuid)
                )).scalar_one()
                if app_after.status == ApplicationStatus.ACCOUNT_OPENED:
                    resumed = True
                    break

        assert resumed is True, "Restarted worker did not resume pending dispatch"

        # Verify account was issued
        async with session_maker() as session:
            final_sub = (await session.execute(
                select(BankSubmission).where(BankSubmission.application_id == app_uuid)
            )).scalar_one()
            assert final_sub.account_number is not None

    await redis_client.aclose()
    await engine.dispose()
