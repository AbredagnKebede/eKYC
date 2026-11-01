import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.clients.bank_cbs_client import (
    BankCBSConnectionError,
    BankCBSPayloadError,
    BankCBSUnavailableError,
)
from src.infrastructure.queue import QueueMessage
from src.models.application import (
    Application,
    ApplicationStatus,
    BankSubmission,
    IdentitySnapshot,
)
from src.services.bank_adapter import BankAdapterExecutionError, BankSchemaValidationError
from src.workers.bank_submission import (
    BankSubmissionWorker,
    calculate_backoff,
)


def test_calculate_backoff_values() -> None:
    # 1. Base values and exponential scaling
    assert calculate_backoff(0, base_delay=2.0) == 2.0
    assert calculate_backoff(1, base_delay=2.0) == 4.0
    assert calculate_backoff(2, base_delay=2.0) == 8.0
    assert calculate_backoff(3, base_delay=2.0) == 16.0
    assert calculate_backoff(4, base_delay=2.0) == 32.0

    # 2. Negative attempt normalization
    assert calculate_backoff(-1, base_delay=5.0) == 5.0

    # 3. Max delay ceiling capping
    assert calculate_backoff(10, base_delay=5.0, max_delay=60.0) == 60.0
    assert calculate_backoff(20, base_delay=10.0, max_delay=300.0) == 300.0


def test_build_submission_payload_reconstruction() -> None:
    app_id = uuid.uuid4()
    app = Application(
        id=app_id,
        user_ref="user_xyz",
        bank_id="bank_awash",
        tier="standard",
        status=ApplicationStatus.SUBMITTED_TO_BANK,
    )
    snapshot = IdentitySnapshot(
        application_id=app_id,
        encrypted_full_name=b"ciphertext_full_name",
        encrypted_dob=b"ciphertext_dob",
        gender="FEMALE",
        fayda_ref_hash="sha256_hash",
        liveness_score=0.98,
    )
    submission = BankSubmission(
        id=uuid.uuid4(),
        application_id=app_id,
        bank_id="bank_awash",
        dynamic_fields={"monthly_income_etb": 35000, "occupation": "Doctor"},
    )
    app.identity_snapshot = snapshot
    app.submissions = [submission]

    worker = BankSubmissionWorker()
    payload = worker.build_submission_payload(app)

    assert payload["application_id"] == str(app_id)
    assert payload["bank_id"] == "bank_awash"
    assert payload["tier"] == "standard"
    assert payload["dynamic_fields"]["monthly_income_etb"] == 35000
    assert payload["dynamic_fields"]["occupation"] == "Doctor"
    assert payload["demographics"]["gender"] == "FEMALE"


@pytest.mark.asyncio
async def test_worker_emit_heartbeat() -> None:
    mock_redis = AsyncMock()
    worker = BankSubmissionWorker(redis_client=mock_redis, worker_id="worker-test-01")

    await worker.emit_heartbeat()

    mock_redis.set.assert_awaited_once()
    call_args = mock_redis.set.call_args
    assert call_args[0][0] == "worker:heartbeat"
    heartbeat_data = json.loads(call_args[0][1])
    assert heartbeat_data["worker_id"] == "worker-test-01"
    assert heartbeat_data["status"] == "ALIVE"
    assert "timestamp" in heartbeat_data
    assert call_args[1]["ex"] == 30


