import asyncio
import json
import os
import signal
import sys
import uuid
from datetime import datetime, timedelta, timezone
import pytest
import redis.asyncio as aioredis
from sqlalchemy import select

from src.clients.bank_cbs_client import BANK_CBS_SANDBOX_URL, BankCBSClient
from src.infrastructure.queue import SubmissionQueue
from src.models.application import (
    Application,
    ApplicationStatus,
    BankSubmission,
    IdentitySnapshot,
    VerificationMethod,
)
from src.models.audit import AuditLog
from src.models.base import async_session_factory, drop_models, init_models
from src.security.encryption import encrypt_str
from src.services.audit import AuditService
from src.workers.bank_submission import BankSubmissionWorker


@pytest.mark.asyncio
async def test_real_submission_worker_db_queue_cbs_and_process_boundaries() -> None:
    # 1. Assert real environment boundary presence
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/ekyc_db")
    assert "postgresql" in db_url or "asyncpg" in db_url

    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    assert redis_url.startswith("redis://")

    cbs_url = os.getenv("BANK_CBS_SANDBOX_URL", "http://127.0.0.1:8082/cbs/v1")
    assert "8082" in cbs_url or "cbs" in cbs_url

    # 2. Reset and initialize PostgreSQL schema
    await drop_models()
    await init_models()

    # 3. Setup Redis connection and isolated stream
    redis_client = aioredis.from_url(redis_url, decode_responses=True)
    stream_name = f"test_worker_stream_{uuid.uuid4().hex[:8]}"
    group_name = f"test_worker_group_{uuid.uuid4().hex[:8]}"
    dlq_name = f"test_worker_dlq_{uuid.uuid4().hex[:8]}"
    heartbeat_key = f"test_worker:heartbeat_{uuid.uuid4().hex[:8]}"

    queue = SubmissionQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        dlq_name=dlq_name,
        group_name=group_name,
    )

    try:
        # 4. Insert real Application in PostgreSQL ready for bank submission
        app_id = uuid.uuid4()
        user_ref = f"usr_{uuid.uuid4().hex[:8]}"
        bank_id = "bank_awash"

        async with async_session_factory() as session:
            app = Application(
                id=app_id,
                user_ref=user_ref,
                bank_id=bank_id,
                tier="standard",
                status=ApplicationStatus.SUBMITTED_TO_BANK,
                idempotency_hash=f"idem_hash_{uuid.uuid4().hex}",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            )
            snapshot = IdentitySnapshot(
                application_id=app_id,
                encrypted_full_name=encrypt_str("Alemu Kebede"),
                encrypted_dob=encrypt_str("1991-08-14"),
                gender="MALE",
                fayda_ref_hash=f"fayda_hash_{uuid.uuid4().hex[:8]}",
                liveness_score=0.96,
                verification_method=VerificationMethod.OTP,
            )
            submission = BankSubmission(
                id=uuid.uuid4(),
                application_id=app_id,
                bank_id=bank_id,
                dynamic_fields={
                    "monthly_income_etb": 42000,
                    "occupation": "Software Architect",
                    "source_of_funds": "Salary",
                },
                retry_count=0,
            )
            session.add_all([app, snapshot, submission])
            await session.commit()

        # 5. Enqueue submission event into live Redis stream
        msg_id = await queue.enqueue(
            application_id=str(app_id),
            bank_id=bank_id,
            payload={
                "event_name": "application_submitted_event",
                "application_id": str(app_id),
                "bank_id": bank_id,
                "tier": "standard",
            },
            idempotency_key=f"idem_queue_{app_id}",
        )
        assert msg_id is not None
        assert len(msg_id) > 0

        # 6. Instantiate real BankSubmissionWorker pointing to live CBS sandbox
        cbs_client = BankCBSClient(base_url=cbs_url)
        audit_service = AuditService()

        worker = BankSubmissionWorker(
            queue=queue,
            audit_service=audit_service,
            session_factory=async_session_factory,
            redis_client=redis_client,
            cbs_client=cbs_client,
            worker_id="int-worker-01",
            heartbeat_key=heartbeat_key,
        )

        # 7. Emit and verify live Redis heartbeat
        await worker.emit_heartbeat()
        raw_hb = await redis_client.get(heartbeat_key)
        assert raw_hb is not None
        hb_data = json.loads(raw_hb)
        assert hb_data["worker_id"] == "int-worker-01"
        assert hb_data["status"] == "ALIVE"
        assert "timestamp" in hb_data

        # 8. Execute worker cycle against live queue and CBS sandbox
        processed_count = await worker.run_once(count=1, block_ms=1500)
        assert processed_count == 1

        # 9. Verify PostgreSQL state updated to ACCOUNT_OPENED with real CBS account number
        async with async_session_factory() as session:
            stmt = select(Application).where(Application.id == app_id)
            res = await session.execute(stmt)
            updated_app = res.scalar_one()
            assert updated_app.status == ApplicationStatus.ACCOUNT_OPENED

            sub_stmt = select(BankSubmission).where(BankSubmission.application_id == app_id)
            sub_res = await session.execute(sub_stmt)
            updated_sub = sub_res.scalar_one()
            assert updated_sub.account_number is not None
            assert len(updated_sub.account_number) >= 10
            assert updated_sub.bank_reference is not None
            assert len(updated_sub.bank_reference) > 0

        # 10. Verify Redis queue message was acknowledged
        unacked = await queue.dequeue(consumer_name="int-worker-01", count=1, block_ms=500)
        assert len(unacked) == 0

        # 11. Verify Audit Ledger integrity in PostgreSQL
        async with async_session_factory() as session:
            is_valid, error = await audit_service.verify_ledger_integrity(session)
            assert is_valid is True, f"Audit verification failed: {error}"
            assert error is None

            # Verify audit entry for CBS submission exists
            audit_stmt = select(AuditLog).where(AuditLog.application_id == app_id)
            audit_entries = (await session.execute(audit_stmt)).scalars().all()
            assert len(audit_entries) >= 1
            assert audit_entries[0].action == "CBS_ACCOUNT_ISSUED"
            assert audit_entries[0].actor_type == "WORKER"

        # 12. Test Daemon Process Execution (worker boundary as a real OS process)
        env = os.environ.copy()
        env["BANK_CBS_SANDBOX_URL"] = cbs_url
        env["DATABASE_URL"] = db_url
        env["REDIS_URL"] = redis_url

        daemon_proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "src.workers.bank_submission",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait for daemon process to emit default heartbeat to Redis
        hb_found = False
        for _ in range(20):
            await asyncio.sleep(0.3)
            default_hb = await redis_client.get("worker:heartbeat")
            if default_hb:
                hb_found = True
                break

        assert hb_found is True

        # Send SIGTERM to daemon process and verify clean graceful shutdown
        daemon_proc.send_signal(signal.SIGTERM)
        await asyncio.wait_for(daemon_proc.wait(), timeout=5.0)
        assert daemon_proc.returncode == 0

    finally:
        await redis_client.delete(stream_name)
        await redis_client.delete(dlq_name)
        await redis_client.delete(heartbeat_key)
        await redis_client.delete("worker:heartbeat")
        await redis_client.aclose()
