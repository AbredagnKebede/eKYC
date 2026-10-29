import os
import uuid
import pytest
from sqlalchemy import update, select

from src.models.base import DATABASE_URL, init_models, drop_models, async_session_factory
from src.models.audit import AuditLog
from src.services.audit import AuditService


@pytest.mark.asyncio
async def test_real_postgres_audit_ledger_chain_and_tamper_detection() -> None:
    assert "postgresql" in DATABASE_URL
    await drop_models()
    await init_models()

    audit_svc = AuditService(secret_key="integration-test-secret-salt")
    app_id = uuid.uuid4()

    # 1. Record sequential audit log entries
    async with async_session_factory() as session:
        e1 = await audit_svc.record_event(
            session=session,
            actor_type="CUSTOMER",
            actor_id="dev_client_001",
            action="CONSENT_GRANTED",
            application_id=app_id,
            payload={"version": "1.0", "terms": "accepted"},
        )
        assert e1.action == "CONSENT_GRANTED"
        assert e1.actor_type == "CUSTOMER"
        await session.commit()

    async with async_session_factory() as session:
        e2 = await audit_svc.record_event(
            session=session,
            actor_type="SYSTEM",
            actor_id="identity_verifier",
            action="IDENTITY_VERIFIED",
            application_id=app_id,
            payload={"status": "VERIFIED", "method": "OTP"},
        )
        assert e2.action == "IDENTITY_VERIFIED"
        assert e2.actor_type == "SYSTEM"
        await session.commit()

    async with async_session_factory() as session:
        e3 = await audit_svc.record_event(
            session=session,
            actor_type="CUSTOMER",
            actor_id="dev_client_001",
            action="APPLICATION_SUBMITTED",
            application_id=app_id,
            payload={"bank": "bank_awash", "tier": "standard"},
        )
        assert e3.action == "APPLICATION_SUBMITTED"
        assert e3.actor_type == "CUSTOMER"
        await session.commit()

    # 2. Verify complete chain integrity on pristine database
    async with async_session_factory() as session:
        is_valid, err = await audit_svc.verify_ledger_integrity(session)
        assert is_valid is True
        assert err is None

    # 3. Simulate unauthorized database tampering on row 2 (e.g. rogue DBA modifies payload_hash)
    async with async_session_factory() as session:
        await session.execute(
            update(AuditLog)
            .where(AuditLog.action == "IDENTITY_VERIFIED")
            .values(payload_hash="malicious_forged_hash_value_1234567890abcdef")
        )
        await session.commit()

    # 4. Verify that cryptographic audit verification immediately catches the tampering
    async with async_session_factory() as session:
        is_valid_after_tamper, tamper_error = await audit_svc.verify_ledger_integrity(session)
        assert is_valid_after_tamper is False
        assert "Chain break" in tamper_error or "mismatch" in tamper_error
