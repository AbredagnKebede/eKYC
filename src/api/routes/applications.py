import base64
import hashlib
import hmac
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.rate_limiter import SlidingWindowRateLimiter
from src.infrastructure.redis import get_redis_client
from src.models.application import ApplicationStatus
from src.models.base import get_db_session
from src.security.liveness import FaceMatchResult, LivenessResult
from src.services.bank_adapter import (
    BankAdapterService,
    BankNotFoundError,
    BankSchemaValidationError,
)
from src.services.identity import (
    FaydaError,
    FaydaFormatError,
    FaydaVerificationError,
    IdentityError,
    IdentityNotFoundError,
    IdentityService,
    InvalidStateError,
    LivenessVerificationError,
)
from src.services.onboarding import (
    ApplicationNotFoundError,
    OnboardingService,
    StateGuardError,
    StateTransitionError,
)
from src.state.machine import ApplicationStateMachine

from src.api.middleware import (
    HTTPAuthorizationCredentials,
    create_access_token,
    decode_access_token,
    security_bearer,
)
from src.api.routes.banks import get_bank_adapter_service

router = APIRouter(prefix="/v1", tags=["Applications"])

BANK_API_KEY = os.getenv("BANK_API_KEY", "dev-bank-key")

# Service Singletons / Dependencies
_onboarding_service = OnboardingService()
_identity_service = IdentityService()
_rate_limiter = SlidingWindowRateLimiter()


def get_onboarding_service() -> OnboardingService:
    return _onboarding_service


def get_identity_service() -> IdentityService:
    return _identity_service


def get_redis_dep():
    return get_redis_client()


# Request / Response Schemas
class CreateApplicationRequest(BaseModel):
    user_ref: str = Field(..., description="Unique applicant client reference")
    bank_id: str = Field(..., description="Selected partner bank identifier (e.g. bank_awash)")
    tier: str = Field(default="standard", description="Selected account tier")


class CreateApplicationResponse(BaseModel):
    application_id: uuid.UUID
    status: str
    expires_at: datetime
    token: str


class ApplicationDetailResponse(BaseModel):
    application_id: uuid.UUID
    user_ref: str
    bank_id: str
    tier: str
    status: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    account_number: Optional[str] = None
    bank_reference: Optional[str] = None


class ConsentRequest(BaseModel):
    consent_version: str = Field(default="v1.0", description="Accepted terms version")
    accepted: bool = Field(default=True, description="True if customer accepted, False if refused/declined")
    ip_address: Optional[str] = None
    device_fingerprint: Optional[str] = None


class ConsentResponse(BaseModel):
    application_id: uuid.UUID
    status: str
    consented_at: Optional[datetime] = None


class IdentityStartRequest(BaseModel):
    fin: str = Field(..., description="12-digit citizen Fayda Identification Number")


class IdentityStartResponse(BaseModel):
    transaction_id: str
    expires_in: int
    message: str


class IdentityVerifyRequest(BaseModel):
    transaction_id: str
    otp: str = Field(..., min_length=6, max_length=6, description="6-digit SMS OTP code")


class IdentityVerifyResponse(BaseModel):
    application_id: uuid.UUID
    status: str
    verified_at: datetime


class LivenessRequest(BaseModel):
    selfie_base64: str = Field(..., description="Base64 encoded selfie frame image")
    fayda_photo_base64: Optional[str] = Field(None, description="Optional demographic photo assertion")


class LivenessResponse(BaseModel):
    status: str
    liveness_score: float
    face_match_score: float
    application_id: str


class DynamicFieldsRequest(BaseModel):
    dynamic_fields: Dict[str, Any] = Field(..., description="Bank specific dynamic attributes")


class DynamicFieldsResponse(BaseModel):
    application_id: uuid.UUID
    status: str
    dynamic_fields: Dict[str, Any]


class SubmitApplicationRequest(BaseModel):
    signature: str = Field(..., min_length=2, description="Applicant digital signature token or SVG path")


