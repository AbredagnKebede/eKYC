import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import redis.asyncio as aioredis
from src.infrastructure.redis import get_redis_client

DEFAULT_STREAM_NAME = "bank_submission_queue"
DEFAULT_DLQ_NAME = "bank_submission_dlq"
DEFAULT_GROUP_NAME = "bank_submission_workers"
DEFAULT_CONSUMER_NAME = "worker-1"
DEFAULT_MAX_RETRIES = 3


class QueueError(Exception):
    """Base exception for queue operations."""
    pass


class QueueMessageSerializationError(QueueError):
    """Raised when message cannot be serialized or deserialized."""
    pass


@dataclass
class QueueMessage:
    """Standard queue envelope for bank submission messages."""

    message_id: str
    application_id: str
    bank_id: str
    payload: Dict[str, Any]
    idempotency_key: str
    retry_count: int = 0
    max_retries: int = DEFAULT_MAX_RETRIES
    created_at: str = ""
    error_message: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_redis_dict(self) -> Dict[str, str]:
        """Serializes envelope into string mapping suitable for Redis Streams."""
        try:
            return {
                "application_id": str(self.application_id),
                "bank_id": str(self.bank_id),
                "payload": json.dumps(self.payload),
                "idempotency_key": str(self.idempotency_key),
                "retry_count": str(self.retry_count),
                "max_retries": str(self.max_retries),
                "created_at": str(self.created_at),
                "error_message": str(self.error_message or ""),
            }
        except (TypeError, ValueError) as exc:
            raise QueueMessageSerializationError(f"Failed to serialize message: {exc}") from exc

    @classmethod
    def from_redis_dict(cls, message_id: str, data: Dict[str, Any]) -> "QueueMessage":
        """Deserializes Redis stream entry mapping into a QueueMessage."""
        try:
            raw_payload = data.get("payload", "{}")
            payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload

            return cls(
                message_id=str(message_id),
                application_id=str(data.get("application_id", "")),
                bank_id=str(data.get("bank_id", "")),
                payload=payload,
                idempotency_key=str(data.get("idempotency_key", "")),
                retry_count=int(data.get("retry_count", 0)),
                max_retries=int(data.get("max_retries", DEFAULT_MAX_RETRIES)),
                created_at=str(data.get("created_at", "")),
                error_message=str(data.get("error_message")) if data.get("error_message") else None,
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise QueueMessageSerializationError(f"Failed to deserialize queue entry: {exc}") from exc


class SubmissionQueue:
    """Persistent message queue transport backed by Redis Streams."""

    def __init__(
        self,
        redis_client: Optional[aioredis.Redis] = None,
        stream_name: str = DEFAULT_STREAM_NAME,
        dlq_name: str = DEFAULT_DLQ_NAME,
        group_name: str = DEFAULT_GROUP_NAME,
    ) -> None:
        self.redis = redis_client or get_redis_client()
        self.stream_name = stream_name
        self.dlq_name = dlq_name
        self.group_name = group_name

    async def ensure_consumer_group(
        self,
        stream_name: Optional[str] = None,
        group_name: Optional[str] = None,
    ) -> None:
        """Creates consumer group on the stream if it does not already exist."""
        s_name = stream_name or self.stream_name
        g_name = group_name or self.group_name
        try:
            await self.redis.xgroup_create(s_name, g_name, id="0", mkstream=True)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise QueueError(f"Failed to create consumer group: {exc}") from exc

    async def enqueue(
        self,
        application_id: str,
        bank_id: str,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        stream_name: Optional[str] = None,
    ) -> str:
        """Publishes an application submission message to the Redis stream."""
        if not application_id or not bank_id:
            raise QueueError("application_id and bank_id are mandatory for queue message.")

        s_name = stream_name or self.stream_name
        idem_key = idempotency_key or f"idem_{application_id}_{bank_id}"

        # Idempotency check: prevent duplicate enqueue of same task within 1 hour
        dedup_key = f"queue:dedup:{idem_key}"
        existing_msg_id = await self.redis.get(dedup_key)
        if existing_msg_id:
            return str(existing_msg_id)

        msg = QueueMessage(
            message_id="",  # assigned by Redis
            application_id=str(application_id),
            bank_id=str(bank_id),
            payload=payload,
            idempotency_key=idem_key,
            max_retries=max_retries,
        )

        stream_data = msg.to_redis_dict()
        message_id = await self.redis.xadd(s_name, stream_data)
        str_msg_id = str(message_id)

        # Cache dedup key for 3600 seconds
        await self.redis.set(dedup_key, str_msg_id, ex=3600)
        return str_msg_id

    async def dequeue(
        self,
        consumer_name: str = DEFAULT_CONSUMER_NAME,
        count: int = 1,
        block_ms: int = 1000,
        stream_name: Optional[str] = None,
        group_name: Optional[str] = None,
    ) -> List[QueueMessage]:
        """Consumes unacknowledged messages from consumer group."""
        s_name = stream_name or self.stream_name
        g_name = group_name or self.group_name

        await self.ensure_consumer_group(s_name, g_name)

        entries = await self.redis.xreadgroup(
            groupname=g_name,
            consumername=consumer_name,
            streams={s_name: ">"},
            count=count,
            block=block_ms,
        )

        # If no new messages, check pending entries list (PEL) for unacknowledged retries
        if not entries or not entries[0][1]:
            entries = await self.redis.xreadgroup(
                groupname=g_name,
                consumername=consumer_name,
                streams={s_name: "0"},
                count=count,
            )

        # If still no messages, autoclaim any abandoned messages idle for > 1000ms
        if not entries or not entries[0][1]:
            try:
                claim_res = await self.redis.xautoclaim(
                    name=s_name,
                    groupname=g_name,
                    consumername=consumer_name,
                    min_idle_time=1000,
                    count=count,
                )
                if claim_res and len(claim_res) > 1 and claim_res[1]:
                    entries = [(s_name, claim_res[1])]
            except Exception:
                pass

        messages: List[QueueMessage] = []
        if not entries:
            return messages

        for stream, stream_messages in entries:
            for msg_id, raw_data in stream_messages:
                messages.append(QueueMessage.from_redis_dict(msg_id, raw_data))

        return messages

    async def acknowledge(
        self,
        message_id: str,
        stream_name: Optional[str] = None,
        group_name: Optional[str] = None,
    ) -> int:
        """Acknowledges successful processing of a message."""
        s_name = stream_name or self.stream_name
        g_name = group_name or self.group_name
        return await self.redis.xack(s_name, g_name, message_id)

    async def route_to_dlq(
        self,
        message: QueueMessage,
        reason: str,
        stream_name: Optional[str] = None,
        dlq_name: Optional[str] = None,
        group_name: Optional[str] = None,
    ) -> str:
        """Moves a poison or max-retry exhausted message to Dead Letter Queue."""
        s_name = stream_name or self.stream_name
        d_name = dlq_name or self.dlq_name
        g_name = group_name or self.group_name

        # Increment retry count and append error
        message.retry_count += 1
        message.error_message = reason

        dlq_data = message.to_redis_dict()
        dlq_data["failed_at"] = datetime.now(timezone.utc).isoformat()
        dlq_data["original_stream"] = s_name

        dlq_msg_id = await self.redis.xadd(d_name, dlq_data)

        # Acknowledge in original queue so worker does not re-process
        if message.message_id:
            await self.acknowledge(message.message_id, stream_name=s_name, group_name=g_name)

        return str(dlq_msg_id)

    async def get_stream_length(self, stream_name: Optional[str] = None) -> int:
        """Returns count of entries in the stream."""
        s_name = stream_name or self.stream_name
        return await self.redis.xlen(s_name)

    async def read_dlq(self, count: int = 10, dlq_name: Optional[str] = None) -> List[QueueMessage]:
        """Inspects dead letter queue contents."""
        d_name = dlq_name or self.dlq_name
        raw_entries = await self.redis.xrange(d_name, count=count)
        return [QueueMessage.from_redis_dict(msg_id, data) for msg_id, data in raw_entries]
