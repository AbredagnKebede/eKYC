import asyncio
import hashlib
import json
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
from sqlalchemy.orm import selectinload

from src.api.middleware import create_access_token
from src.clients.bank_cbs_client import (
    BankCBSCircuitBreakerOpenError,
    BankCBSClient,
    CircuitBreaker,
    CircuitBreakerState,
)
from src.clients.fayda_client import FaydaClient, FaydaTimeoutError
from src.models.application import (
    Application,
    ApplicationStatus,
    BankSubmission,
    IdentitySnapshot,
    VerificationMethod,
)
from src.models.audit import AuditLog
from src.services.audit import AuditService
from src.services.onboarding import OnboardingService

pytestmark = [pytest.mark.asyncio]


@pytest.fixture(scope="module")
def api_base_url() -> str:
    return os.getenv("API_BASE_URL", "http://127.0.0.1:8005")


@pytest.fixture(scope="module")
def cbs_sandbox_url() -> str:
    url = os.getenv("BANK_CBS_SANDBOX_URL", "http://127.0.0.1:8082/cbs/v1")
    return url.split("/cbs")[0] if "/cbs" in url else url


@pytest.fixture(scope="module")
def fayda_sandbox_url() -> str:
    return os.getenv("FAYDA_SANDBOX_URL", "http://127.0.0.1:8081/fayda/v2")


@pytest.fixture(scope="module")
def db_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")


@pytest.fixture(scope="module")
def redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")


