"""Bank portal settings, staff RBAC, partner catalog, and passport identity."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import Boolean, DateTime, Enum, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.application import utc_now
from src.models.base import Base


class BankStaffRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    EMPLOYEE = "EMPLOYEE"


class PartnerBank(Base):
    """Persisted partner bank catalogue (source of truth for mobile + portals)."""

    __tablename__ = "partner_banks"

    bank_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bank_name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_code: Mapped[str] = mapped_column(String(32), nullable=False)
    hq_city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    supported_tiers: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    use_legacy_awash: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    def __init__(self, **kwargs: Any) -> None:
        if "supported_tiers" not in kwargs:
            kwargs["supported_tiers"] = ["standard"]
        if "use_legacy_awash" not in kwargs:
            kwargs["use_legacy_awash"] = False
        if "active" not in kwargs:
            kwargs["active"] = True
        now = utc_now()
        if "created_at" not in kwargs:
            kwargs["created_at"] = now
        if "updated_at" not in kwargs:
            kwargs["updated_at"] = now
        super().__init__(**kwargs)


class PlatformOperator(Base):
    """Fayda/eKYC platform operator who onboards bank customers."""

    __tablename__ = "platform_operators"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    def __init__(self, **kwargs: Any) -> None:
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "active" not in kwargs:
            kwargs["active"] = True
        if "created_at" not in kwargs:
            kwargs["created_at"] = utc_now()
        super().__init__(**kwargs)


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
