import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.api.main import app
from src.infrastructure.redis import get_redis_client
from src.models.application import (
    Application,
    ApplicationStatus,
    BankSubmission,
    ConsentRecord,
)
from src.models.audit import AuditLog
from src.models.base import async_session_factory, drop_models, init_models
from src.services.audit import AuditService


@pytest.mark.asyncio
async def test_api_gateway_real_postgres_redis_readiness_and_lifecycle_boundaries() -> None:
    """Verifies live API gateway endpoints against real PostgreSQL and Redis containers (db boundary)."""
    # 1. Assert real environment boundary presence
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/ekyc_db")
    assert "postgresql" in db_url or "asyncpg" in db_url

    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    assert redis_url.startswith("redis://")

    # 2. Reset and initialize PostgreSQL schema
    await drop_models()
    await init_models()

    from src.infrastructure.redis import close_redis_pool
    await close_redis_pool()

    redis_client = get_redis_client()
    pong = await redis_client.ping()
    assert pong is True

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 3. Test Deep Readiness Probe against live PostgreSQL and Redis
        ready_resp = await ac.get("/health/ready")
        assert ready_resp.status_code == 200
        ready_data = ready_resp.json()
        assert ready_data["status"] == "ready"
        assert ready_data["components"]["database"] == "connected"
        assert ready_data["components"]["redis"] == "connected"

        # 4. Test POST /v1/applications creating real row in PostgreSQL
        user_ref = f"usr_integ_{uuid.uuid4().hex[:8]}"
        create_resp = await ac.post(
            "/v1/applications",
            json={"user_ref": user_ref, "bank_id": "bank_awash", "tier": "standard"},
            headers={"X-Device-Fingerprint": "fp_integration_test"},
        )
        assert create_resp.status_code == 201
        create_data = create_resp.json()
        app_id = uuid.UUID(create_data["application_id"])
        assert create_data["status"] == "DRAFT"
        assert "token" in create_data
        token = create_data["token"]
        assert len(token) > 20

        # Verify real PostgreSQL database row
        async with async_session_factory() as session:
            stmt = select(Application).where(Application.id == app_id)
            db_app = (await session.execute(stmt)).scalar_one()
            assert db_app.user_ref == user_ref
            assert db_app.bank_id == "bank_awash"
            assert db_app.status == ApplicationStatus.DRAFT

        # 5. Test GET /v1/applications/{id} reading real database state
        get_resp = await ac.get(f"/v1/applications/{app_id}", headers={"Authorization": f"Bearer {token}"})
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["application_id"] == str(app_id)
        assert get_data["user_ref"] == user_ref
        assert get_data["status"] == "DRAFT"

        # 6. Test POST /v1/applications/{id}/consent mutating real PostgreSQL database
        consent_resp = await ac.post(
            f"/v1/applications/{app_id}/consent",
            json={"consent_version": "v1.2", "accepted": True},
            headers={
                "Authorization": f"Bearer {token}",
                "X-Device-Fingerprint": "fp_integration_test",
            },
        )
        assert consent_resp.status_code == 200
        consent_data = consent_resp.json()
        assert consent_data["status"] == "CONSENTED"
        assert consent_data["application_id"] == str(app_id)

        # Verify ConsentRecord and AuditLog persisted to real PostgreSQL
        async with async_session_factory() as session:
            app_stmt = select(Application).where(Application.id == app_id)
            app_row = (await session.execute(app_stmt)).scalar_one()
            assert app_row.status == ApplicationStatus.CONSENTED

            consent_stmt = select(ConsentRecord).where(ConsentRecord.application_id == app_id)
            consent_rows = (await session.execute(consent_stmt)).scalars().all()
            assert len(consent_rows) == 1
            assert consent_rows[0].consent_version == "v1.2"
            assert consent_rows[0].device_fingerprint == "fp_integration_test"

            audit_stmt = select(AuditLog).where(AuditLog.application_id == app_id)
            audit_rows = (await session.execute(audit_stmt)).scalars().all()
            assert len(audit_rows) >= 2  # APPLICATION_CREATED and CONSENT_GRANTED
            assert any(row.action == "CONSENT_GRANTED" for row in audit_rows)

        # 7. Advance state to LIVENESS_PASSED directly in DB to test details validation
        async with async_session_factory() as session:
            app_to_advance = (await session.execute(select(Application).where(Application.id == app_id))).scalar_one()
            app_to_advance.status = ApplicationStatus.LIVENESS_PASSED
            await session.commit()

        # 8. Test PUT /v1/applications/{id}/details schema validation against live DB
        # 8a. Invalid dynamic schema properties return HTTP 400
        bad_details_resp = await ac.put(
            f"/v1/applications/{app_id}/details",
            json={"dynamic_fields": {"monthly_income_etb": -100}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert bad_details_resp.status_code == 400
        bad_data = bad_details_resp.json()
        assert bad_data["status"] == 400
        assert "validation failed" in bad_data["title"].lower()

        # 8b. Valid dynamic schema properties persist to PostgreSQL
        good_details = {
            "monthly_income_etb": 45000,
            "occupation": "Senior Security Engineer",
            "source_of_funds": "Salary",
            "branch_code": "BR-001",
        }
        good_details_resp = await ac.put(
            f"/v1/applications/{app_id}/details",
            json={"dynamic_fields": good_details},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert good_details_resp.status_code == 200
        good_data = good_details_resp.json()
        assert good_data["status"] == "DATA_COMPLETE"

        # Verify BankSubmission persisted in PostgreSQL
        async with async_session_factory() as session:
            sub_stmt = select(BankSubmission).where(BankSubmission.application_id == app_id)
            sub_rows = (await session.execute(sub_stmt)).scalars().all()
            assert len(sub_rows) == 1
            assert sub_rows[0].dynamic_fields["monthly_income_etb"] == 45000
            assert sub_rows[0].dynamic_fields["occupation"] == "Senior Security Engineer"

        # 9. Test Signed Bank Webhook Callback (J-08) updating real PostgreSQL
        async with async_session_factory() as session:
            app_to_sub = (await session.execute(select(Application).where(Application.id == app_id))).scalar_one()
            app_to_sub.status = ApplicationStatus.SUBMITTED_TO_BANK
            await session.commit()

        issued_account = "1000887766554"
        issued_ref = "AW-REF-7766"
        webhook_payload = {
            "application_id": str(app_id),
            "status": "ACCOUNT_OPENED",
            "account_number": issued_account,
            "bank_reference": issued_ref,
        }
        raw_webhook_body = json.dumps(webhook_payload).encode("utf-8")
        bank_key = os.getenv("BANK_API_KEY", "dev-bank-key")
        signature = hmac.new(bank_key.encode(), raw_webhook_body, hashlib.sha256).hexdigest()

        webhook_resp = await ac.post(
            "/v1/webhooks/bank/bank_awash",
            content=raw_webhook_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": signature,
            },
        )
        assert webhook_resp.status_code == 200
        webhook_data = webhook_resp.json()
        assert webhook_data["status"] == "acknowledged"
        assert webhook_data["application_id"] == str(app_id)

        # Verify final state and account number in PostgreSQL
        async with async_session_factory() as session:
            final_app = (await session.execute(select(Application).where(Application.id == app_id))).scalar_one()
            assert final_app.status == ApplicationStatus.ACCOUNT_OPENED

            final_sub = (await session.execute(select(BankSubmission).where(BankSubmission.application_id == app_id))).scalar_one()
            assert final_sub.account_number == issued_account
            assert final_sub.bank_reference == issued_ref

            # Verify audit ledger integrity
            audit_svc = AuditService()
            is_valid, err = await audit_svc.verify_ledger_integrity(session)
            assert is_valid is True, f"Audit ledger integrity failed: {err}"
            assert err is None

            webhook_audit_stmt = select(AuditLog).where(
                AuditLog.application_id == app_id,
                AuditLog.action == "BANK_STATUS_WEBHOOK_PROCESSED",
            )
            webhook_audits = (await session.execute(webhook_audit_stmt)).scalars().all()
            assert len(webhook_audits) == 1
            assert webhook_audits[0].actor_type == "BANK"
            assert webhook_audits[0].actor_id == "bank_awash"

        # 10. Test Duplicate Webhook Callback Idempotency against live DB
        dup_webhook_resp = await ac.post(
            "/v1/webhooks/bank/bank_awash",
            content=raw_webhook_body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": signature,
            },
        )
        assert dup_webhook_resp.status_code == 200
        dup_data = dup_webhook_resp.json()
        assert dup_data["status"] == "acknowledged"
        assert dup_data["idempotent"] is True