@pytest.mark.asyncio
async def test_process_message_success_path() -> None:
    app_id = uuid.uuid4()
    app = Application(
        id=app_id,
        user_ref="user_123",
        bank_id="bank_awash",
        tier="standard",
        status=ApplicationStatus.SUBMITTED_TO_BANK,
        idempotency_hash="hash_idem_123",
    )
    sub = BankSubmission(
        id=uuid.uuid4(),
        application_id=app_id,
        bank_id="bank_awash",
        dynamic_fields={"monthly_income_etb": 50000},
    )
    app.submissions = [sub]

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = app
    mock_session.execute.return_value = mock_result

    session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session

    mock_queue = AsyncMock()
    mock_adapter_service = AsyncMock()
    mock_adapter_service.submit.return_value = {
        "status": "ACCOUNT_OPENED",
        "account_number": "100055667788",
        "bank_reference": "AWASH-CBS-REF-11",
    }
    mock_audit = AsyncMock()

    worker = BankSubmissionWorker(
        queue=mock_queue,
        adapter_service=mock_adapter_service,
        audit_service=mock_audit,
        session_factory=session_factory,
    )

    msg = QueueMessage(
        message_id="msg-101",
        application_id=str(app_id),
        bank_id="bank_awash",
        payload={"tier": "standard"},
        idempotency_key="hash_idem_123",
    )

    success = await worker.process_message(msg)

    assert success is True
    assert app.status == ApplicationStatus.ACCOUNT_OPENED
    assert sub.account_number == "100055667788"
    assert sub.bank_reference == "AWASH-CBS-REF-11"
    mock_queue.acknowledge.assert_awaited_once_with("msg-101")
    mock_audit.record_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_message_transient_retry() -> None:
    app_id = uuid.uuid4()
    app = Application(
        id=app_id,
        user_ref="user_123",
        bank_id="bank_awash",
        tier="standard",
        status=ApplicationStatus.SUBMITTED_TO_BANK,
    )
    sub = BankSubmission(
        id=uuid.uuid4(),
        application_id=app_id,
        bank_id="bank_awash",
        dynamic_fields={},
        retry_count=1,
    )
    app.submissions = [sub]

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = app
    mock_session.execute.return_value = mock_result
    session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session

    mock_queue = AsyncMock()
    mock_adapter_service = AsyncMock()
    mock_adapter_service.submit.side_effect = BankCBSUnavailableError("Partner CBS maintenance (503)")
    mock_audit = AsyncMock()

    worker = BankSubmissionWorker(
        queue=mock_queue,
        adapter_service=mock_adapter_service,
        audit_service=mock_audit,
        session_factory=session_factory,
        max_retries=5,
    )

    msg = QueueMessage(
        message_id="msg-102",
        application_id=str(app_id),
        bank_id="bank_awash",
        payload={},
        idempotency_key="idem_1",
    )

    success = await worker.process_message(msg)

    assert success is False
    assert sub.retry_count == 2
    assert app.status == ApplicationStatus.SUBMITTED_TO_BANK
    mock_queue.acknowledge.assert_not_awaited()
    mock_queue.route_to_dlq.assert_not_awaited()
    mock_audit.record_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_message_max_retries_exceeded_dlq() -> None:
    app_id = uuid.uuid4()
    app = Application(
        id=app_id,
        user_ref="user_123",
        bank_id="bank_awash",
        tier="standard",
        status=ApplicationStatus.SUBMITTED_TO_BANK,
    )
    sub = BankSubmission(
        id=uuid.uuid4(),
        application_id=app_id,
        bank_id="bank_awash",
        dynamic_fields={},
        retry_count=5,  # already reached max
    )
    app.submissions = [sub]

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = app
    mock_session.execute.return_value = mock_result
    session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session

    mock_queue = AsyncMock()
    mock_adapter_service = AsyncMock()
    mock_adapter_service.submit.side_effect = BankCBSConnectionError("Connection timed out after 8000ms")
    mock_audit = AsyncMock()

    worker = BankSubmissionWorker(
        queue=mock_queue,
        adapter_service=mock_adapter_service,
        audit_service=mock_audit,
        session_factory=session_factory,
        max_retries=5,
    )

    msg = QueueMessage(
        message_id="msg-103",
        application_id=str(app_id),
        bank_id="bank_awash",
        payload={},
        idempotency_key="idem_2",
    )

    success = await worker.process_message(msg)

    assert success is False
    assert sub.retry_count == 6
    assert app.status == ApplicationStatus.BANK_REJECTED
    mock_queue.route_to_dlq.assert_awaited_once()
    mock_queue.acknowledge.assert_awaited_once_with("msg-103")


@pytest.mark.asyncio
async def test_process_message_permanent_error_dlq() -> None:
    app_id = uuid.uuid4()
    app = Application(
        id=app_id,
        user_ref="user_123",
        bank_id="bank_awash",
        tier="standard",
        status=ApplicationStatus.SUBMITTED_TO_BANK,
    )
    sub = BankSubmission(
        id=uuid.uuid4(),
        application_id=app_id,
        bank_id="bank_awash",
        dynamic_fields={},
        retry_count=0,
    )
    app.submissions = [sub]

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = app
    mock_session.execute.return_value = mock_result
    session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session

    mock_queue = AsyncMock()
    mock_adapter_service = AsyncMock()
    mock_adapter_service.submit.side_effect = BankCBSPayloadError("Blacklisted identity", status_code=403)
    mock_audit = AsyncMock()

    worker = BankSubmissionWorker(
        queue=mock_queue,
        adapter_service=mock_adapter_service,
        audit_service=mock_audit,
        session_factory=session_factory,
    )

    msg = QueueMessage(
        message_id="msg-104",
        application_id=str(app_id),
        bank_id="bank_awash",
        payload={},
        idempotency_key="idem_3",
    )

    success = await worker.process_message(msg)

    assert success is False
    assert app.status == ApplicationStatus.BANK_REJECTED
    mock_queue.route_to_dlq.assert_awaited_once()
    mock_queue.acknowledge.assert_awaited_once_with("msg-104")


