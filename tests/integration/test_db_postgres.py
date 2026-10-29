import os
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select

from src.models.base import DATABASE_URL, init_models, drop_models, async_session_factory
from src.models.application import (
    Application,
    ApplicationStatus,
    IdentitySnapshot,
    VerificationMethod,
    ConsentRecord,
    BankSubmission,
)
from src.models.audit import AuditLog


@pytest.mark.asyncio
async def test_real_postgres_application_lifecycle_and_cascade() -> None:
    # 1. Initialize schema in live database
    await drop_models()
    await init_models()

    now = datetime.now(timezone.utc)
    app_id = uuid.uuid4()
    user_ref = f"usr_{uuid.uuid4().hex[:12]}"

    # 2. Persist Application in real PostgreSQL
    async with async_session_factory() as session:
        app = Application(
            id=app_id,
            user_ref=user_ref,
            bank_id="bank_awash",
            tier="standard",
            status=ApplicationStatus.DRAFT,
            expires_at=now + timedelta(hours=24),
        )
        session.add(app)
        await session.commit()

    # 3. Query Application back and assert persisted attributes
    async with async_session_factory() as session:
        result = await session.execute(
            select(Application).where(Application.id == app_id)
        )
        fetched_app = result.scalar_one()
        assert fetched_app.id == app_id
        assert fetched_app.user_ref == user_ref
        assert fetched_app.bank_id == "bank_awash"
        assert fetched_app.status == ApplicationStatus.DRAFT

        # 4. Attach IdentitySnapshot and ConsentRecord
        snapshot = IdentitySnapshot(
            application_id=app_id,
            encrypted_full_name=b"encrypted_alemu_kebede",
            encrypted_dob=b"encrypted_1990_05_12",
            gender="MALE",
            fayda_ref_hash="salted_hash_fayda_12345",
            liveness_score=0.96,
            verification_method=VerificationMethod.OTP,
        )
        consent = ConsentRecord(
            id=uuid.uuid4(),
            application_id=app_id,
            consent_version="v2.1",
            ip_address="197.156.78.90",
            device_fingerprint="device_fp_addis_ababa_01",
        )
        submission = BankSubmission(
            id=uuid.uuid4(),
            application_id=app_id,
            bank_id="bank_awash",
            dynamic_fields={"branch_code": "001", "monthly_income": 50000},
            bank_reference="AWASH-CBS-9988",
            account_number="100055443322",
            retry_count=0,
        )
        session.add_all([snapshot, consent, submission])
        await session.commit()

    # 5. Verify records exist and foreign keys resolve
    async with async_session_factory() as session:
        snap_res = await session.execute(
            select(IdentitySnapshot).where(IdentitySnapshot.application_id == app_id)
        )
        saved_snap = snap_res.scalar_one()
        assert saved_snap.gender == "MALE"
        assert saved_snap.liveness_score == 0.96
        assert saved_snap.encrypted_full_name == b"encrypted_alemu_kebede"

        sub_res = await session.execute(
            select(BankSubmission).where(BankSubmission.application_id == app_id)
        )
        saved_sub = sub_res.scalar_one()
        assert saved_sub.bank_reference == "AWASH-CBS-9988"
        assert saved_sub.account_number == "100055443322"
        assert saved_sub.dynamic_fields["branch_code"] == "001"

    # 6. Test Cascade Delete: deleting Application must cascade-delete attached child rows
    async with async_session_factory() as session:
        res = await session.execute(
            select(Application).where(Application.id == app_id)
        )
        target = res.scalar_one()
        await session.delete(target)
        await session.commit()

    async with async_session_factory() as session:
        orphan_snap = await session.execute(
            select(IdentitySnapshot).where(IdentitySnapshot.application_id == app_id)
        )
        assert orphan_snap.scalar_one_or_none() is None

        orphan_consent = await session.execute(
            select(ConsentRecord).where(ConsentRecord.application_id == app_id)
        )
        assert orphan_consent.scalar_one_or_none() is None

        orphan_sub = await session.execute(
            select(BankSubmission).where(BankSubmission.application_id == app_id)
        )
        assert orphan_sub.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_real_postgres_audit_log_persistence() -> None:
    await init_models()

    async with async_session_factory() as session:
        log_entry = AuditLog(
            actor_type="SYSTEM",
            actor_id="ekyc_orchestrator",
            action="APPLICATION_SUBMITTED",
            payload_hash="sha256_hash_payload_1234567890abcdef",
            prev_log_hash="sha256_root_zero_prev_hash",
            hmac_signature="hmac_sha256_signed_audit_block",
        )
        session.add(log_entry)
        await session.commit()
        assigned_id = log_entry.id

    async with async_session_factory() as session:
        result = await session.execute(
            select(AuditLog).where(AuditLog.id == assigned_id)
        )
        retrieved = result.scalar_one()
        assert retrieved.id == assigned_id
        assert retrieved.actor_type == "SYSTEM"
        assert retrieved.action == "APPLICATION_SUBMITTED"
        assert retrieved.payload_hash == "sha256_hash_payload_1234567890abcdef"
        assert retrieved.prev_log_hash == "sha256_root_zero_prev_hash"
        assert retrieved.hmac_signature == "hmac_sha256_signed_audit_block"
