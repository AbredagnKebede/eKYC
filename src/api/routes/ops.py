"""Bank operations console API — sandbox-friendly staff actions."""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.application import ApplicationStatus
from src.models.base import get_db_session
from src.services.audit import AuditService
from src.services.onboarding import ApplicationNotFoundError, OnboardingService
from src.api.routes.applications import get_onboarding_service

router = APIRouter(prefix="/v1/ops", tags=["BankOps"])

OPS_API_KEY = os.getenv("OPS_API_KEY", os.getenv("BANK_API_KEY", "dev-bank-key"))
_audit = AuditService()


def require_ops_key(x_ops_api_key: Optional[str] = Header(None, alias="X-Ops-Api-Key")) -> None:
    provided = (x_ops_api_key or "").strip()
    if not provided or not secrets.compare_digest(provided, OPS_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Ops-Api-Key.",
        )


class OpsApplicationItem(BaseModel):
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


class ApproveRequest(BaseModel):
    account_number: str = Field(..., min_length=6, max_length=32)
    bank_reference: Optional[str] = None


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class AuditItem(BaseModel):
    id: int
    timestamp: datetime
    actor_type: str
    actor_id: str
    action: str
    application_id: Optional[uuid.UUID] = None
    payload_hash: str


def _to_item(app: Any) -> OpsApplicationItem:
    account = None
    bank_ref = None
    err = None
    if app.submissions:
        sub = app.submissions[0]
        account = sub.account_number
        bank_ref = sub.bank_reference
        err = sub.error_message
    return OpsApplicationItem(
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
    )


@router.get("/queue", response_model=List[OpsApplicationItem], dependencies=[Depends(require_ops_key)])
async def list_pending_queue(
    bank_id: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
) -> List[OpsApplicationItem]:
    apps = await onboarding.list_pending_bank_queue(session, bank_id=bank_id)
    return [_to_item(a) for a in apps]


@router.post(
    "/applications/{application_id}/approve",
    response_model=OpsApplicationItem,
    dependencies=[Depends(require_ops_key)],
)
async def approve_application(
    application_id: uuid.UUID,
    req: ApproveRequest,
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
) -> OpsApplicationItem:
    try:
        app = await onboarding.update_bank_status(
            session=session,
            application_id=application_id,
            new_status=ApplicationStatus.ACCOUNT_OPENED,
            account_number=req.account_number,
            bank_reference=req.bank_reference or f"OPS-{application_id.hex[:8]}",
            actor_id="OPS_CONSOLE",
        )
    except ApplicationNotFoundError:
        raise HTTPException(status_code=404, detail="Application not found")
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await onboarding.audit_service.record_event(
        session=session,
        actor_type="BANK",
        actor_id="OPS_CONSOLE",
        action="OPS_APPROVED",
        application_id=application_id,
        payload={"account_number": req.account_number},
    )
    await session.commit()
    return _to_item(app)


@router.post(
    "/applications/{application_id}/reject",
    response_model=OpsApplicationItem,
    dependencies=[Depends(require_ops_key)],
)
async def reject_application(
    application_id: uuid.UUID,
    req: RejectRequest,
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
) -> OpsApplicationItem:
    try:
        app = await onboarding.get_application(session, application_id)
        if app.submissions:
            app.submissions[0].error_message = req.reason
        app = await onboarding.update_bank_status(
            session=session,
            application_id=application_id,
            new_status=ApplicationStatus.BANK_REJECTED,
            actor_id="OPS_CONSOLE",
        )
    except ApplicationNotFoundError:
        raise HTTPException(status_code=404, detail="Application not found")
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await onboarding.audit_service.record_event(
        session=session,
        actor_type="BANK",
        actor_id="OPS_CONSOLE",
        action="OPS_REJECTED",
        application_id=application_id,
        payload={"reason": req.reason},
    )
    await session.commit()
    return _to_item(app)


@router.get("/audit", response_model=List[AuditItem], dependencies=[Depends(require_ops_key)])
async def list_audit_events(
    application_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
) -> List[AuditItem]:
    rows = await _audit.list_recent(session, application_id=application_id, limit=limit)
    return [
        AuditItem(
            id=r.id,
            timestamp=r.timestamp,
            actor_type=r.actor_type,
            actor_id=r.actor_id,
            action=r.action,
            application_id=r.application_id,
            payload_hash=r.payload_hash,
        )
        for r in rows
    ]


@router.get("/audit/integrity", dependencies=[Depends(require_ops_key)])
async def audit_integrity(session: AsyncSession = Depends(get_db_session)) -> Dict[str, Any]:
    ok, err = await _audit.verify_ledger_integrity(session)
    return {"ok": ok, "error": err}