class SubmitApplicationResponse(BaseModel):
    application_id: uuid.UUID
    status: str
    idempotency_hash: Optional[str] = None


class WebhookCallbackRequest(BaseModel):
    application_id: uuid.UUID
    status: str = Field(..., description="CBS status update (e.g. ACCOUNT_OPENED or BANK_REJECTED)")
    account_number: Optional[str] = None
    bank_reference: Optional[str] = None


class WebhookCallbackResponse(BaseModel):
    status: str
    application_id: str
    idempotent: Optional[bool] = None


# Endpoints
@router.post("/applications", response_model=CreateApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    req: CreateApplicationRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
    banks: BankAdapterService = Depends(get_bank_adapter_service),
    x_device_fingerprint: Optional[str] = Header(None, alias="X-Device-Fingerprint"),
) -> CreateApplicationResponse:
    """Initializes a new customer onboarding session in DRAFT state."""
    # Ensure bank is supported
    try:
        banks.get_adapter(req.bank_id)
    except BankNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Partner bank '{req.bank_id}' not found.",
        )

    device_fp = x_device_fingerprint or "default-device-fp"
    app = await onboarding.create_application(
        session=session,
        user_ref=req.user_ref,
        bank_id=req.bank_id,
        tier=req.tier,
    )
    await session.commit()

    token = create_access_token(
        user_ref=req.user_ref,
        device_fingerprint=device_fp,
        extra_claims={"application_id": str(app.id)},
    )

    return CreateApplicationResponse(
        application_id=app.id,
        status=app.status.value,
        expires_at=app.expires_at,
        token=token,
    )


@router.get("/applications/{application_id}", response_model=ApplicationDetailResponse)
async def get_application_details(
    application_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
) -> ApplicationDetailResponse:
    """Returns application status, issued account number, and next steps."""
    try:
        app = await onboarding.get_application(session, application_id)
    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found.",
        )

    account_no = None
    bank_ref = None
    if app.submissions:
        sub = app.submissions[0]
        account_no = sub.account_number
        bank_ref = sub.bank_reference

    return ApplicationDetailResponse(
        application_id=app.id,
        user_ref=app.user_ref,
        bank_id=app.bank_id,
        tier=app.tier,
        status=app.status.value,
        created_at=app.created_at,
        updated_at=app.updated_at,
        expires_at=app.expires_at,
        account_number=account_no,
        bank_reference=bank_ref,
    )


@router.post("/applications/{application_id}/consent", response_model=ConsentResponse)
async def record_consent(
    application_id: uuid.UUID,
    req: ConsentRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    x_device_fingerprint: Optional[str] = Header(None, alias="X-Device-Fingerprint"),
) -> ConsentResponse:
    """Records explicit citizen consent or processes cancellation if consent refused."""
    if credentials:
        decode_access_token(credentials.credentials)

    try:
        app = await onboarding.get_application(session, application_id)
    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found.",
        )

    if app.expires_at and app.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please start a new application.",
        )

    ip_addr = req.ip_address or (request.client.host if request.client else "127.0.0.1")
    device_fp = req.device_fingerprint or x_device_fingerprint or "default-device-fp"

    # User refused consent -> AS-02 / J-02: transition to CANCELLED and log CONSENT_REFUSED
    if not req.accepted:
        if app.status == ApplicationStatus.CANCELLED:
            # Deterministic idempotent response for duplicate cancellations
            return ConsentResponse(application_id=app.id, status=ApplicationStatus.CANCELLED.value)

        ApplicationStateMachine.validate_transition(app.status, ApplicationStatus.CANCELLED)
        app.status = ApplicationStatus.CANCELLED
        await onboarding.audit_service.record_event(
            session=session,
            actor_type="CUSTOMER",
            actor_id=app.user_ref,
            action="CONSENT_REFUSED",
            application_id=app.id,
            payload={"ip_address": ip_addr, "device_fingerprint": device_fp},
        )
        await session.commit()
        return ConsentResponse(application_id=app.id, status=ApplicationStatus.CANCELLED.value)

    # Consent accepted
    try:
        updated_app = await onboarding.record_consent(
            session=session,
            application_id=application_id,
            consent_version=req.consent_version,
            ip_address=ip_addr,
            device_fingerprint=device_fp,
        )
        await session.commit()
        consent_rec = updated_app.consents[-1] if updated_app.consents else None
        return ConsentResponse(
            application_id=updated_app.id,
            status=updated_app.status.value,
            consented_at=consent_rec.accepted_at if consent_rec else None,
        )
    except StateTransitionError as st_err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(st_err),
        )


