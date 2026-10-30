import os
import uuid
import pytest
import redis.asyncio as aioredis

from src.infrastructure.queue import (
    QueueMessage,
    SubmissionQueue,
)


@pytest.mark.asyncio
async def test_real_redis_submission_queue_lifecycle() -> None:
    # Real queue boundary verification using live Redis
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    assert redis_url.startswith("redis://")

    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    stream_name = f"test_stream_{uuid.uuid4().hex[:8]}"
    dlq_name = f"test_dlq_{uuid.uuid4().hex[:8]}"
    group_name = f"test_group_{uuid.uuid4().hex[:8]}"

    queue = SubmissionQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        dlq_name=dlq_name,
        group_name=group_name,
    )

    try:
        # 1. Enqueue message
        app_id = str(uuid.uuid4())
        idem_key = f"idem_real_{app_id}"
        payload = {
            "tier": "standard",
            "full_name": "Almaz Ayana",
            "income": 45000,
        }

        msg_id1 = await queue.enqueue(
            application_id=app_id,
            bank_id="bank_awash",
            payload=payload,
            idempotency_key=idem_key,
        )
        assert "-" in msg_id1
        stream_len = await queue.get_stream_length()
        assert stream_len == 1

        # 2. Idempotency test: duplicate enqueue with same idempotency key returns identical msg_id
        msg_id2 = await queue.enqueue(
            application_id=app_id,
            bank_id="bank_awash",
            payload=payload,
            idempotency_key=idem_key,
        )
        assert msg_id2 == msg_id1
        # Stream length must still be 1 (no duplicate message created)
        assert await queue.get_stream_length() == 1

        # 3. Dequeue message via consumer group
        messages = await queue.dequeue(consumer_name="integration-worker-1", count=1)
        assert len(messages) == 1
        msg = messages[0]
        assert msg.message_id == msg_id1
        assert msg.application_id == app_id
        assert msg.bank_id == "bank_awash"
        assert msg.payload["full_name"] == "Almaz Ayana"
        assert msg.payload["income"] == 45000

        # 4. Acknowledge message
        ack_res = await queue.acknowledge(msg.message_id)
        assert ack_res == 1

        # Subsequent dequeue yields no more pending new messages
        empty_batch = await queue.dequeue(consumer_name="integration-worker-1", count=1, block_ms=200)
        assert len(empty_batch) == 0

        # 5. Route poison message to DLQ
        poison_id = await queue.enqueue(
            application_id="app_poison_real",
            bank_id="bank_awash",
            payload={"corrupt": True},
        )
        poison_msgs = await queue.dequeue(consumer_name="integration-worker-1", count=1)
        assert len(poison_msgs) == 1
        poison_msg = poison_msgs[0]

        dlq_id = await queue.route_to_dlq(poison_msg, reason="Simulated CBS Timeout 504")
        assert "-" in dlq_id

        # Inspect DLQ
        dlq_items = await queue.read_dlq(count=5)
        assert len(dlq_items) == 1
        dlq_item = dlq_items[0]
        assert dlq_item.application_id == "app_poison_real"
        assert dlq_item.retry_count == 1
        assert dlq_item.error_message == "Simulated CBS Timeout 504"

    finally:
        # Cleanup test streams
        await redis_client.delete(stream_name, dlq_name)
        await redis_client.aclose()
