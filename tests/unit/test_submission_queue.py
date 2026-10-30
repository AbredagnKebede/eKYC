import json
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.infrastructure.queue import (
    DEFAULT_MAX_RETRIES,
    QueueError,
    QueueMessage,
    QueueMessageSerializationError,
    SubmissionQueue,
)


def test_queue_message_serialization_and_deserialization() -> None:
    msg = QueueMessage(
        message_id="1672531199000-0",
        application_id="app_test_123",
        bank_id="bank_awash",
        payload={"tier": "standard", "full_name": "Tesfaye Abebe"},
        idempotency_key="idem_key_999",
        retry_count=1,
        max_retries=5,
    )

    redis_dict = msg.to_redis_dict()
    assert redis_dict["application_id"] == "app_test_123"
    assert redis_dict["bank_id"] == "bank_awash"
    assert redis_dict["idempotency_key"] == "idem_key_999"
    assert redis_dict["retry_count"] == "1"
    assert redis_dict["max_retries"] == "5"

    parsed_payload = json.loads(redis_dict["payload"])
    assert parsed_payload["full_name"] == "Tesfaye Abebe"
    assert parsed_payload["tier"] == "standard"

    # Deserialize back
    recovered = QueueMessage.from_redis_dict("1672531199000-0", redis_dict)
    assert recovered.message_id == "1672531199000-0"
    assert recovered.application_id == "app_test_123"
    assert recovered.bank_id == "bank_awash"
    assert recovered.retry_count == 1
    assert recovered.max_retries == 5
    assert recovered.payload["tier"] == "standard"
    assert recovered.idempotency_key == "idem_key_999"


def test_queue_message_serialization_errors() -> None:
    # Non-serializable object in payload
    class UnserializableObj:
        pass

    bad_msg = QueueMessage(
        message_id="1",
        application_id="app_1",
        bank_id="bank_1",
        payload={"bad": UnserializableObj()},
        idempotency_key="k",
    )
    with pytest.raises(QueueMessageSerializationError) as exc_ser:
        bad_msg.to_redis_dict()
    assert "Failed to serialize message" in str(exc_ser.value)

    # Deserializing corrupt JSON
    corrupt_data = {
        "application_id": "app_1",
        "bank_id": "bank_1",
        "payload": "not-valid-json{{{",
        "idempotency_key": "k",
    }
    with pytest.raises(QueueMessageSerializationError) as exc_deser:
        QueueMessage.from_redis_dict("1", corrupt_data)
    assert "Failed to deserialize queue entry" in str(exc_deser.value)


@pytest.mark.asyncio
async def test_submission_queue_validation_and_idempotency_unit() -> None:
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.xadd = AsyncMock(return_value="1670000000000-0")

    queue = SubmissionQueue(redis_client=mock_redis)

    # 1. Missing application_id or bank_id
    with pytest.raises(QueueError) as exc_val1:
        await queue.enqueue("", "bank_awash", {"data": 1})
    assert "application_id and bank_id are mandatory" in str(exc_val1.value)

    with pytest.raises(QueueError) as exc_val2:
        await queue.enqueue("app_1", "", {"data": 1})
    assert "application_id and bank_id are mandatory" in str(exc_val2.value)

    # 2. Enqueue fresh message
    msg_id = await queue.enqueue("app_1", "bank_awash", {"amount": 100}, idempotency_key="key_1")
    assert msg_id == "1670000000000-0"
    mock_redis.xadd.assert_awaited_once()

    # 3. Duplicate enqueue returns cached message ID without xadd
    mock_redis.get = AsyncMock(return_value="1670000000000-0")
    mock_redis.xadd.reset_mock()

    cached_id = await queue.enqueue("app_1", "bank_awash", {"amount": 100}, idempotency_key="key_1")
    assert cached_id == "1670000000000-0"
    mock_redis.xadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_submission_queue_dequeue_and_ack_unit() -> None:
    mock_redis = MagicMock()
    mock_redis.xgroup_create = AsyncMock(return_value=True)
    mock_redis.xreadgroup = AsyncMock(return_value=[
        (
            "bank_submission_queue",
            [
                (
                    "msg_id_1",
                    {
                        "application_id": "app_unit_1",
                        "bank_id": "bank_awash",
                        "payload": json.dumps({"tier": "standard"}),
                        "idempotency_key": "idem_1",
                        "retry_count": "0",
                        "max_retries": "3",
                    },
                ),
            ],
        ),
    ])
    mock_redis.xack = AsyncMock(return_value=1)

    queue = SubmissionQueue(redis_client=mock_redis)
    messages = await queue.dequeue()
    assert len(messages) == 1
    m = messages[0]
    assert m.message_id == "msg_id_1"
    assert m.application_id == "app_unit_1"
    assert m.bank_id == "bank_awash"
    assert m.payload["tier"] == "standard"

    ack_res = await queue.acknowledge("msg_id_1")
    assert ack_res == 1
    mock_redis.xack.assert_awaited_once_with("bank_submission_queue", "bank_submission_workers", "msg_id_1")


@pytest.mark.asyncio
async def test_submission_queue_route_to_dlq_unit() -> None:
    mock_redis = MagicMock()
    mock_redis.xadd = AsyncMock(return_value="dlq_msg_id_99")
    mock_redis.xack = AsyncMock(return_value=1)

    queue = SubmissionQueue(redis_client=mock_redis)
    msg = QueueMessage(
        message_id="orig_msg_1",
        application_id="app_poison_1",
        bank_id="bank_awash",
        payload={"tier": "unknown"},
        idempotency_key="key_poison",
        retry_count=2,
    )

    dlq_id = await queue.route_to_dlq(msg, reason="HTTP 500 CBS Crash")
    assert dlq_id == "dlq_msg_id_99"
    assert msg.retry_count == 3
    assert msg.error_message == "HTTP 500 CBS Crash"
    mock_redis.xadd.assert_awaited_once()
    mock_redis.xack.assert_awaited_once_with("bank_submission_queue", "bank_submission_workers", "orig_msg_1")