@pytest.mark.asyncio
async def test_process_message_invalid_uuid() -> None:
    mock_queue = AsyncMock()
    worker = BankSubmissionWorker(queue=mock_queue)

    msg = QueueMessage(
        message_id="msg-err-1",
        application_id="not-a-valid-uuid",
        bank_id="bank_awash",
        payload={},
        idempotency_key="idem_err",
    )

    success = await worker.process_message(msg)

    assert success is False
    mock_queue.route_to_dlq.assert_awaited_once()
    mock_queue.acknowledge.assert_awaited_once_with("msg-err-1")


@pytest.mark.asyncio
async def test_process_message_app_not_found() -> None:
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session

    mock_queue = AsyncMock()
    worker = BankSubmissionWorker(queue=mock_queue, session_factory=session_factory)

    valid_uuid = str(uuid.uuid4())
    msg = QueueMessage(
        message_id="msg-err-2",
        application_id=valid_uuid,
        bank_id="bank_awash",
        payload={},
        idempotency_key="idem_err_2",
    )

    success = await worker.process_message(msg)

    assert success is False
    mock_queue.route_to_dlq.assert_awaited_once()
    mock_queue.acknowledge.assert_awaited_once_with("msg-err-2")


@pytest.mark.asyncio
async def test_process_message_already_opened() -> None:
    app_id = uuid.uuid4()
    app = Application(
        id=app_id,
        user_ref="user_123",
        bank_id="bank_awash",
        tier="standard",
        status=ApplicationStatus.ACCOUNT_OPENED,
    )
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = app
    mock_session.execute.return_value = mock_result
    session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session

    mock_queue = AsyncMock()
    worker = BankSubmissionWorker(queue=mock_queue, session_factory=session_factory)

    msg = QueueMessage(
        message_id="msg-already-opened",
        application_id=str(app_id),
        bank_id="bank_awash",
        payload={},
        idempotency_key="idem_already",
    )

    success = await worker.process_message(msg)

    assert success is True
    mock_queue.acknowledge.assert_awaited_once_with("msg-already-opened")


@pytest.mark.asyncio
async def test_process_message_unexpected_error() -> None:
    app_id = uuid.uuid4()
    app = Application(
        id=app_id,
        user_ref="user_123",
        bank_id="bank_awash",
        tier="standard",
        status=ApplicationStatus.SUBMITTED_TO_BANK,
    )
    sub = BankSubmission(
        id=uuid.uuid4(),
        application_id=app_id,
        bank_id="bank_awash",
        dynamic_fields={},
        retry_count=0,
    )
    app.submissions = [sub]

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = app
    mock_session.execute.return_value = mock_result
    session_factory = MagicMock(return_value=mock_session)
    mock_session.__aenter__.return_value = mock_session

    mock_queue = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.submit.side_effect = RuntimeError("Fatal hardware failure")

    worker = BankSubmissionWorker(
        queue=mock_queue,
        adapter_service=mock_adapter,
        session_factory=session_factory,
    )

    msg = QueueMessage(
        message_id="msg-unhandled",
        application_id=str(app_id),
        bank_id="bank_awash",
        payload={},
        idempotency_key="idem_unhandled",
    )

    success = await worker.process_message(msg)

    assert success is False
    assert sub.retry_count == 1
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_run_and_stop_lifecycle() -> None:
    mock_queue = AsyncMock()
    mock_queue.dequeue.return_value = []
    mock_redis = AsyncMock()

    worker = BankSubmissionWorker(
        queue=mock_queue,
        redis_client=mock_redis,
        heartbeat_interval=0.05,
    )

    run_task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.08)

    assert worker._running is True
    worker.stop()
    await run_task
    assert worker._running is False
    mock_redis.set.assert_awaited()


@pytest.mark.asyncio
async def test_worker_main_entrypoint() -> None:
    from src.workers.bank_submission import main

    with patch("src.workers.bank_submission.BankSubmissionWorker") as MockWorkerClass:
        mock_instance = AsyncMock()
        mock_instance.stop = MagicMock()
        mock_instance.redis = AsyncMock()
        mock_instance.run.return_value = None
        MockWorkerClass.return_value = mock_instance

        await main()

        mock_instance.run.assert_awaited_once()
        mock_instance.redis.aclose.assert_awaited_once()
