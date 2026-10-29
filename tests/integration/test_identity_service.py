import os
import uuid
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from src.clients.fayda_client import FaydaClient, FAYDA_API_KEY, FAYDA_SANDBOX_URL
from src.models.application import Application, ApplicationStatus, IdentitySnapshot, VerificationMethod
from src.models.base import DATABASE_URL, async_session_factory, drop_models, init_models
from src.security.liveness import LivenessEngine
from src.services.audit import AuditService
from src.services.identity import IdentityService


@pytest.mark.asyncio
async def test_real_identity_service_with_postgres_and_fayda_sandbox() -> None:
    # 1. Real boundary assertions
    assert "postgresql" in DATABASE_URL
    sandbox_url = os.getenv("FAYDA_SANDBOX_URL", "http://127.0.0.1:8081/fayda/v2")
    assert "sandbox" in sandbox_url.lower() or "8081" in sandbox_url

    # Reset clean schema
    await drop_models()
    await init_models()

    fayda_client = FaydaClient(base_url=sandbox_url, api_key=FAYDA_API_KEY)
    audit_service = AuditService(secret_key="integration-test-secret-salt")
    liveness_engine = LivenessEngine()

    service = IdentityService(
        fayda_client=fayda_client,
        liveness_engine=liveness_engine,
        audit_service=audit_service,
    )

    app_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # 2. Seed initial application in Postgres
    async with async_session_factory() as session:
        new_app = Application(
            id=app_id,
            user_ref="citizen_user_001",
            bank_id="awash",
            tier="standard",
            status=ApplicationStatus.CONSENTED,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=2),
        )
        session.add(new_app)
        await session.commit()

    # 3. Start Fayda OTP verification over real HTTP sandbox
    async with async_session_factory() as session:
        challenge = await service.start_fayda_verification(
            application_id=app_id,
            fin="123456789012",
            session=session,
        )
        assert challenge["status"] == "OTP_SENT"
        assert challenge["expires_in"] == 180
        tx_id = challenge["transaction_id"]
        assert tx_id.startswith("tx_fayda_")

    # 4. Verify OTP against real sandbox and store encrypted snapshot in Postgres
    async with async_session_factory() as session:
        snapshot = await service.verify_fayda_otp(
            application_id=app_id,
            transaction_id=tx_id,
            otp="123456",
            session=session,
        )
        assert snapshot.application_id == app_id
        assert snapshot.gender == "MALE"
        assert snapshot.verification_method == VerificationMethod.OTP
        assert len(snapshot.fayda_ref_hash) == 64

        # Verify ciphertext properties (AES-256-GCM envelope: >= 28 bytes)
        assert isinstance(snapshot.encrypted_full_name, bytes)
        assert len(snapshot.encrypted_full_name) >= 28
        assert isinstance(snapshot.encrypted_dob, bytes)
        assert len(snapshot.encrypted_dob) >= 28

        # Critical zero-retention check: cleartext name and DOB never appear in raw DB bytes
        assert b"Alemu" not in snapshot.encrypted_full_name
        assert b"1992" not in snapshot.encrypted_dob

    # 5. Verify application state transitioned to ID_VERIFIED in Postgres
    async with async_session_factory() as session:
        stmt = select(Application).where(Application.id == app_id)
        res = await session.execute(stmt)
        app = res.scalar_one()
        assert app.status == ApplicationStatus.ID_VERIFIED

        # Decrypt demographic payload
        demographics = await service.get_decrypted_demographics(app_id, session)
        assert demographics["full_name"] == "Alemu Kebede Tadesse"
        assert demographics["date_of_birth"] == "1992-05-18"
        assert demographics["gender"] == "MALE"

    # 6. Execute live anti-spoofing and face comparison verification
    async with async_session_factory() as session:
        live_selfie = b"alemu_live_highres_selfie_feed_data_frame1_frame2"
        fayda_ref_photo = b"fayda_id_photo_alemu_citizen_archive_sample"

        liveness_out = await service.verify_liveness_and_face(
            application_id=app_id,
            selfie_bytes=live_selfie,
            fayda_photo_bytes=fayda_ref_photo,
            session=session,
        )
        assert liveness_out["status"] == "LIVENESS_PASSED"
        assert liveness_out["liveness_score"] >= 0.90
        assert liveness_out["face_match_score"] >= 0.82

    # 7. Verify application state transitioned to LIVENESS_PASSED in Postgres
    async with async_session_factory() as session:
        stmt = select(Application).where(Application.id == app_id)
        res = await session.execute(stmt)
        app_after_liveness = res.scalar_one()
        assert app_after_liveness.status == ApplicationStatus.LIVENESS_PASSED

        snap_stmt = select(IdentitySnapshot).where(IdentitySnapshot.application_id == app_id)
        snap_res = await session.execute(snap_stmt)
        snap_updated = snap_res.scalar_one()
        assert snap_updated.liveness_score >= 0.90

        # 8. Cryptographic audit trail validation across all events
        is_valid, issue = await audit_service.verify_ledger_integrity(session)
        assert is_valid is True
        assert issue is None