@router.post("/applications/{application_id}/identity/start", response_model=IdentityStartResponse)
async def start_identity_verification(
    application_id: uuid.UUID,
    req: IdentityStartRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
    identity: IdentityService = Depends(get_identity_service),
    redis_client: Any = Depends(get_redis_dep),
    x_device_fingerprint: Optional[str] = Header(None, alias="X-Device-Fingerprint"),
) -> IdentityStartResponse:
    """Dispatches Fayda OTP challenge with format verification and failure lockout protection."""
    try:
        app = await onboarding.get_application(session, application_id)
    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found.",
        )

    # Invariant: Must be in CONSENTED state before identity verification (J-02 AP-4)
    if app.status != ApplicationStatus.CONSENTED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CONSENT_REQUIRED: Consent must be granted before starting identity verification.",
        )

    device_key = x_device_fingerprint or (request.client.host if request.client else "unknown-device")
    lockout_key = f"ratelimit:fayda:attempts:{device_key}"

    # Format check: 12-digit FIN requirement (AS-03 / J-03)
    if not re.fullmatch(r"\d{12}", req.fin.strip()):
        # Increment attempt counter in Redis
        try:
            current_attempts = await redis_client.incr(lockout_key)
            if current_attempts == 1:
                await redis_client.expire(lockout_key, 900)  # 15 minutes window

            if current_attempts >= 6:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Identity requests are temporarily locked for 15 minutes due to repeated invalid attempts.",
                    headers={"Retry-After": "900"},
                )
        except HTTPException:
            raise
        except Exception:
            pass

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Fayda FIN must be exactly 12 numeric digits.",
        )

    # Valid format: Check if client is currently locked out
    try:
        attempts_str = await redis_client.get(lockout_key)
        if attempts_str and int(attempts_str) >= 6:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Identity requests are temporarily locked for 15 minutes due to repeated invalid attempts.",
                headers={"Retry-After": "900"},
            )
    except HTTPException:
        raise
    except Exception:
        pass

    try:
        challenge = await identity.start_fayda_verification(
            application_id=application_id,
            fin=req.fin.strip(),
            session=session,
        )
        try:
            tx_id = challenge["transaction_id"]
            await redis_client.set(f"otp:session:{application_id}", tx_id, ex=180)
            await redis_client.set(f"otp:attempts:{application_id}", 0, ex=180)
        except Exception:
            pass
        return IdentityStartResponse(
            transaction_id=challenge["transaction_id"],
            expires_in=challenge.get("expires_in", 300),
            message="Fayda OTP challenge dispatched successfully.",
        )
    except (InvalidStateError, StateGuardError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except FaydaError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Fayda Gateway Error: {exc}")


@router.post("/applications/{application_id}/identity/verify", response_model=IdentityVerifyResponse)
async def verify_identity_otp(
    application_id: uuid.UUID,
    req: IdentityVerifyRequest,
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
    identity: IdentityService = Depends(get_identity_service),
    redis_client: Any = Depends(get_redis_dep),
) -> IdentityVerifyResponse:
    """Verifies citizen OTP against Fayda eKYC asserting encrypted demographic snapshot."""
    try:
        app = await onboarding.get_application(session, application_id)
    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found.",
        )

    if app.status == ApplicationStatus.ID_FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Application is in terminal state ID_FAILED. Please visit your nearest bank branch.",
        )

    session_key = f"otp:session:{application_id}"
    attempts_key = f"otp:attempts:{application_id}"
    current_attempt = 1
    try:
        if await redis_client.exists(attempts_key) and not await redis_client.exists(session_key):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="OTP challenge has expired. Please request a new OTP challenge.",
            )
        current_attempt = await redis_client.incr(attempts_key)
    except HTTPException:
        raise
    except Exception:
        pass

    try:
        snapshot = await identity.verify_fayda_otp(
            application_id=application_id,
            transaction_id=req.transaction_id,
            otp=req.otp,
            session=session,
            attempt=current_attempt,
            max_attempts=3,
        )
        try:
            await redis_client.delete(session_key)
            await redis_client.delete(attempts_key)
        except Exception:
            pass
        return IdentityVerifyResponse(
            application_id=application_id,
            status=ApplicationStatus.ID_VERIFIED.value,
            verified_at=snapshot.verified_at,
        )
    except FaydaVerificationError as ver_err:
        if "410" in str(ver_err) or "expired" in str(ver_err).lower():
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="OTP challenge has expired. Please request a new OTP challenge.",
            )
        if current_attempt >= 3:
            try:
                await redis_client.delete(session_key)
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Identity verification failed. Maximum attempts reached. Please visit your chosen bank branch to complete onboarding.",
            )
        remaining = max(0, 3 - current_attempt)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid OTP. {remaining} attempt{'s' if remaining != 1 else ''} remaining.",
        )
    except FaydaError as fayda_err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(fayda_err),
        )


