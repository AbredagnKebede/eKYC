import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        nullable=True, index=True
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_log_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hmac_signature: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("idx_audit_chain", "id", "prev_log_hash"),
    )
