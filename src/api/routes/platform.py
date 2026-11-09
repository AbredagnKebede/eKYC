"""Platform operator APIs: onboard banks, issue Super Admin credentials."""
from __future__ import annotations

import os
import re
import secrets
import string
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware import create_access_token
from src.api.platform_auth import require_platform_auth
from src.models.application import utc_now
from src.models.bank_portal import BankSettings, BankStaff, BankStaffRole, PartnerBank, PlatformOperator
from src.models.base import get_db_session
from src.security.passwords import hash_password, verify_password
from src.services.audit import AuditService
from src.services.partner_catalog import list_partner_bank_rows

router = APIRouter(prefix="/v1/platform", tags=["Platform"])
_audit = AuditService()

PLATFORM_TOKEN_MINUTES = int(os.getenv("PLATFORM_TOKEN_MINUTES", "480"))
_BANK_ID_RE = re.compile(r"^bank_[a-z0-9_]{2,48}$")


class PlatformLoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)


class PlatformLoginResponse(BaseModel):
    token: str
    email: str
    role: str
    expires_in: int


class PartnerBankOut(BaseModel):
    bank_id: str
    bank_name: str
    short_code: str
    hq_city: Optional[str] = None
    supported_tiers: List[str]
    active: bool
    use_legacy_awash: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CreateBankRequest(BaseModel):
    bank_id: str = Field(..., min_length=6, max_length=64)
    bank_name: str = Field(..., min_length=2, max_length=255)
    short_code: str = Field(..., min_length=2, max_length=32)
    hq_city: Optional[str] = Field(default="Addis Ababa", max_length=128)
    supported_tiers: List[str] = Field(default_factory=lambda: ["standard", "diaspora"])
    super_admin_email: Optional[str] = Field(default=None, max_length=255)


class CreateBankResponse(BaseModel):
    bank: PartnerBankOut
    super_admin_email: str
    temporary_password: str


class PatchBankRequest(BaseModel):
    bank_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    short_code: Optional[str] = Field(default=None, min_length=2, max_length=32)
    hq_city: Optional[str] = Field(default=None, max_length=128)
    supported_tiers: Optional[List[str]] = None
    active: Optional[bool] = None


class ResetSuperAdminRequest(BaseModel):
    confirm: bool = Field(..., description="Must be true to rotate credentials")
    email: Optional[str] = None


class ResetSuperAdminResponse(BaseModel):
    bank_id: str
    super_admin_email: str
    temporary_password: str


def _random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    # Ensure mixed classes for bank portal min-length rules.
    return (
        secrets.choice(string.ascii_uppercase)
        + secrets.choice(string.ascii_lowercase)
        + secrets.choice(string.digits)
        + "".join(secrets.choice(alphabet) for _ in range(max(0, length - 3)))
    )