@router.post("/applications/{application_id}/liveness", response_model=LivenessResponse)
async def verify_liveness(
    application_id: uuid.UUID,
    req: LivenessRequest,
    session: AsyncSession = Depends(get_db_session),
    identity: IdentityService = Depends(get_identity_service),
) -> LivenessResponse:
    """Evaluates biometric camera frames against anti-spoofing engine and face match."""
    try:
        selfie_bytes = base64.b64decode(req.selfie_base64)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid base64 encoding for selfie frame.",
        )

    ref_photo_bytes = None
    if req.fayda_photo_base64:
        try:
            ref_photo_bytes = base64.b64decode(req.fayda_photo_base64)
        except Exception:
            pass

    try:
        res = await identity.verify_liveness_and_face(
            application_id=application_id,
            selfie_bytes=selfie_bytes,
            fayda_photo_bytes=ref_photo_bytes,
            session=session,
        )
        return LivenessResponse(
            status=res["status"],
            liveness_score=res["liveness_score"],
            face_match_score=res["face_match_score"],
            application_id=res["application_id"],
        )
    except IdentityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found.",
        )
    except LivenessVerificationError as liveness_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "type": "https://errors.ekyc.et/LIVENESS_FAILED",
                "title": "Liveness Verification Failed",
                "status": 422,
                "detail": str(liveness_err),
                "spoof_detected": True,
                "liveness_score": liveness_err.liveness_score,
                "face_match_score": liveness_err.match_score,
            },
        )


@router.put("/applications/{application_id}/details", response_model=DynamicFieldsResponse)
async def save_dynamic_fields(
    application_id: uuid.UUID,
    req: DynamicFieldsRequest,
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
    banks: BankAdapterService = Depends(get_bank_adapter_service),
) -> DynamicFieldsResponse:
    """Validates and persists bank-specific dynamic form attributes."""
    try:
        app = await onboarding.get_application(session, application_id)
    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found.",
        )

    # Validate against partner bank's JSONSchema specification (J-06 AP-1)
    try:
        banks.validate_fields(app.bank_id, req.dynamic_fields)
    except BankSchemaValidationError as schema_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "type": "https://errors.ekyc.et/INVALID_DYNAMIC_FIELDS",
                "title": "Dynamic Schema Validation Failed",
                "status": 400,
                "detail": str(schema_err),
                "field_errors": schema_err.field_errors,
            },
        )
    except BankNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Partner bank '{app.bank_id}' not found.",
        )

    try:
        updated_app = await onboarding.save_dynamic_fields(
            session=session,
            application_id=application_id,
            dynamic_fields=req.dynamic_fields,
        )
        await session.commit()
        return DynamicFieldsResponse(
            application_id=updated_app.id,
            status=updated_app.status.value,
            dynamic_fields=req.dynamic_fields,
        )
    except StateTransitionError as st_err:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(st_err))


