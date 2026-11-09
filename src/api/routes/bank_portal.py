"""Per-bank management portal API with Super Admin / Admin / Employee RBAC."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware import create_access_token, decode_access_token
from src.api.routes.applications import get_onboarding_service
from src.models.application import ApplicationStatus
from src.models.bank_portal import BankStaff, BankStaffRole, PartnerBank
from src.models.base import get_db_session
from src.security.passwords import default_staff_password, hash_password, verify_password
from src.services.audit import AuditService
from src.services.bank_routing import BankRoutingService
from src.services.onboarding import ApplicationNotFoundError, OnboardingService
from src.state.machine import StateGuardError, StateTransitionError

router = APIRouter(prefix="/v1/bank-portal", tags=["BankPortal"])
_bearer = HTTPBearer(auto_error=False)
_audit = AuditService()
_routing = BankRoutingService(audit=_audit)

PORTAL_TOKEN_MINUTES = int(os.getenv("BANK_PORTAL_TOKEN_MINUTES", "480"))


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)
    bank_id: str = Field(..., min_length=3)


class LoginResponse(BaseModel):
    token: str
    bank_id: str
    role: str
    email: str
    expires_in: int


class SettingsResponse(BaseModel):
    bank_id: str
    ff_outbound: bool
    ff_inbound: bool
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None


class SettingsPatchRequest(BaseModel):
    ff_outbound: Optional[bool] = None
    ff_inbound: Optional[bool] = None


class QueueItem(BaseModel):
    application_id: uuid.UUID
    user_ref: str
    bank_id: str
    tier: str
    status: str
    created_at: datetime
    updated_at: datetime
    account_number: Optional[str] = None
    bank_reference: Optional[str] = None
    error_message: Optional[str] = None
    dynamic_fields: Optional[Dict[str, Any]] = None
    bank_edited_fields: Optional[Dict[str, Any]] = None


class DashboardResponse(BaseModel):
    bank_id: str
    outbound_count: int
    inbound_count: int
    ff_outbound: bool
    ff_inbound: bool


class OutboundSendRequest(BaseModel):
    edited_fields: Optional[Dict[str, Any]] = None


class InboundReleaseRequest(BaseModel):
    status: str = Field(..., description="ACCOUNT_OPENED or BANK_REJECTED")
    account_number: Optional[str] = None
    bank_reference: Optional[str] = None
    reject_reason: Optional[str] = None
    edited_fields: Optional[Dict[str, Any]] = None


class StaffCreateRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)
    role: BankStaffRole = BankStaffRole.EMPLOYEE


class StaffItem(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    active: bool
    created_at: datetime
    created_by: Optional[str] = None


class AuditItem(BaseModel):
    id: int
    timestamp: datetime
    actor_type: str
    actor_id: str
    action: str
    application_id: Optional[uuid.UUID] = None
    payload_hash: str


def _staff_actor(claims: Dict[str, Any]) -> str:
    return f"{claims.get('bank_id')}:{claims.get('email')}"


async def require_portal_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing Authorization Bearer token.")
    # Avoid JWT `aud` (PyJWT verifies it by default); use portal_scope instead.
    claims = decode_access_token(credentials.credentials)
    if claims.get("portal_scope") != "bank-portal" and claims.get("aud") != "bank-portal":
        raise HTTPException(status_code=403, detail="Not a bank portal token.")
    if not claims.get("bank_id") or not claims.get("role"):
        raise HTTPException(status_code=403, detail="Incomplete portal claims.")
    return claims


def require_roles(*roles: BankStaffRole):
    allowed = {r.value for r in roles}

    async def _dep(claims: Dict[str, Any] = Depends(require_portal_auth)) -> Dict[str, Any]:
        if str(claims.get("role")) not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient portal role.")
        return claims

    return _dep


def _to_queue_item(app: Any) -> QueueItem:
    account = bank_ref = err = None
    dyn = None
    if app.submissions:
        sub = app.submissions[0]
        account = sub.account_number
        bank_ref = sub.bank_reference
        err = sub.error_message
        dyn = sub.dynamic_fields
    return QueueItem(
        application_id=app.id,
        user_ref=app.user_ref,
        bank_id=app.bank_id,
        tier=app.tier,
        status=app.status.value,
        created_at=app.created_at,
        updated_at=app.updated_at,
        account_number=account,
        bank_reference=bank_ref,
        error_message=err,
        dynamic_fields=dyn,
        bank_edited_fields=app.bank_edited_fields,
    )


@router.post("/auth/login", response_model=LoginResponse)
async def portal_login(
    req: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    partner = await session.get(PartnerBank, req.bank_id)
    if partner is None or not partner.active:
        # Fall back to public registry refresh for first-boot / seed races.
        from src.api.routes.banks import refresh_bank_registry

        await refresh_bank_registry(session)
        partner = await session.get(PartnerBank, req.bank_id)
        if partner is None or not partner.active:
            raise HTTPException(status_code=404, detail=f"Unknown bank '{req.bank_id}'.")

    email = req.email.lower().strip()
    stmt = select(BankStaff).where(
        BankStaff.bank_id == req.bank_id,
        BankStaff.email == email,
        BankStaff.active.is_(True),
    )
    staff = (await session.execute(stmt)).scalar_one_or_none()
    if staff is None or not verify_password(req.password, staff.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token(
        user_ref=str(staff.id),
        device_fingerprint=f"portal:{staff.bank_id}:{staff.id}",
        expires_delta=timedelta(minutes=PORTAL_TOKEN_MINUTES),
        extra_claims={
            "portal_scope": "bank-portal",
            "bank_id": staff.bank_id,
            "role": staff.role.value,
            "email": staff.email,
            "staff_id": str(staff.id),
        },
    )
    await _audit.record_event(
        session=session,
        actor_type="BANK",
        actor_id=f"{staff.bank_id}:{staff.email}",
        action="PORTAL_LOGIN",
        application_id=None,
        payload={"bank_id": staff.bank_id, "role": staff.role.value},
    )
    await session.commit()
    return LoginResponse(
        token=token,
        bank_id=staff.bank_id,
        role=staff.role.value,
        email=staff.email,
        expires_in=PORTAL_TOKEN_MINUTES * 60,
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
    claims: Dict[str, Any] = Depends(require_portal_auth),
) -> DashboardResponse:
    bank_id = str(claims["bank_id"])
    outbound = await onboarding.list_outbound_queue(session, bank_id)
    inbound = await onboarding.list_inbound_queue(session, bank_id)
    settings = await _routing.get_or_create_settings(session, bank_id)
    await session.commit()
    return DashboardResponse(
        bank_id=bank_id,
        outbound_count=len(outbound),
        inbound_count=len(inbound),
        ff_outbound=bool(settings.ff_outbound),
        ff_inbound=bool(settings.ff_inbound),
    )


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    session: AsyncSession = Depends(get_db_session),
    claims: Dict[str, Any] = Depends(require_portal_auth),
) -> SettingsResponse:
    row = await _routing.get_or_create_settings(session, str(claims["bank_id"]))
    await session.commit()
    return SettingsResponse(
        bank_id=row.bank_id,
        ff_outbound=row.ff_outbound,
        ff_inbound=row.ff_inbound,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


@router.patch("/settings", response_model=SettingsResponse)
async def patch_settings(
    req: SettingsPatchRequest,
    session: AsyncSession = Depends(get_db_session),
    claims: Dict[str, Any] = Depends(
        require_roles(BankStaffRole.SUPER_ADMIN, BankStaffRole.ADMIN)
    ),
) -> SettingsResponse:
    if req.ff_outbound is None and req.ff_inbound is None:
        raise HTTPException(status_code=400, detail="Provide ff_outbound and/or ff_inbound.")
    row = await _routing.update_flags(
        session,
        str(claims["bank_id"]),
        ff_outbound=req.ff_outbound,
        ff_inbound=req.ff_inbound,
        actor_id=_staff_actor(claims),
    )
    await session.commit()
    return SettingsResponse(
        bank_id=row.bank_id,
        ff_outbound=row.ff_outbound,
        ff_inbound=row.ff_inbound,
        updated_by=row.updated_by,
        updated_at=row.updated_at,
    )


@router.get("/queues/outbound", response_model=List[QueueItem])
async def outbound_queue(
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
    claims: Dict[str, Any] = Depends(require_portal_auth),
) -> List[QueueItem]:
    apps = await onboarding.list_outbound_queue(session, str(claims["bank_id"]))
    return [_to_queue_item(a) for a in apps]


@router.get("/queues/inbound", response_model=List[QueueItem])
async def inbound_queue(
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
    claims: Dict[str, Any] = Depends(require_portal_auth),
) -> List[QueueItem]:
    apps = await onboarding.list_inbound_queue(session, str(claims["bank_id"]))
    return [_to_queue_item(a) for a in apps]


@router.post("/queues/outbound/{application_id}/send", response_model=QueueItem)
async def send_outbound(
    application_id: uuid.UUID,
    req: OutboundSendRequest,
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
    claims: Dict[str, Any] = Depends(require_portal_auth),
) -> QueueItem:
    bank_id = str(claims["bank_id"])
    try:
        app = await onboarding.get_application(session, application_id)
    except ApplicationNotFoundError:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.bank_id != bank_id:
        raise HTTPException(status_code=403, detail="Cross-bank access denied.")
    try:
        app = await onboarding.enqueue_outbound_to_cbs(
            session,
            application_id,
            actor_id=_staff_actor(claims),
            edited_fields=req.edited_fields,
        )
    except (StateGuardError, StateTransitionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _to_queue_item(app)


@router.post("/queues/inbound/{application_id}/release", response_model=QueueItem)
async def release_inbound(
    application_id: uuid.UUID,
    req: InboundReleaseRequest,
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
    claims: Dict[str, Any] = Depends(require_portal_auth),
) -> QueueItem:
    bank_id = str(claims["bank_id"])
    try:
        release_status = ApplicationStatus(req.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid release status") from exc
    try:
        app = await onboarding.get_application(session, application_id)
    except ApplicationNotFoundError:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.bank_id != bank_id:
        raise HTTPException(status_code=403, detail="Cross-bank access denied.")
    try:
        app = await onboarding.release_inbound(
            session,
            application_id,
            release_status=release_status,
            account_number=req.account_number,
            bank_reference=req.bank_reference,
            reject_reason=req.reject_reason,
            edited_fields=req.edited_fields,
            actor_id=_staff_actor(claims),
        )
    except (StateGuardError, StateTransitionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return _to_queue_item(app)


@router.get("/staff", response_model=List[StaffItem])
async def list_staff(
    session: AsyncSession = Depends(get_db_session),
    claims: Dict[str, Any] = Depends(
        require_roles(BankStaffRole.SUPER_ADMIN, BankStaffRole.ADMIN)
    ),
) -> List[StaffItem]:
    bank_id = str(claims["bank_id"])
    rows = (
        await session.execute(
            select(BankStaff).where(BankStaff.bank_id == bank_id).order_by(BankStaff.created_at)
        )
    ).scalars().all()
    return [
        StaffItem(
            id=r.id,
            email=r.email,
            role=r.role.value,
            active=r.active,
            created_at=r.created_at,
            created_by=r.created_by,
        )
        for r in rows
    ]


@router.post("/staff", response_model=StaffItem, status_code=201)
async def invite_staff(
    req: StaffCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    claims: Dict[str, Any] = Depends(
        require_roles(BankStaffRole.SUPER_ADMIN, BankStaffRole.ADMIN)
    ),
) -> StaffItem:
    bank_id = str(claims["bank_id"])
    actor_role = BankStaffRole(str(claims["role"]))
    if req.role == BankStaffRole.SUPER_ADMIN and actor_role != BankStaffRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only Super Admin can create Super Admins.")
    if actor_role == BankStaffRole.ADMIN and req.role not in (
        BankStaffRole.ADMIN,
        BankStaffRole.EMPLOYEE,
    ):
        raise HTTPException(status_code=403, detail="Admins may only invite Admin/Employee.")

    email = req.email.lower().strip()
    existing = (
        await session.execute(
            select(BankStaff).where(BankStaff.bank_id == bank_id, BankStaff.email == email)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Staff email already exists for this bank.")

    row = BankStaff(
        bank_id=bank_id,
        email=email,
        password_hash=hash_password(req.password),
        role=req.role,
        active=True,
        created_by=_staff_actor(claims),
    )
    session.add(row)
    await _audit.record_event(
        session=session,
        actor_type="BANK",
        actor_id=_staff_actor(claims),
        action="STAFF_INVITED",
        application_id=None,
        payload={"bank_id": bank_id, "email": email, "role": req.role.value},
    )
    await session.commit()
    await session.refresh(row)
    return StaffItem(
        id=row.id,
        email=row.email,
        role=row.role.value,
        active=row.active,
        created_at=row.created_at,
        created_by=row.created_by,
    )


@router.post("/staff/{staff_id}/revoke", response_model=StaffItem)
async def revoke_staff(
    staff_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    claims: Dict[str, Any] = Depends(
        require_roles(BankStaffRole.SUPER_ADMIN, BankStaffRole.ADMIN)
    ),
) -> StaffItem:
    bank_id = str(claims["bank_id"])
    row = await session.get(BankStaff, staff_id)
    if row is None or row.bank_id != bank_id:
        raise HTTPException(status_code=404, detail="Staff not found.")
    if row.role == BankStaffRole.SUPER_ADMIN and str(claims["role"]) != BankStaffRole.SUPER_ADMIN.value:
        raise HTTPException(status_code=403, detail="Cannot revoke Super Admin.")
    if str(row.id) == str(claims.get("staff_id")):
        raise HTTPException(status_code=400, detail="Cannot revoke your own account.")
    row.active = False
    await _audit.record_event(
        session=session,
        actor_type="BANK",
        actor_id=_staff_actor(claims),
        action="STAFF_REVOKED",
        application_id=None,
        payload={"bank_id": bank_id, "staff_id": str(staff_id), "email": row.email},
    )
    await session.commit()
    return StaffItem(
        id=row.id,
        email=row.email,
        role=row.role.value,
        active=row.active,
        created_at=row.created_at,
        created_by=row.created_by,
    )


@router.get("/audit", response_model=List[AuditItem])
async def list_audit(
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
    claims: Dict[str, Any] = Depends(
        require_roles(BankStaffRole.SUPER_ADMIN, BankStaffRole.ADMIN)
    ),
) -> List[AuditItem]:
    bank_id = str(claims["bank_id"])
    rows = await _audit.list_recent(session, application_id=None, limit=limit * 3)
    # Filter bank-scoped actions by actor_id / payload bank_id heuristic
    filtered: List[AuditItem] = []
    for r in rows:
        actor = r.actor_id or ""
        if actor.startswith(f"{bank_id}:") or actor == bank_id:
            filtered.append(
                AuditItem(
                    id=r.id,
                    timestamp=r.timestamp,
                    actor_type=r.actor_type,
                    actor_id=r.actor_id,
                    action=r.action,
                    application_id=r.application_id,
                    payload_hash=r.payload_hash,
                )
            )
        if len(filtered) >= limit:
            break
    return filtered


async def bootstrap_bank_portal_staff(session: AsyncSession) -> int:
    """Seed one Super Admin per partner bank when none exist."""
    from src.services.partner_catalog import list_partner_bank_rows, seed_partner_banks_from_catalog

    await seed_partner_banks_from_catalog(session)
    password = default_staff_password()
    created = 0
    for row in await list_partner_bank_rows(session, active_only=True):
        bank_id = row.bank_id
        await _routing.get_or_create_settings(session, bank_id)
        existing = (
            await session.execute(
                select(BankStaff).where(
                    BankStaff.bank_id == bank_id,
                    BankStaff.role == BankStaffRole.SUPER_ADMIN,
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        email = os.getenv(
            f"BANK_PORTAL_SUPER_{bank_id.upper()}",
            f"super@{bank_id.replace('bank_', '')}.portal.local",
        ).lower()
        session.add(
            BankStaff(
                bank_id=bank_id,
                email=email,
                password_hash=hash_password(password),
                role=BankStaffRole.SUPER_ADMIN,
                active=True,
                created_by="SYSTEM_BOOTSTRAP",
            )
        )
        created += 1
    if created:
        await session.flush()
    return created
