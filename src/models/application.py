import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class ApplicationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CONSENTED = "CONSENTED"
    ID_VERIFIED = "ID_VERIFIED"
    ID_FAILED = "ID_FAILED"
    LIVENESS_PASSED = "LIVENESS_PASSED"
    LIVENESS_FAILED = "LIVENESS_FAILED"
    DATA_COMPLETE = "DATA_COMPLETE"
    SUBMITTED_TO_BANK = "SUBMITTED_TO_BANK"
    BANK_ACCEPTED = "BANK_ACCEPTED"
    BANK_REJECTED = "BANK_REJECTED"
    ACCOUNT_OPENED = "ACCOUNT_OPENED"
    ACTIVATED = "ACTIVATED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class VerificationMethod(str, enum.Enum):
    OTP = "OTP"
    BIOMETRIC = "BIOMETRIC"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_ref: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    bank_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(32), default="standard", nullable=False)
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, name="application_status_enum"),
        default=ApplicationStatus.DRAFT,
        nullable=False,
        index=True,
    )
    idempotency_hash: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Relationships
    identity_snapshot: Mapped[Optional["IdentitySnapshot"]] = relationship(
        "IdentitySnapshot", back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
    consents: Mapped[list["ConsentRecord"]] = relationship(
        "ConsentRecord", back_populates="application", cascade="all, delete-orphan"
    )
    submissions: Mapped[list["BankSubmission"]] = relationship(
        "BankSubmission", back_populates="application", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_app_bank_status", "bank_id", "status"),
    )

    def __init__(self, **kwargs: Any) -> None:
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "tier" not in kwargs:
            kwargs["tier"] = "standard"
        if "status" not in kwargs:
            kwargs["status"] = ApplicationStatus.DRAFT
        if "created_at" not in kwargs:
            kwargs["created_at"] = utc_now()
        if "updated_at" not in kwargs:
            kwargs["updated_at"] = utc_now()
        super().__init__(**kwargs)


class IdentitySnapshot(Base):
    __tablename__ = "identity_snapshots"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    encrypted_full_name: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encrypted_dob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    gender: Mapped[str] = mapped_column(String(16), nullable=False)
    fayda_ref_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    liveness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    verification_method: Mapped[VerificationMethod] = mapped_column(
        Enum(VerificationMethod, name="verification_method_enum"),
        default=VerificationMethod.OTP,
        nullable=False,
    )

    application: Mapped["Application"] = relationship(
        "Application", back_populates="identity_snapshot"
    )


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    consent_version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    device_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)

    application: Mapped["Application"] = relationship(
        "Application", back_populates="consents"
    )


class BankSubmission(Base):
    __tablename__ = "bank_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bank_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dynamic_fields: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    bank_reference: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    account_number: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )
    bank_status: Mapped[Optional[str]] = mapped_column(
        String(32), default="pending", nullable=True, index=True
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    application: Mapped["Application"] = relationship(
        "Application", back_populates="submissions"
    )

    @property
    def last_error(self) -> Optional[str]:
        return self.error_message

    def __init__(self, **kwargs: Any) -> None:
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "bank_status" not in kwargs:
            kwargs["bank_status"] = "pending"
        if "retry_count" not in kwargs:
            kwargs["retry_count"] = 0
        if "sent_at" not in kwargs:
            kwargs["sent_at"] = utc_now()
        if "last_attempt_at" not in kwargs:
            kwargs["last_attempt_at"] = utc_now()
        if "dynamic_fields" not in kwargs:
            kwargs["dynamic_fields"] = {}
        super().__init__(**kwargs)
