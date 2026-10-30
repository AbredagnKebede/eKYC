import os
import uuid
import pytest
import redis.asyncio as aioredis

from src.events.application_submitted import (
    ApplicationSubmittedEvent,
    ApplicationStatusUpdatedEvent,
)
from src.infrastructure.queue import SubmissionQueue


@pytest.mark.asyncio
async def test_real_redis_submission_event_publish_and_consume() -> None:
    # Real queue boundary verification using live Redis
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    assert redis_url.startswith("redis://")

    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    stream_name = f"test_event_stream_{uuid.uuid4().hex[:8]}"
    group_name = f"test_event_group_{uuid.uuid4().hex[:8]}"

    queue = SubmissionQueue(
        redis_client=redis_client,
        stream_name=stream_name,
        group_name=group_name,
    )

    try:
        secret_key = "test-event-signing-hmac-key"
        app_id = str(uuid.uuid4())

        # 1. Create and sign ApplicationSubmittedEvent
        event = ApplicationSubmittedEvent.create(
            application_id=app_id,
            bank_id="bank_awash",
            secret_key=secret_key,
            tier="standard",
            dynamic_fields={
                "monthly_income_etb": 32000,
                "occupation": "Software Engineer",
                "source_of_funds": "Salary",
            },
        )
        assert event.application_id == app_id
        assert event.verify_signature(secret_key) is True

        # 2. Publish to live Redis stream via SubmissionQueue
        msg_id = await queue.enqueue(
            application_id=event.application_id,
            bank_id=event.bank_id,
            payload=event.model_dump(),
            idempotency_key=event.idempotency_key,
        )
        assert "-" in msg_id

        # 3. Dequeue and validate message contract
        messages = await queue.dequeue(consumer_name="event-consumer-1", count=1)
        assert len(messages) == 1
        queue_msg = messages[0]
        assert queue_msg.message_id == msg_id

        # Reconstruct ApplicationSubmittedEvent from consumed queue payload
        consumed_event = ApplicationSubmittedEvent.model_validate(queue_msg.payload)
        assert consumed_event.event_name == "application_submitted_event"
        assert consumed_event.application_id == app_id
        assert consumed_event.bank_id == "bank_awash"
        assert consumed_event.tier == "standard"
        assert consumed_event.dynamic_fields["monthly_income_etb"] == 32000

        # Verify signature on consumed event
        assert consumed_event.verify_signature(secret_key) is True

        # 4. Acknowledge message
        ack_res = await queue.acknowledge(queue_msg.message_id)
        assert ack_res == 1

    finally:
        await redis_client.delete(stream_name)
        await redis_client.aclose()
