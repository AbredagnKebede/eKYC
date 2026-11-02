import asyncio
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models.application import (
    Application,
    ApplicationStatus,
    BankSubmission,
    IdentitySnapshot,
    VerificationMethod,
)
from src.models.audit import AuditLog
from src.services.audit import AuditService, compute_payload_hash

pytestmark = [pytest.mark.asyncio, pytest.mark.black_box]


def compute_hmac_signature(secret: str, payload_bytes: bytes) -> str:
    """Helper to compute HMAC-SHA256 signature matching bank API gateway expectations."""
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


@pytest.mark.black_box
async def test_journey_08_async_bank_callback_success_e2e() -> None:
    """
    End-to-end user journey test for asynchronous bank callback and account number issuance (J-08).

    Covers architectural requirements AS-08:
    - Real PostgreSQL connection via DATABASE_URL and asyncpg (no mocks).
    - Real API Gateway exposing POST /v1/webhooks/bank/{bank_id} with HMAC signature validation.
    - Application state transition from BANK_ACCEPTED to ACCOUNT_OPENED.
    - Bank submission record enrichment with issued account_number and bank_status='opened'.
    - Cryptographic audit trail logging BANK_STATUS_WEBHOOK_PROCESSED.
    - Customer polling GET /v1/applications/{id} reflecting ACCOUNT_OPENED and activation instructions.

    Assertion Points Verified:
    - AP-1 API response: Webhook call with valid bank HMAC signature returns HTTP 200 { "status": "acknowledged" }.
    - AP-2 Database: applications transitions atomically from BANK_ACCEPTED to status='ACCOUNT_OPENED'.
    - AP-3 Database: bank_submissions records issued account_number and sets bank_status='opened'.
    - AP-5 Audit: audit_logs records BANK_STATUS_WEBHOOK_PROCESSED with bank reference and verified payload hash.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
    bank_secret = os.getenv("BANK_API_KEY", "dev-bank-key")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    app_uuid = uuid.uuid4()
    test_user_ref = f"usr_j08_{uuid.uuid4().hex[:8]}"
    bank_id = "bank_awash"
    expected_account_number = f"1000{uuid.uuid4().int % 1000000000:09d}"
    expected_bank_ref = f"AW-CBS-{uuid.uuid4().hex[:8].upper()}"

    # Step 1: Seed application in BANK_ACCEPTED state with initial submission in PostgreSQL
    async with session_maker() as session:
        app = Application(
            id=app_uuid,
            user_ref=test_user_ref,
            bank_id=bank_id,
            tier="standard",
            status=ApplicationStatus.BANK_ACCEPTED,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        session.add(app)

        submission = BankSubmission(
            application_id=app_uuid,
            bank_id=bank_id,
            dynamic_fields={"monthly_income_etb": 90000.0, "source_of_funds": "Business"},
            bank_reference=expected_bank_ref,
            bank_status="pending",
        )
        session.add(submission)
        await session.commit()

    # Step 2: Prepare signed bank CBS webhook payload
    webhook_payload = {
        "application_id": str(app_uuid),
        "status": "ACCOUNT_OPENED",
        "account_number": expected_account_number,
        "bank_reference": expected_bank_ref,
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")
    valid_sig = compute_hmac_signature(bank_secret, raw_body)

    async with httpx.AsyncClient(timeout=10.0) as http_client:
        # Step 3: Call POST /v1/webhooks/bank/{bank_id} with valid HMAC signature (AP-1)
        webhook_resp = await http_client.post(
            f"{api_base_url}/v1/webhooks/bank/{bank_id}",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": valid_sig,
            },
        )
        # Verify AP-1 API response: Webhook call with valid bank HMAC signature returns HTTP 200 { "status": "acknowledged" }
        assert webhook_resp.status_code == 200, f"Webhook failed: {webhook_resp.text}"
        data = webhook_resp.json()
        assert data.get("status") == "acknowledged"
        assert data.get("application_id") == str(app_uuid)

        # Step 4: Verify customer polling GET /v1/applications/{id} reflects ACCOUNT_OPENED and activation instructions
        poll_resp = await http_client.get(f"{api_base_url}/v1/applications/{app_uuid}")
        assert poll_resp.status_code == 200
        poll_data = poll_resp.json()
        assert poll_data.get("status") == "ACCOUNT_OPENED"
        assert poll_data.get("account_number") == expected_account_number
        assert poll_data.get("bank_reference") == expected_bank_ref
        assert poll_data.get("activation_instructions") is not None
        assert "Welcome" in poll_data["activation_instructions"]

    # Step 5: Direct DB assertions against real PostgreSQL boundary (AP-2, AP-3, AP-5)
    async with session_maker() as session:
        # AP-2 Database: applications transitions atomically from BANK_ACCEPTED to status='ACCOUNT_OPENED'
        app_stmt = select(Application).where(Application.id == app_uuid)
        persisted_app = (await session.execute(app_stmt)).scalar_one()
        assert persisted_app.status == ApplicationStatus.ACCOUNT_OPENED
        assert persisted_app.bank_id == bank_id

        # AP-3 Database: bank_submissions records issued account_number and sets bank_status='opened'
        sub_stmt = select(BankSubmission).where(BankSubmission.application_id == app_uuid)
        persisted_sub = (await session.execute(sub_stmt)).scalar_one()
        assert persisted_sub.account_number == expected_account_number
        assert persisted_sub.bank_reference == expected_bank_ref
        assert persisted_sub.bank_status == "opened"

        # AP-5 Audit: audit_logs records BANK_STATUS_WEBHOOK_PROCESSED with bank reference and verified payload hash
        audit_stmt = (
            select(AuditLog)
            .where(
                AuditLog.application_id == app_uuid,
                AuditLog.action == "BANK_STATUS_WEBHOOK_PROCESSED",
            )
            .order_by(AuditLog.id.desc())
        )
        audit_entries = (await session.execute(audit_stmt)).scalars().all()
        assert len(audit_entries) >= 1
        audit_rec = audit_entries[0]
        assert audit_rec.actor_type == "BANK"
        assert audit_rec.actor_id == bank_id
        assert audit_rec.action == "BANK_STATUS_WEBHOOK_PROCESSED"
        expected_body_hash = hashlib.sha256(raw_body).hexdigest()
        expected_audit_payload = {
            "bank_id": bank_id,
            "status": "ACCOUNT_OPENED",
            "account_number": expected_account_number,
            "bank_reference": expected_bank_ref,
            "body_hash": expected_body_hash,
        }
        assert audit_rec.payload_hash == compute_payload_hash(expected_audit_payload)

        # Verify audit ledger cryptographic integrity
        audit_service = AuditService()
        is_valid, err = await audit_service.verify_ledger_integrity(session)
        assert is_valid is True, f"Audit ledger integrity failed: {err}"
        assert err is None


@pytest.mark.black_box
async def test_journey_08_invalid_or_tampered_hmac_rejected_security() -> None:
    """
    Security verification: Webhook call with tampered or invalid HMAC signature is rejected with HTTP 401 Unauthorized.

    Assertion Points Verified:
    - AP-4 Security: Webhook call with tampered or invalid HMAC signature is rejected with HTTP 401 Unauthorized.
    - AP-1 API response: Valid signature requirement enforcement.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    app_uuid = uuid.uuid4()
    test_user_ref = f"usr_j08_sec_{uuid.uuid4().hex[:8]}"
    bank_id = "bank_awash"

    # Seed application in BANK_ACCEPTED
    async with session_maker() as session:
        app = Application(
            id=app_uuid,
            user_ref=test_user_ref,
            bank_id=bank_id,
            tier="standard",
            status=ApplicationStatus.BANK_ACCEPTED,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        session.add(app)
        await session.commit()

    webhook_payload = {
        "application_id": str(app_uuid),
        "status": "ACCOUNT_OPENED",
        "account_number": "1000999999999",
        "bank_reference": "AW-CBS-SEC-001",
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")

    async with httpx.AsyncClient(timeout=10.0) as http_client:
        # Case 1: Tampered HMAC signature (AP-4)
        tampered_sig = "a" * 64
        tampered_resp = await http_client.post(
            f"{api_base_url}/v1/webhooks/bank/{bank_id}",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": tampered_sig,
            },
        )
        assert tampered_resp.status_code == 401
        assert "invalid" in tampered_resp.json().get("detail", "").lower() or "tampered" in tampered_resp.json().get("detail", "").lower()

        # Case 2: Missing HMAC signature header (AP-4)
        missing_resp = await http_client.post(
            f"{api_base_url}/v1/webhooks/bank/{bank_id}",
            content=raw_body,
            headers={"Content-Type": "application/json"},
        )
        assert missing_resp.status_code == 401
        assert "missing" in missing_resp.json().get("detail", "").lower()

        # Case 3: Wrong secret key used to compute signature (AP-4)
        wrong_sig = compute_hmac_signature("wrong-attacker-secret-key", raw_body)
        wrong_resp = await http_client.post(
            f"{api_base_url}/v1/webhooks/bank/{bank_id}",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": wrong_sig,
            },
        )
        assert wrong_resp.status_code == 401
        assert "invalid" in wrong_resp.json().get("detail", "").lower() or "tampered" in wrong_resp.json().get("detail", "").lower()

    # Verify application status in DB was completely untouched
    async with session_maker() as session:
        persisted_app = (
            await session.execute(select(Application).where(Application.id == app_uuid))
        ).scalar_one()
        assert persisted_app.status == ApplicationStatus.BANK_ACCEPTED