def _row_out(row: PartnerBank) -> PartnerBankOut:
    return PartnerBankOut(
        bank_id=row.bank_id,
        bank_name=row.bank_name,
        short_code=row.short_code,
        hq_city=row.hq_city,
        supported_tiers=list(row.supported_tiers or []),
        active=row.active,
        use_legacy_awash=bool(row.use_legacy_awash),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def bootstrap_platform_operators(session: AsyncSession) -> int:
    """Ensure at least one platform operator from env (dev defaults documented)."""
    existing = (await session.execute(select(PlatformOperator.id).limit(1))).scalar_one_or_none()
    if existing is not None:
        return 0
    email = (os.getenv("PLATFORM_OPERATOR_EMAIL") or "platform@ekyc.local").lower().strip()
    password = os.getenv("PLATFORM_OPERATOR_PASSWORD") or "ChangeMePlatform!1"
    session.add(
        PlatformOperator(
            email=email,
            password_hash=hash_password(password),
            active=True,
        )
    )
    await session.flush()
    return 1


@router.post("/auth/login", response_model=PlatformLoginResponse)
async def platform_login(
    req: PlatformLoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> PlatformLoginResponse:
    email = req.email.lower().strip()
    stmt = select(PlatformOperator).where(
        PlatformOperator.email == email,
        PlatformOperator.active.is_(True),
    )
    op = (await session.execute(stmt)).scalar_one_or_none()
    if op is None or not verify_password(req.password, op.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token(
        user_ref=str(op.id),
        device_fingerprint=f"platform:{op.id}",
        expires_delta=timedelta(minutes=PLATFORM_TOKEN_MINUTES),
        extra_claims={
            "portal_scope": "platform",
            "role": "PLATFORM_OPERATOR",
            "email": op.email,
            "operator_id": str(op.id),
        },
    )
    await _audit.record_event(
        session=session,
        actor_type="PLATFORM",
        actor_id=op.email,
        action="PLATFORM_LOGIN",
        application_id=None,
        payload={"email": op.email},
    )
    await session.commit()
    return PlatformLoginResponse(
        token=token,
        email=op.email,
        role="PLATFORM_OPERATOR",
        expires_in=PLATFORM_TOKEN_MINUTES * 60,
    )


@router.get("/banks", response_model=List[PartnerBankOut])
async def list_all_banks(
    session: AsyncSession = Depends(get_db_session),
    _claims: Dict[str, Any] = Depends(require_platform_auth),
) -> List[PartnerBankOut]:
    rows = await list_partner_bank_rows(session, active_only=False)
    return [_row_out(r) for r in rows]


@router.post("/banks", response_model=CreateBankResponse, status_code=status.HTTP_201_CREATED)
async def create_bank(
    req: CreateBankRequest,
    session: AsyncSession = Depends(get_db_session),
    claims: Dict[str, Any] = Depends(require_platform_auth),
) -> CreateBankResponse:
    bank_id = req.bank_id.strip().lower()
    if not _BANK_ID_RE.match(bank_id):
        raise HTTPException(
            status_code=422,
            detail="bank_id must match bank_[a-z0-9_]{2,48}",
        )
    existing = await session.get(PartnerBank, bank_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Bank '{bank_id}' already exists.")

    tiers = [t.strip().lower() for t in (req.supported_tiers or ["standard"]) if t.strip()]
    if "standard" not in tiers:
        tiers.insert(0, "standard")

    row = PartnerBank(
        bank_id=bank_id,
        bank_name=req.bank_name.strip(),
        short_code=req.short_code.strip().upper(),
        hq_city=(req.hq_city or "Addis Ababa").strip(),
        supported_tiers=tiers,
        use_legacy_awash=False,
        active=True,
    )
    session.add(row)

    settings = await session.get(BankSettings, bank_id)
    if settings is None:
        session.add(BankSettings(bank_id=bank_id, ff_outbound=True, ff_inbound=True))

    admin_email = (req.super_admin_email or f"admin@{bank_id.replace('_', '-')}.local").lower().strip()
    temp_password = _random_password(16)

    staff_stmt = select(BankStaff).where(
        BankStaff.bank_id == bank_id,
        BankStaff.email == admin_email,
    )
    staff = (await session.execute(staff_stmt)).scalar_one_or_none()
    if staff is None:
        session.add(
            BankStaff(
                bank_id=bank_id,
                email=admin_email,
                password_hash=hash_password(temp_password),
                role=BankStaffRole.SUPER_ADMIN,
                active=True,
                created_by=claims.get("email"),
            )
        )
    else:
        staff.password_hash = hash_password(temp_password)
        staff.role = BankStaffRole.SUPER_ADMIN
        staff.active = True

    await _audit.record_event(
        session=session,
        actor_type="PLATFORM",
        actor_id=str(claims.get("email")),
        action="PLATFORM_BANK_ONBOARDED",
        application_id=None,
        payload={
            "bank_id": bank_id,
            "bank_name": row.bank_name,
            "super_admin_email": admin_email,
        },
    )
    await session.commit()
    await session.refresh(row)

    # Hot-reload public adapter registry.
    from src.api.routes.banks import refresh_bank_registry

    await refresh_bank_registry(session)

    return CreateBankResponse(
        bank=_row_out(row),
        super_admin_email=admin_email,
        temporary_password=temp_password,
    )


@router.patch("/banks/{bank_id}", response_model=PartnerBankOut)
async def patch_bank(
    bank_id: str,
    req: PatchBankRequest,
    session: AsyncSession = Depends(get_db_session),
    claims: Dict[str, Any] = Depends(require_platform_auth),
) -> PartnerBankOut:
    row = await session.get(PartnerBank, bank_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Bank '{bank_id}' not found.")

    if req.bank_name is not None:
        row.bank_name = req.bank_name.strip()
    if req.short_code is not None:
        row.short_code = req.short_code.strip().upper()
    if req.hq_city is not None:
        row.hq_city = req.hq_city.strip()
    if req.supported_tiers is not None:
        tiers = [t.strip().lower() for t in req.supported_tiers if t.strip()]
        if "standard" not in tiers:
            tiers.insert(0, "standard")
        row.supported_tiers = tiers
    if req.active is not None:
        row.active = req.active
    row.updated_at = utc_now()

    await _audit.record_event(
        session=session,
        actor_type="PLATFORM",
        actor_id=str(claims.get("email")),
        action="PLATFORM_BANK_UPDATED",
        application_id=None,
        payload={
            "bank_id": bank_id,
            "active": row.active,
            "bank_name": row.bank_name,
        },
    )
    await session.commit()
    await session.refresh(row)
    from src.api.routes.banks import refresh_bank_registry

    await refresh_bank_registry(session)
    return _row_out(row)


@router.post("/banks/{bank_id}/reset-super-admin", response_model=ResetSuperAdminResponse)
async def reset_super_admin(
    bank_id: str,
    req: ResetSuperAdminRequest,
    session: AsyncSession = Depends(get_db_session),
    claims: Dict[str, Any] = Depends(require_platform_auth),
) -> ResetSuperAdminResponse:
    if not req.confirm:
        raise HTTPException(status_code=400, detail="confirm must be true.")

    row = await session.get(PartnerBank, bank_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Bank '{bank_id}' not found.")

    email = (req.email or f"admin@{bank_id.replace('_', '-')}.local").lower().strip()
    temp_password = _random_password(16)

    stmt = select(BankStaff).where(
        BankStaff.bank_id == bank_id,
        BankStaff.role == BankStaffRole.SUPER_ADMIN,
    )
    staff = (await session.execute(stmt)).scalars().first()
    if staff is None:
        staff = BankStaff(
            bank_id=bank_id,
            email=email,
            password_hash=hash_password(temp_password),
            role=BankStaffRole.SUPER_ADMIN,
            active=True,
            created_by=claims.get("email"),
        )
        session.add(staff)
    else:
        if req.email:
            staff.email = email
        staff.password_hash = hash_password(temp_password)
        staff.active = True
        staff.role = BankStaffRole.SUPER_ADMIN

    await _audit.record_event(
        session=session,
        actor_type="PLATFORM",
        actor_id=str(claims.get("email")),
        action="PLATFORM_SUPER_RESET",
        application_id=None,
        payload={"bank_id": bank_id, "super_admin_email": staff.email},
    )
    await session.commit()
    return ResetSuperAdminResponse(
        bank_id=bank_id,
        super_admin_email=staff.email,
        temporary_password=temp_password,
    )
