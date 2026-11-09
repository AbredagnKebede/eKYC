"""Bank portal settings, staff RBAC, and passport identity persistence."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models.application import utc_now
from src.models.base import Base


class BankStaffRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    EMPLOYEE = "EMPLOYEE"


class BankSettings(Base):
    __tablename__ = "bank_settings"

    bank_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ff_outbound: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ff_inbound: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    def __init__(self, **kwargs: Any) -> None:
        if "ff_outbound" not in kwargs:
            kwargs["ff_outbound"] = True
        if "ff_inbound" not in kwargs:
            kwargs["ff_inbound"] = True
        if "updated_at" not in kwargs:
            kwargs["updated_at"] = utc_now()
        super().__init__(**kwargs)


class BankStaff(Base):
    __tablename__ = "bank_staff"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    bank_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[BankStaffRole] = mapped_column(
        Enum(BankStaffRole, name="bank_staff_role_enum"),
        nullable=False,
        default=BankStaffRole.EMPLOYEE,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("bank_id", "email", name="uq_bank_staff_bank_email"),
        Index("idx_bank_staff_bank_role", "bank_id", "role"),
    )

    def __init__(self, **kwargs: Any) -> None:
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "role" not in kwargs:
            kwargs["role"] = BankStaffRole.EMPLOYEE
        if "active" not in kwargs:
            kwargs["active"] = True
        if "created_at" not in kwargs:
            kwargs["created_at"] = utc_now()
        super().__init__(**kwargs)


class PassportIdentity(Base):
    """Fayda-bound passport profile for a device."""

    __tablename__ = "passport_identities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fayda_ref_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_ref: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    device_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("fayda_ref_hash", "device_fingerprint", name="uq_passport_fayda_device"),
    )

    def __init__(self, **kwargs: Any) -> None:
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        now = utc_now()
        if "created_at" not in kwargs:
            kwargs["created_at"] = now
        if "last_seen_at" not in kwargs:
            kwargs["last_seen_at"] = now
        super().__init__(**kwargs)