async def test_chaos_ch01_client_session_token_expiry(api_base_url: str, db_url: str) -> None:
    """
    Scenario CH-01: Client Session Token Expiry mid-journey.
    Max TTL: 15 minutes.
    When expired: Returns HTTP 401 Unauthorized; client prompts re-authentication without dropping draft state.
    """
    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    app_uuid = uuid.uuid4()
    test_user_ref = f"usr_ch01_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_ch01_{uuid.uuid4().hex[:8]}"

    # Seed application in DRAFT state in real PostgreSQL
    async with session_maker() as session:
        app = Application(
            id=app_uuid,
            user_ref=test_user_ref,
            bank_id="bank_awash",
            tier="standard",
            status=ApplicationStatus.DRAFT,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        session.add(app)
        await session.commit()

    # Generate an expired session token (expired 5 minutes ago)
    expired_token = create_access_token(
        user_ref=test_user_ref,
        device_fingerprint=device_fp,
        expires_delta=timedelta(minutes=-5),
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Call authenticated endpoint with expired JWT token
        resp = await client.post(
            f"{api_base_url}/v1/applications/{app_uuid}/consent",
            json={"consent_version": "v1.0", "accepted": True},
            headers={
                "Authorization": f"Bearer {expired_token}",
                "X-Device-Fingerprint": device_fp,
            },
        )
        # CH-01: Returns HTTP 401 Unauthorized
        assert resp.status_code == 401
        detail = resp.json().get("detail", "").lower()
        assert "expired" in detail or "authenticate" in detail

    # CH-01: Verify draft progress in database is completely preserved without data loss
    async with session_maker() as session:
        persisted_app = (
            await session.execute(select(Application).where(Application.id == app_uuid))
        ).scalar_one()
        assert persisted_app.status == ApplicationStatus.DRAFT
        assert persisted_app.user_ref == test_user_ref


async def test_chaos_ch02_fayda_otp_challenge_expiry(
    api_base_url: str, db_url: str, redis_url: str
) -> None:
    """
    Scenario CH-02: Fayda eKYC OTP Challenge Expiry (180s).
    Max TTL: 180 seconds.
    When expired: Verification endpoint returns HTTP 410 Gone; OTP session is invalidated in cache_redis.
    """
    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    app_uuid = uuid.uuid4()
    test_user_ref = f"usr_ch02_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_ch02_{uuid.uuid4().hex[:8]}"

    # Seed application in CONSENTED state
    async with session_maker() as session:
        app = Application(
            id=app_uuid,
            user_ref=test_user_ref,
            bank_id="bank_awash",
            tier="standard",
            status=ApplicationStatus.CONSENTED,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        session.add(app)
        await session.commit()

    token = create_access_token(
        user_ref=test_user_ref,
        device_fingerprint=device_fp,
        expires_delta=timedelta(minutes=15),
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Call verification endpoint with expired OTP simulation code '999999' supported by sandbox
        resp = await client.post(
            f"{api_base_url}/v1/applications/{app_uuid}/identity/verify",
            json={"transaction_id": "tx_expired_1234", "otp": "999999"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Device-Fingerprint": device_fp,
            },
        )
        # CH-02: Verification endpoint returns HTTP 410 Gone
        assert resp.status_code == 410
        detail = resp.json().get("detail", "").lower()
        assert "expired" in detail

    # CH-02: Verify OTP session key is not present or expired in cache_redis
    session_data = await redis_client.get(f"otp_session:{app_uuid}")
    assert session_data is None


async def test_chaos_ch03_incomplete_application_draft_expiration(db_url: str) -> None:
    """
    Scenario CH-03: Incomplete Application Draft Expiration after 24 hours.
    Background cleanup task marks status as EXPIRED and triggers cryptographic shredding of temporary artifacts.
    """
    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    app_uuid = uuid.uuid4()
    test_user_ref = f"usr_ch03_{uuid.uuid4().hex[:8]}"

    # Seed application inactive past 24-hour expiration threshold
    async with session_maker() as session:
        past_expiration = datetime.now(timezone.utc) - timedelta(hours=25)
        app = Application(
            id=app_uuid,
            user_ref=test_user_ref,
            bank_id="bank_awash",
            tier="standard",
            status=ApplicationStatus.DRAFT,
            expires_at=past_expiration,
        )
        session.add(app)

        # Temporary demographic snapshot containing encrypted PII
        snapshot = IdentitySnapshot(
            application_id=app_uuid,
            encrypted_full_name=b"sensitive_encrypted_citizen_name_bytes",
            encrypted_dob=b"sensitive_encrypted_citizen_dob_bytes",
            gender="FEMALE",
            fayda_ref_hash="hash_draft_ch03_sha256",
            liveness_score=0.95,
            verification_method=VerificationMethod.OTP,
        )
        session.add(snapshot)
        await session.commit()

    # Trigger background cleanup task (§9.1 CH-03)
    audit_service = AuditService()
    onboarding_service = OnboardingService(audit_service=audit_service)

    async with session_maker() as session:
        expired_count = await onboarding_service.expire_inactive_applications(session)
        assert expired_count >= 1

    # Verify state transition to EXPIRED, cryptographic shredding, and audit trail
    async with session_maker() as session:
        persisted_app = (
            await session.execute(
                select(Application)
                .options(selectinload(Application.identity_snapshot))
                .where(Application.id == app_uuid)
            )
        ).scalar_one()
        # CH-03: Status transitioned to EXPIRED
        assert persisted_app.status == ApplicationStatus.EXPIRED

        # CH-03: Cryptographic shredding of temporary artifacts
        assert persisted_app.identity_snapshot.encrypted_full_name == b"SHREDDED"
        assert persisted_app.identity_snapshot.encrypted_dob == b"SHREDDED"

        # CH-03: Audit log records APPLICATION_EXPIRED
        audit_stmt = select(AuditLog).where(
            AuditLog.application_id == app_uuid,
            AuditLog.action == "APPLICATION_EXPIRED",
        )
        audit_entry = (await session.execute(audit_stmt)).scalar_one_or_none()
        assert audit_entry is not None
        assert audit_entry.actor_type == "SYSTEM"


async def test_chaos_ch04_fayda_ekyc_timeout_and_circuit_breaker(fayda_sandbox_url: str) -> None:
    """
    Scenario CH-04: Fayda eKYC External Call Timeout (5000ms).
    Timeout: 5000ms.
    Retry Count: 2 retries with exponential backoff.
    Circuit breaker prevents continuous hung sockets; raises FaydaTimeoutError.
    """
    # Instantiate real FaydaClient with 1 microsecond timeout to simulate guaranteed socket timeout
    client = FaydaClient(
        base_url=fayda_sandbox_url,
        api_key="dev-fayda-key",
        timeout=0.000001,  # 1 microsecond to simulate guaranteed network socket timeout
        max_retries=2,  # 2 retries as per §9.2 policy
    )

    start_time = time.monotonic()
    with pytest.raises(FaydaTimeoutError) as exc_info:
        await client.generate_otp("123456789012")

    elapsed = time.monotonic() - start_time
    # CH-04: Verified retry attempts and backoff elapsed
    assert exc_info.value.status_code == 504
    assert "timed out after 3 attempts" in str(exc_info.value)
    assert elapsed > 0.1  # Verified exponential backoff delay occurred


async def test_chaos_ch05_bank_cbs_timeout_and_circuit_breaker_isolation(
    cbs_sandbox_url: str
) -> None:
    """
    Scenario CH-05: Bank CBS Outbound Adapter Submission Timeout (8000ms).
    Circuit Breaker: Per-bank circuit breaker isolates failing banks while allowing healthy partner banks to continue processing applications.
    """
    # Bank A (Awash Bank): Experiencing severe timeout outages
    failing_cbs_client = BankCBSClient(
        base_url=f"{cbs_sandbox_url}/cbs/v1",
        api_key="dev-bank-key",
        timeout=0.000001,  # Force immediate timeout
        max_retries=1,
        failure_threshold=2,
        recovery_timeout=10.0,
    )

    # Bank B (Commercial Bank of Ethiopia): Healthy partner bank
    healthy_cbs_client = BankCBSClient(
        base_url=f"{cbs_sandbox_url}/cbs/v1",
        api_key="dev-bank-key",
        timeout=5.0,
        max_retries=1,
        failure_threshold=3,
        recovery_timeout=10.0,
    )

    # 1. Trip Bank A circuit breaker via consecutive timeouts
    for _ in range(2):
        try:
            await failing_cbs_client.open_account(
                {"application_id": str(uuid.uuid4()), "bank_id": "bank_awash"}
            )
        except Exception:
            pass

    # CH-05: Bank A circuit breaker is now OPEN
    assert failing_cbs_client.circuit_breaker.state == CircuitBreakerState.OPEN

    # Subsequent requests to Bank A fail fast with BankCBSCircuitBreakerOpenError
    with pytest.raises(BankCBSCircuitBreakerOpenError) as exc_info:
        await failing_cbs_client.open_account(
            {"application_id": str(uuid.uuid4()), "bank_id": "bank_awash"}
        )
    assert "circuit breaker is OPEN" in str(exc_info.value)

    # CH-05: Per-bank isolation verification — Bank B circuit breaker remains CLOSED and operates normally
    assert healthy_cbs_client.circuit_breaker.state == CircuitBreakerState.CLOSED
    cbe_resp = await healthy_cbs_client.open_account(
        {
            "application_id": str(uuid.uuid4()),
            "bank_id": "bank_cbe",
            "account_tier": "standard",
            "dynamic_fields": {},
        }
    )
    assert cbe_resp.get("status") in ("SUCCESS", "PENDING_REVIEW")
    assert healthy_cbs_client.circuit_breaker.state == CircuitBreakerState.CLOSED


async def test_chaos_ch06_duplicate_submission_race_condition(
    api_base_url: str, db_url: str
) -> None:
    """
    Scenario CH-06: Duplicate Submission Race Condition.
    Handled atomically via row-level locks (SELECT ... FOR UPDATE) and 30-day idempotency hash.
    Concurrent attempts receive HTTP 409 Conflict.
    """
    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    app_uuid = uuid.uuid4()
    test_user_ref = f"usr_ch06_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_ch06_{uuid.uuid4().hex[:8]}"

    # Seed application in DATA_COMPLETE state
    async with session_maker() as session:
        app = Application(
            id=app_uuid,
            user_ref=test_user_ref,
            bank_id="bank_awash",
            tier="standard",
            status=ApplicationStatus.DATA_COMPLETE,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        session.add(app)
        snapshot = IdentitySnapshot(
            application_id=app_uuid,
            encrypted_full_name=b"enc_name_ch06",
            encrypted_dob=b"enc_dob_ch06",
            gender="MALE",
            fayda_ref_hash="hash_ch06_sha256",
            liveness_score=0.96,
            verification_method=VerificationMethod.OTP,
        )
        session.add(snapshot)
        sub = BankSubmission(
            application_id=app_uuid,
            bank_id="bank_awash",
            dynamic_fields={
                "monthly_income_etb": 45000.0,
                "occupation": "Software Architect",
                "source_of_funds": "Salary",
            },
        )
        session.add(sub)
        await session.commit()

    token = create_access_token(
        user_ref=test_user_ref,
        device_fingerprint=device_fp,
        expires_delta=timedelta(minutes=15),
    )

    auth_headers = {
        "Authorization": f"Bearer {token}",
        "X-Device-Fingerprint": device_fp,
    }

    # CH-06: Simulate concurrent submission race condition
    async with httpx.AsyncClient(timeout=10.0) as client:
        async def submit_request():
            return await client.post(
                f"{api_base_url}/v1/applications/{app_uuid}/submit",
                json={"signature": "digital_sig_citizen_sha256_token"},
                headers=auth_headers,
            )

        # Launch two simultaneous submit requests concurrently
        results = await asyncio.gather(submit_request(), submit_request())

    status_codes = [r.status_code for r in results]
    # CH-06: Exactly one succeeds with 200, concurrent duplicate rejected with 409 Conflict
    assert 200 in status_codes
    assert 409 in status_codes or status_codes.count(200) == 1

    # Verify exactly 1 submission entry exists in real PostgreSQL database
    async with session_maker() as session:
        submissions = (
            await session.execute(
                select(BankSubmission).where(BankSubmission.application_id == app_uuid)
            )
        ).scalars().all()
        assert len(submissions) == 1


async def test_chaos_ch07_crash_recovery_transactional_outbox(
    api_base_url: str, db_url: str, redis_url: str
) -> None:
    """
    Scenario CH-07: Crash Between Database Transition and Message Enqueue.
    Transactional Outbox pattern commits state mutation and outbox enqueue in PostgreSQL.
    Surviving / restarted worker automatically picks up pending outbox records.
    """
    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    app_uuid = uuid.uuid4()
    test_user_ref = f"usr_ch07_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_ch07_{uuid.uuid4().hex[:8]}"

    # Seed application in DATA_COMPLETE state
    async with session_maker() as session:
        app = Application(
            id=app_uuid,
            user_ref=test_user_ref,
            bank_id="bank_awash",
            tier="standard",
            status=ApplicationStatus.DATA_COMPLETE,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        session.add(app)
        snapshot = IdentitySnapshot(
            application_id=app_uuid,
            encrypted_full_name=b"enc_name_ch07",
            encrypted_dob=b"enc_dob_ch07",
            gender="MALE",
            fayda_ref_hash="hash_ch07_sha256",
            liveness_score=0.98,
            verification_method=VerificationMethod.OTP,
        )
        session.add(snapshot)
        sub = BankSubmission(
            application_id=app_uuid,
            bank_id="bank_awash",
            dynamic_fields={
                "monthly_income_etb": 45000.0,
                "occupation": "Software Architect",
                "source_of_funds": "Salary",
            },
        )
        session.add(sub)
        await session.commit()

    token = create_access_token(
        user_ref=test_user_ref,
        device_fingerprint=device_fp,
        expires_delta=timedelta(minutes=15),
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        submit_resp = await client.post(
            f"{api_base_url}/v1/applications/{app_uuid}/submit",
            json={"signature": "digital_sig_citizen_ch07_token"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Device-Fingerprint": device_fp,
            },
        )
        assert submit_resp.status_code == 200

    # Simulate worker container restart mid-stream
    restart_result = subprocess.run(
        ["docker", "compose", "restart", "worker"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert restart_result.returncode == 0

    # CH-07: Verify surviving/restarted worker claims stream message and updates status
    resumed = False
    for _ in range(30):
        await asyncio.sleep(0.5)
        async with session_maker() as session:
            stmt = select(Application).where(Application.id == app_uuid)
            app_state = (await session.execute(stmt)).scalar_one()
            if app_state.status in (ApplicationStatus.ACCOUNT_OPENED, ApplicationStatus.BANK_ACCEPTED):
                resumed = True
                break

    assert resumed is True, "Restarted worker failed to process transactional outbox record"


async def test_chaos_ch08_bank_cbs_permanent_rejection_dlq_escalation(
    api_base_url: str, db_url: str, redis_url: str, cbs_sandbox_url: str
) -> None:
    """
    Scenario CH-08: Bank CBS Permanent Rejection & Dead-Letter Escalation.
    Non-retryable error (e.g. HTTP 400 or HTTP 403) causes worker to mark status as BANK_REJECTED,
    log audit entry, and route payload to bank_submission_dlq.
    """
    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    app_uuid = uuid.uuid4()
    test_user_ref = f"usr_ch08_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_ch08_{uuid.uuid4().hex[:8]}"

    # Configure CBS sandbox simulation mode for permanent failure
    async with httpx.AsyncClient(timeout=10.0) as client:
        mode_resp = await client.post(
            f"{cbs_sandbox_url}/cbs/v1/sandbox/mode",
            json={"mode": "error", "status_code": 403},
        )
        assert mode_resp.status_code == 200

    # Seed application in DATA_COMPLETE state
    async with session_maker() as session:
        app = Application(
            id=app_uuid,
            user_ref=test_user_ref,
            bank_id="bank_awash",
            tier="standard",
            status=ApplicationStatus.DATA_COMPLETE,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        session.add(app)
        snapshot = IdentitySnapshot(
            application_id=app_uuid,
            encrypted_full_name=b"enc_name_ch08",
            encrypted_dob=b"enc_dob_ch08",
            gender="FEMALE",
            fayda_ref_hash="hash_ch08_sha256",
            liveness_score=0.98,
            verification_method=VerificationMethod.OTP,
        )
        session.add(snapshot)
        sub = BankSubmission(
            application_id=app_uuid,
            bank_id="bank_awash",
            dynamic_fields={
                "monthly_income_etb": 45000.0,
                "occupation": "Software Architect",
                "source_of_funds": "Salary",
            },
        )
        session.add(sub)
        await session.commit()

    token = create_access_token(
        user_ref=test_user_ref,
        device_fingerprint=device_fp,
        expires_delta=timedelta(minutes=15),
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        submit_resp = await client.post(
            f"{api_base_url}/v1/applications/{app_uuid}/submit",
            json={"signature": "digital_sig_citizen_ch08_token"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Device-Fingerprint": device_fp,
            },
        )
        assert submit_resp.status_code == 200

    # Wait for worker to encounter non-retryable 403 and route to DLQ
    dlq_routed = False
    for _ in range(30):
        await asyncio.sleep(0.5)
        # Check Redis DLQ stream
        dlq_entries = await redis_client.xrange("bank_submission_dlq", count=20)
        for entry_id, fields in dlq_entries:
            if fields.get("application_id") == str(app_uuid):
                dlq_routed = True
                assert "Permanent rejection" in fields.get("error_message", "")
                break
        if dlq_routed:
            break

    assert dlq_routed is True, "Failed to route permanent CBS error to bank_submission_dlq"

    # CH-08: Verify database status marked as BANK_REJECTED
    async with session_maker() as session:
        app_stmt = select(Application).where(Application.id == app_uuid)
        rejected_app = (await session.execute(app_stmt)).scalar_one()
        assert rejected_app.status == ApplicationStatus.BANK_REJECTED

        # CH-08: Verify audit trail recorded CBS_PERMANENT_REJECTION
        audit_stmt = select(AuditLog).where(
            AuditLog.application_id == app_uuid,
            AuditLog.action == "CBS_PERMANENT_REJECTION",
        )
        audit_entry = (await session.execute(audit_stmt)).scalar_one_or_none()
        assert audit_entry is not None

    # Reset CBS sandbox back to normal mode
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(f"{cbs_sandbox_url}/cbs/v1/sandbox/reset")
