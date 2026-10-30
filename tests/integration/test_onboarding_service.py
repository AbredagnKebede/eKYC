import os
import uuid
import pytest
import redis.asyncio as aioredis
from src.infrastructure.queue import SubmissionQueue
from src.models.base import async_session_factory, drop_models, init_models
from src.models.application import (
    Application,
    ApplicationStatus,
    Base,
    IdentitySnapshot,
    VerificationMethod,
)
from src.models.audit import AuditLog
from src.services.audit import AuditService
from src.services.onboarding import OnboardingService


@pytest.mark.asyncio
async def test_real_onboarding_service_lifecycle_db_and_queue() -> None:
    # Real db and queue boundary verification
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/ekyc_db")
    assert "postgresql" in db_url or "asyncpg" in db_url

    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    assert redis_url.startswith("redis://")

    # Connect to live PostgreSQL and isolate test schema
    await drop_models()
    await init_models()

    # Connect to live Redis
    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    stream_name = f"test_onboarding_stream_{uuid.uuid4().hex[:8]}"
    group_name = f"test_onboarding_group_{uuid.uuid4().hex[:8]}"

    queue = SubmissionQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        group_name=group_name,
    )
    audit_service = AuditService()
    service = OnboardingService(audit_service=audit_service, queue=queue)

    try:
        user_ref = f"usr_{uuid.uuid4().hex[:8]}"
        bank_id = "bank_awash"

        # 1. Create Application in DB
        async with async_session_factory() as session:
            app = await service.create_application(
                session=session,
                user_ref=user_ref,
                bank_id=bank_id,
                tier="standard",
            )
            app_id = app.id
            await session.commit()

        assert app_id is not None

        # 2. Record Consent in DB
        async with async_session_factory() as session:
            app = await service.record_consent(
                session=session,
                application_id=app_id,
                consent_version="v2.1",
                ip_address="197.156.104.22",
                device_fingerprint="fp_samsung_galaxy_a12",
            )
            assert app.status == ApplicationStatus.CONSENTED
            await session.commit()

        # 3. Attach Verified Identity Snapshot in DB
        async with async_session_factory() as session:
            snapshot = IdentitySnapshot(
                application_id=app_id,
                encrypted_full_name=b"aes_encrypted_alemu_kebede",
                encrypted_dob=b"aes_encrypted_1992_05_18",
                gender="MALE",
                fayda_ref_hash="sha256_salted_fayda_hash_7788",
                liveness_score=0.0,
                verification_method=VerificationMethod.OTP,
            )
            app = await service.attach_identity_snapshot(
                session=session,
                application_id=app_id,
                snapshot=snapshot,
            )
            assert app.status == ApplicationStatus.ID_VERIFIED
            await session.commit()

        # 4. Evaluate and Record Liveness (Score 0.95, Similarity 0.89)
        async with async_session_factory() as session:
            app = await service.record_liveness(
                session=session,
                application_id=app_id,
                liveness_score=0.95,
                face_similarity=0.89,
            )
            assert app.status == ApplicationStatus.LIVENESS_PASSED
            await session.commit()

        # 5. Save Dynamic Intake Fields in DB
        async with async_session_factory() as session:
            dynamic_data = {
                "monthly_income_etb": 28000,
                "occupation": "Civil Engineer",
                "source_of_funds": "Salary",
            }
            app = await service.save_dynamic_fields(
                session=session,
                application_id=app_id,
                dynamic_fields=dynamic_data,
            )
            assert app.status == ApplicationStatus.DATA_COMPLETE
            await session.commit()

        # 6. Submit Application: ACID mutation in DB + Enqueue into Redis stream
        async with async_session_factory() as session:
            app = await service.submit_application(
                session=session,
                application_id=app_id,
                signature="data:image/svg+xml;base64,signedDigitalCanvas",
            )
            assert app.status == ApplicationStatus.SUBMITTED_TO_BANK
            assert app.idempotency_hash is not None
            await session.commit()

        # 7. Verify Redis Stream Message was published and acknowledged
        messages = await queue.dequeue(consumer_name="worker-int-test", count=1)
        assert len(messages) == 1
        queue_msg = messages[0]
        assert queue_msg.application_id == str(app_id)
        assert queue_msg.bank_id == bank_id
        assert queue_msg.payload["tier"] == "standard"
        assert len(queue_msg.payload["payload_signature"]) == 64
        await queue.acknowledge(queue_msg.message_id)

        # 8. Reconcile Account Opening Status Mutation
        async with async_session_factory() as session:
            app = await service.update_bank_status(
                session=session,
                application_id=app_id,
                new_status=ApplicationStatus.ACCOUNT_OPENED,
                account_number="1000987654321",
                bank_reference="AWASH-CBS-REF-987",
            )
            assert app.status == ApplicationStatus.ACCOUNT_OPENED
            assert len(app.submissions) == 1
            assert app.submissions[0].account_number == "1000987654321"
            assert app.submissions[0].bank_reference == "AWASH-CBS-REF-987"
            await session.commit()

        # 9. Verify Audit Trail and Cryptographic Hash Chaining Integrity in DB
        async with async_session_factory() as session:
            is_valid, error = await audit_service.verify_ledger_integrity(session)
            assert is_valid is True, f"Audit verification failed: {error}"
            assert error is None

    finally:
        await redis_client.delete(stream_name)
        await redis_client.aclose()