@router.post("/applications/{application_id}/submit", response_model=SubmitApplicationResponse)
async def submit_application(
    application_id: uuid.UUID,
    req: SubmitApplicationRequest,
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
) -> SubmitApplicationResponse:
    """Captures citizen signature, moves to SUBMITTED_TO_BANK, and publishes queue event."""
    try:
        app = await onboarding.get_application(session, application_id)
    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {application_id} not found.",
        )

    try:
        updated_app = await onboarding.submit_application(
            session=session,
            application_id=application_id,
            signature=req.signature,
        )
        await session.commit()
        return SubmitApplicationResponse(
            application_id=updated_app.id,
            status=updated_app.status.value,
            idempotency_hash=updated_app.idempotency_hash,
        )
    except (StateGuardError, StateTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.post("/webhooks/bank/{bank_id}", response_model=WebhookCallbackResponse)
async def bank_webhook_callback(
    bank_id: str,
    req: WebhookCallbackRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    onboarding: OnboardingService = Depends(get_onboarding_service),
    x_signature: Optional[str] = Header(None, alias="X-Signature-SHA256"),
    x_bank_sig: Optional[str] = Header(None, alias="X-Bank-Signature"),
) -> WebhookCallbackResponse:
    """Asynchronous signed webhook callback invoked by partner bank CBS (J-08)."""
    # 1. Enforce HMAC-SHA256 signature verification (§6.1 / J-08 AP-4)
    provided_sig = x_signature or x_bank_sig
    if not provided_sig:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required webhook signature header (X-Signature-SHA256).",
        )

    body_bytes = await request.body()
    expected_sig = hmac.new(BANK_API_KEY.encode(), body_bytes, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided_sig, expected_sig):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tampered or invalid webhook signature.",
        )

    # 2. Retrieve application
    try:
        app = await onboarding.get_application(session, req.application_id)
    except ApplicationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {req.application_id} not found.",
        )

    # 3. Idempotent check: duplicate delivery with same account number returns HTTP 200 without duplicate mutation
    if app.status == ApplicationStatus.ACCOUNT_OPENED and app.submissions:
        if app.submissions[0].account_number == req.account_number:
            return WebhookCallbackResponse(
                status="acknowledged",
                application_id=str(app.id),
                idempotent=True,
            )

    # 4. Resolve target status and apply transition
    try:
        target_status = ApplicationStatus(req.status)
    except ValueError:
        target_status = ApplicationStatus.ACCOUNT_OPENED

    # Reconcile status transition
    await onboarding.update_bank_status(
        session=session,
        application_id=req.application_id,
        new_status=target_status,
        account_number=req.account_number,
        bank_reference=req.bank_reference,
    )

    # 5. Record BANK_STATUS_WEBHOOK_PROCESSED audit entry (J-08 AP-5)
    await onboarding.audit_service.record_event(
        session=session,
        actor_type="BANK",
        actor_id=bank_id,
        action="BANK_STATUS_WEBHOOK_PROCESSED",
        application_id=app.id,
        payload={
            "bank_id": bank_id,
            "status": target_status.value,
            "account_number": req.account_number,
            "bank_reference": req.bank_reference,
            "body_hash": hashlib.sha256(body_bytes).hexdigest(),
        },
    )
    await session.commit()

    return WebhookCallbackResponse(
        status="acknowledged",
        application_id=str(app.id),
    )