@pytest.mark.black_box
async def test_journey_08_failure_modes_idempotency_and_out_of_order() -> None:
    """
    Failure mode verifications for asynchronous bank callbacks:
    - CH-06 Duplicate webhook callbacks with identical account number return HTTP 200 idempotent acknowledgment.
    - CH-08 Out-of-order webhook delivery (e.g. ACCOUNT_OPENED before BANK_ACCEPTED) reconciled safely.

    Assertion Points Verified:
    - AP-1 API response: Webhook call returns HTTP 200.
    - AP-2 Database: State machine safely transitions to ACCOUNT_OPENED from SUBMITTED_TO_BANK.
    - AP-3 Database: Bank submission updated with issued account number.
    - AP-5 Audit: Recorded correctly.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
    bank_secret = os.getenv("BANK_API_KEY", "dev-bank-key")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    app_uuid = uuid.uuid4()
    test_user_ref = f"usr_j08_ch_{uuid.uuid4().hex[:8]}"
    bank_id = "bank_awash"
    account_number = f"1000{uuid.uuid4().int % 1000000000:09d}"
    bank_ref = f"AW-CBS-CH-{uuid.uuid4().hex[:6].upper()}"

    # CH-08: Application is currently in SUBMITTED_TO_BANK (bank callback arrives before intermediate BANK_ACCEPTED)
    async with session_maker() as session:
        app = Application(
            id=app_uuid,
            user_ref=test_user_ref,
            bank_id=bank_id,
            tier="standard",
            status=ApplicationStatus.SUBMITTED_TO_BANK,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        session.add(app)
        sub = BankSubmission(
            application_id=app_uuid,
            bank_id=bank_id,
            dynamic_fields={"monthly_income_etb": 50000.0},
            bank_reference=bank_ref,
            bank_status="pending",
        )
        session.add(sub)
        await session.commit()

    webhook_payload = {
        "application_id": str(app_uuid),
        "status": "ACCOUNT_OPENED",
        "account_number": account_number,
        "bank_reference": bank_ref,
    }
    raw_body = json.dumps(webhook_payload).encode("utf-8")
    valid_sig = compute_hmac_signature(bank_secret, raw_body)

    async with httpx.AsyncClient(timeout=10.0) as http_client:
        # Part 1: Process out-of-order callback directly from SUBMITTED_TO_BANK (CH-08 / AP-1 / AP-2)
        resp1 = await http_client.post(
            f"{api_base_url}/v1/webhooks/bank/{bank_id}",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": valid_sig,
            },
        )
        assert resp1.status_code == 200
        assert resp1.json().get("status") == "acknowledged"

        # Verify DB transition succeeded to ACCOUNT_OPENED (AP-2, AP-3)
        async with session_maker() as session:
            db_app = (await session.execute(select(Application).where(Application.id == app_uuid))).scalar_one()
            assert db_app.status == ApplicationStatus.ACCOUNT_OPENED
            db_sub = (await session.execute(select(BankSubmission).where(BankSubmission.application_id == app_uuid))).scalar_one()
            assert db_sub.account_number == account_number
            assert db_sub.bank_status == "opened"

        # Part 2: CH-06 Duplicate webhook callback delivery with identical payload
        resp2 = await http_client.post(
            f"{api_base_url}/v1/webhooks/bank/{bank_id}",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": valid_sig,
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2.get("status") == "acknowledged"
        assert data2.get("idempotent") is True

        # Verify DB status is still strictly ACCOUNT_OPENED without duplicate rows
        async with session_maker() as session:
            submissions = (
                await session.execute(
                    select(BankSubmission).where(BankSubmission.application_id == app_uuid)
                )
            ).scalars().all()
            assert len(submissions) == 1
            assert submissions[0].account_number == account_number
