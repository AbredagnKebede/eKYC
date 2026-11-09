import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.events.application_submitted import ApplicationSubmittedEvent
from src.infrastructure.queue import SubmissionQueue
from src.models.application import (
    Application,
    ApplicationStatus,
    BankSubmission,
    ConsentRecord,
    IdentitySnapshot,
    utc_now,
)
from src.services.audit import AuditService
from src.state.machine import ApplicationStateMachine, StateGuardError, StateTransitionError

EVENT_SIGNING_KEY = os.getenv("JWT_SECRET_KEY", "dev-insecure-jwt-secret-replace-in-prod")


class ApplicationNotFoundError(Exception):
    """Raised when an onboarding application is not found by ID."""

    def __init__(self, application_id: Any) -> None:
        super().__init__(f"Application with ID '{application_id}' not found.")
        self.status_code = 404
        self.detail = str(self)


class OnboardingService:
    """Manages the full lifecycle and state machine progression for customer onboarding."""

    def __init__(
        self,
        audit_service: Optional[AuditService] = None,
        queue: Optional[SubmissionQueue] = None,
        signing_key: Optional[str] = None,
    ) -> None:
        self.audit_service = audit_service or AuditService()
        self.queue = queue or SubmissionQueue()
        self.signing_key = signing_key or EVENT_SIGNING_KEY

    async def get_application(
        self,
        session: AsyncSession,
        application_id: uuid.UUID,
        for_update: bool = False,
    ) -> Application:
        """Loads application along with eager-loaded relationships."""
        stmt = (
            select(Application)
            .options(
                selectinload(Application.consents),
                selectinload(Application.identity_snapshot),
                selectinload(Application.submissions),
            )
            .where(Application.id == application_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
        app = result.scalar_one_or_none()
        if not app:
            raise ApplicationNotFoundError(application_id)
        return app

    async def list_applications_for_user(
        self,
        session: AsyncSession,
        user_ref: str,
        limit: int = 50,
        fayda_ref_hash: Optional[str] = None,
    ) -> List[Application]:
        """Passport: all journeys for one applicant profile, newest first."""
        stmt = (
            select(Application)
            .options(
                selectinload(Application.consents),
                selectinload(Application.identity_snapshot),
                selectinload(Application.submissions),
            )
            .order_by(Application.created_at.desc())
            .limit(limit)
        )
        if fayda_ref_hash:
            stmt = stmt.where(
                (Application.user_ref == user_ref)
                | (Application.fayda_ref_hash == fayda_ref_hash)
            )
        else:
            stmt = stmt.where(Application.user_ref == user_ref)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_bank_queue(
        self,
        session: AsyncSession,
        bank_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Application]:
        """Ops console: applications awaiting bank decision."""
        pending = (
            ApplicationStatus.SUBMITTED_TO_BANK,
            ApplicationStatus.BANK_ACCEPTED,
            ApplicationStatus.AWAITING_BANK_OUTBOUND,
            ApplicationStatus.CBS_PENDING_BANK_RELEASE,
        )
        stmt = (
            select(Application)
            .options(selectinload(Application.submissions))
            .where(Application.status.in_(pending))
            .order_by(Application.updated_at.asc())
            .limit(limit)
        )
        if bank_id:
            stmt = stmt.where(Application.bank_id == bank_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def list_outbound_queue(
        self,
        session: AsyncSession,
        bank_id: str,
        limit: int = 100,
    ) -> List[Application]:
        stmt = (
            select(Application)
            .options(selectinload(Application.submissions))
            .where(
                Application.bank_id == bank_id,
                Application.status == ApplicationStatus.AWAITING_BANK_OUTBOUND,
            )
            .order_by(Application.updated_at.asc())
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())

    async def list_inbound_queue(
        self,
        session: AsyncSession,
        bank_id: str,
        limit: int = 100,
    ) -> List[Application]:
        stmt = (
            select(Application)
            .options(selectinload(Application.submissions))
            .where(
                Application.bank_id == bank_id,
                Application.status == ApplicationStatus.CBS_PENDING_BANK_RELEASE,
            )
            .order_by(Application.updated_at.asc())
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())

    async def create_application(
        self,
        session: AsyncSession,
        user_ref: str,
        bank_id: str,
        tier: str = "standard",
        duration_minutes: int = 60,
        actor_id: str = "SYSTEM",
        fayda_ref_hash: Optional[str] = None,
    ) -> Application:
        """Initializes a new onboarding session in DRAFT state."""
        app = Application(
            user_ref=user_ref,
            bank_id=bank_id,
            tier=tier,
            status=ApplicationStatus.DRAFT,
            fayda_ref_hash=fayda_ref_hash,
            expires_at=utc_now() + timedelta(minutes=duration_minutes),
        )
        session.add(app)
        await session.flush()

        await self.audit_service.record_event(
            session=session,
            actor_type="CUSTOMER",
            actor_id=actor_id,
            action="APPLICATION_CREATED",
            application_id=app.id,
            payload={"user_ref": user_ref, "bank_id": bank_id, "tier": tier},
        )
        return app

    async def record_consent(
        self,
        session: AsyncSession,
        application_id: uuid.UUID,
        consent_version: str,
        ip_address: str,
        device_fingerprint: str,
        actor_id: str = "CUSTOMER",
    ) -> Application:
        """Records explicit applicant consent and transitions state to CONSENTED."""
        app = await self.get_application(session, application_id)
        ApplicationStateMachine.validate_transition(app.status, ApplicationStatus.CONSENTED)

        consent = ConsentRecord(
            application_id=app.id,
            consent_version=consent_version,
            ip_address=ip_address,
            device_fingerprint=device_fingerprint,
        )
        session.add(consent)
        app.consents.append(consent)

        ApplicationStateMachine.check_consent_guard(app.consents)
        app.status = ApplicationStatus.CONSENTED
        await session.flush()

        await self.audit_service.record_event(
            session=session,
            actor_type="CUSTOMER",
            actor_id=actor_id,
            action="CONSENT_GRANTED",
            application_id=app.id,
            payload={
                "consent_version": consent_version,
                "ip_address": ip_address,
                "device_fingerprint": device_fingerprint,
            },
        )
        return app

    async def attach_identity_snapshot(
        self,
        session: AsyncSession,
        application_id: uuid.UUID,
        snapshot: IdentitySnapshot,
        actor_id: str = "SYSTEM",
    ) -> Application:
        """Associates verified demographic assertion and transitions to ID_VERIFIED."""
        app = await self.get_application(session, application_id)
        ApplicationStateMachine.validate_transition(app.status, ApplicationStatus.ID_VERIFIED)
        ApplicationStateMachine.check_id_verified_guard(snapshot)

        snapshot.application_id = app.id
        session.add(snapshot)
        app.identity_snapshot = snapshot
        app.fayda_ref_hash = snapshot.fayda_ref_hash
        app.status = ApplicationStatus.ID_VERIFIED
        await session.flush()

        await self.audit_service.record_event(
            session=session,
            actor_type="SYSTEM",
            actor_id=actor_id,
            action="IDENTITY_VERIFIED",
            application_id=app.id,
            payload={
                "fayda_ref_hash": snapshot.fayda_ref_hash,
                "verification_method": snapshot.verification_method.value,
            },
        )
        return app

    async def record_liveness(
        self,
        session: AsyncSession,
        application_id: uuid.UUID,
        liveness_score: float,
        face_similarity: float = 1.0,
        actor_id: str = "SYSTEM",
    ) -> Application:
        """Evaluates anti-spoofing and face comparison to transition liveness state."""
        app = await self.get_application(session, application_id)

        is_passed = (
            liveness_score >= ApplicationStateMachine.LIVENESS_THRESHOLD
            and face_similarity >= ApplicationStateMachine.SIMILARITY_THRESHOLD
        )

        target_status = ApplicationStatus.LIVENESS_PASSED if is_passed else ApplicationStatus.LIVENESS_FAILED
        ApplicationStateMachine.validate_transition(app.status, target_status)

        if is_passed:
            ApplicationStateMachine.check_liveness_guard(liveness_score, face_similarity)

        app.status = target_status
        if app.identity_snapshot:
            app.identity_snapshot.liveness_score = liveness_score

        await session.flush()

        await self.audit_service.record_event(
            session=session,
            actor_type="SYSTEM",
            actor_id=actor_id,
            action="LIVENESS_PASSED" if is_passed else "LIVENESS_FAILED",
            application_id=app.id,
            payload={
                "liveness_score": liveness_score,
                "face_similarity": face_similarity,
                "passed": is_passed,
            },
        )
        return app

    async def save_dynamic_fields(
        self,
        session: AsyncSession,
        application_id: uuid.UUID,
        dynamic_fields: Dict[str, Any],
        actor_id: str = "CUSTOMER",
    ) -> Application:
        """Validates and persists bank-specific dynamic fields, moving to DATA_COMPLETE."""
        app = await self.get_application(session, application_id)
        ApplicationStateMachine.validate_transition(app.status, ApplicationStatus.DATA_COMPLETE)
        ApplicationStateMachine.check_data_complete_guard(dynamic_fields)

        # Check existing or create new BankSubmission record
        submission = None
        for s in app.submissions:
            if s.bank_id == app.bank_id:
                submission = s
                break

        if not submission:
            submission = BankSubmission(
                application_id=app.id,
                bank_id=app.bank_id,
                dynamic_fields=dynamic_fields,
            )
            session.add(submission)
            app.submissions.append(submission)
        else:
            submission.dynamic_fields = dynamic_fields

        app.status = ApplicationStatus.DATA_COMPLETE
        await session.flush()

        await self.audit_service.record_event(
            session=session,
            actor_type="CUSTOMER",
            actor_id=actor_id,
            action="DYNAMIC_FIELDS_SAVED",
            application_id=app.id,
            payload={"bank_id": app.bank_id, "dynamic_fields": dynamic_fields},
        )
        return app

    async def submit_application(
        self,
        session: AsyncSession,
        application_id: uuid.UUID,
        signature: str,
        actor_id: str = "CUSTOMER",
    ) -> Application:
        """Finalizes application with signature; routes via Fast Forward outbound flag."""
        from src.services.bank_routing import BankRoutingService

        app = await self.get_application(session, application_id, for_update=True)
        ApplicationStateMachine.check_submission_guard(signature)

        routing = BankRoutingService(audit=self.audit_service)
        ff_outbound, _ = await routing.get_flags(session, app.bank_id)
        target = (
            ApplicationStatus.SUBMITTED_TO_BANK
            if ff_outbound
            else ApplicationStatus.AWAITING_BANK_OUTBOUND
        )
        ApplicationStateMachine.validate_transition(app.status, target)

        app.status = target
        idem_key = f"idem_{app.id}_{app.bank_id}"
        app.idempotency_hash = idem_key

        submission = None
        for s in app.submissions:
            if s.bank_id == app.bank_id:
                submission = s
                break

        if submission is None:
            submission = BankSubmission(
                application_id=app.id,
                bank_id=app.bank_id,
                dynamic_fields={},
            )
            session.add(submission)
            app.submissions.append(submission)
            dynamic_data: Dict[str, Any] = {}
        else:
            dynamic_data = submission.dynamic_fields or {}

        if ff_outbound:
            submission.sent_at = utc_now()
            submission.last_attempt_at = utc_now()
            event = ApplicationSubmittedEvent.create(
                application_id=str(app.id),
                bank_id=app.bank_id,
                secret_key=self.signing_key,
                tier=app.tier,
                idempotency_key=idem_key,
                dynamic_fields=dynamic_data,
            )
            await self.queue.enqueue(
                application_id=str(app.id),
                bank_id=app.bank_id,
                payload=event.model_dump(),
                idempotency_key=idem_key,
            )
            payload_sig = event.payload_signature
        else:
            payload_sig = None

        await session.flush()

        await self.audit_service.record_event(
            session=session,
            actor_type="CUSTOMER",
            actor_id=actor_id,
            action="APPLICATION_SUBMITTED",
            application_id=app.id,
            payload={
                "bank_id": app.bank_id,
                "tier": app.tier,
                "ff_outbound": ff_outbound,
                "status": target.value,
                "payload_signature": payload_sig,
            },
        )
        return app

    async def enqueue_outbound_to_cbs(
        self,
        session: AsyncSession,
        application_id: uuid.UUID,
        actor_id: str = "BANK",
        edited_fields: Optional[Dict[str, Any]] = None,
    ) -> Application:
        """Staff confirms outbound queue item and forwards to CBS."""
        app = await self.get_application(session, application_id, for_update=True)
        ApplicationStateMachine.validate_transition(
            app.status, ApplicationStatus.SUBMITTED_TO_BANK
        )
        if edited_fields:
            app.bank_edited_fields = edited_fields
            for s in app.submissions:
                if s.bank_id == app.bank_id:
                    merged = dict(s.dynamic_fields or {})
                    merged.update(edited_fields)
                    s.dynamic_fields = merged
                    break

        app.status = ApplicationStatus.SUBMITTED_TO_BANK
        idem_key = app.idempotency_hash or f"idem_{app.id}_{app.bank_id}"
        app.idempotency_hash = idem_key
        dynamic_data: Dict[str, Any] = {}
        for s in app.submissions:
            if s.bank_id == app.bank_id:
                s.sent_at = utc_now()
                s.last_attempt_at = utc_now()
                dynamic_data = s.dynamic_fields or {}
                break

        event = ApplicationSubmittedEvent.create(
            application_id=str(app.id),
            bank_id=app.bank_id,
            secret_key=self.signing_key,
            tier=app.tier,
            idempotency_key=idem_key,
            dynamic_fields=dynamic_data,
        )
        await self.queue.enqueue(
            application_id=str(app.id),
            bank_id=app.bank_id,
            payload=event.model_dump(),
            idempotency_key=f"{idem_key}_staff",
        )
        await self.audit_service.record_event(
            session=session,
            actor_type="BANK",
            actor_id=actor_id,
            action="OUTBOUND_SENT",
            application_id=app.id,
            payload={"bank_id": app.bank_id, "edited": bool(edited_fields)},
        )
        await session.flush()
        return app

    async def update_bank_status(
        self,
        session: AsyncSession,
        application_id: uuid.UUID,
        new_status: ApplicationStatus,
        account_number: Optional[str] = None,
        bank_reference: Optional[str] = None,
        actor_id: str = "WORKER",
        respect_inbound_ff: bool = True,
    ) -> Application:
        """Reconciles asynchronous callback or worker status mutation."""
        from src.services.bank_routing import BankRoutingService

        app = await self.get_application(session, application_id)
        resolved = new_status
        if respect_inbound_ff and new_status in (
            ApplicationStatus.ACCOUNT_OPENED,
            ApplicationStatus.BANK_REJECTED,
        ):
            _, ff_inbound = await BankRoutingService(audit=self.audit_service).get_flags(
                session, app.bank_id
            )
            if not ff_inbound:
                resolved = ApplicationStatus.CBS_PENDING_BANK_RELEASE

        ApplicationStateMachine.validate_transition(app.status, resolved)
        app.status = resolved

        target_sub = None
        for sub in app.submissions:
            if sub.bank_id == app.bank_id:
                target_sub = sub
                break

        if target_sub is None:
            bank_status = "pending"
            if resolved == ApplicationStatus.ACCOUNT_OPENED:
                bank_status = "opened"
            elif new_status == ApplicationStatus.BANK_REJECTED:
                bank_status = "rejected"
            target_sub = BankSubmission(
                application_id=app.id,
                bank_id=app.bank_id,
                account_number=account_number,
                bank_reference=bank_reference,
                bank_status=bank_status,
            )
            session.add(target_sub)
            app.submissions.append(target_sub)
        else:
            if account_number:
                target_sub.account_number = account_number
            if bank_reference:
                target_sub.bank_reference = bank_reference
            if resolved == ApplicationStatus.ACCOUNT_OPENED:
                target_sub.bank_status = "opened"
            elif new_status == ApplicationStatus.BANK_REJECTED:
                target_sub.bank_status = "rejected"
            elif resolved == ApplicationStatus.CBS_PENDING_BANK_RELEASE:
                if new_status == ApplicationStatus.BANK_REJECTED:
                    target_sub.bank_status = "rejected"
                elif account_number:
                    target_sub.bank_status = "opened_pending_release"

        await session.flush()

        await self.audit_service.record_event(
            session=session,
            actor_type="WORKER",
            actor_id=actor_id,
            action="STATUS_UPDATED",
            application_id=app.id,
            payload={
                "requested_status": new_status.value,
                "new_status": resolved.value,
                "account_number": account_number,
                "bank_reference": bank_reference,
            },
        )
        return app

    async def release_inbound(
        self,
        session: AsyncSession,
        application_id: uuid.UUID,
        *,
        release_status: ApplicationStatus,
        account_number: Optional[str] = None,
        bank_reference: Optional[str] = None,
        reject_reason: Optional[str] = None,
        edited_fields: Optional[Dict[str, Any]] = None,
        actor_id: str = "BANK",
    ) -> Application:
        """Staff releases a CBS result held in the inbound queue to the customer app."""
        if release_status not in (
            ApplicationStatus.ACCOUNT_OPENED,
            ApplicationStatus.BANK_REJECTED,
        ):
            raise StateGuardError(
                release_status,
                "Inbound release must be ACCOUNT_OPENED or BANK_REJECTED.",
            )
        app = await self.get_application(session, application_id, for_update=True)
        ApplicationStateMachine.validate_transition(app.status, release_status)
        if edited_fields:
            app.bank_edited_fields = {
                **(app.bank_edited_fields or {}),
                **edited_fields,
            }
        app.status = release_status
        for sub in app.submissions:
            if sub.bank_id != app.bank_id:
                continue
            if account_number:
                sub.account_number = account_number
            if bank_reference:
                sub.bank_reference = bank_reference
            if release_status == ApplicationStatus.ACCOUNT_OPENED:
                sub.bank_status = "opened"
            else:
                sub.bank_status = "rejected"
                if reject_reason:
                    sub.error_message = reject_reason
            break
        await self.audit_service.record_event(
            session=session,
            actor_type="BANK",
            actor_id=actor_id,
            action="INBOUND_RELEASED",
            application_id=app.id,
            payload={
                "bank_id": app.bank_id,
                "status": release_status.value,
                "account_number": account_number,
                "reject_reason": reject_reason,
            },
        )
        await session.flush()
        return app

    async def expire_inactive_applications(self, session: AsyncSession) -> int:
        """
        Background cleanup task (§9.1 CH-03):
        Identifies incomplete draft/in-progress applications past their expiration timestamp,
        transitions status to EXPIRED, cryptographically shreds ephemeral demographic snapshots,
        and records APPLICATION_EXPIRED audit logs.
        """
        now = utc_now()
        stmt = (
            select(Application)
            .options(selectinload(Application.identity_snapshot))
            .where(
                Application.expires_at < now,
                Application.status.notin_([
                    ApplicationStatus.ACCOUNT_OPENED,
                    ApplicationStatus.ACTIVATED,
                    ApplicationStatus.BANK_REJECTED,
                    ApplicationStatus.CANCELLED,
                    ApplicationStatus.EXPIRED,
                    ApplicationStatus.AWAITING_BANK_OUTBOUND,
                    ApplicationStatus.CBS_PENDING_BANK_RELEASE,
                    ApplicationStatus.SUBMITTED_TO_BANK,
                ]),
            )
        )
        expired_apps = (await session.execute(stmt)).scalars().all()
        count = 0
        for app in expired_apps:
            app.status = ApplicationStatus.EXPIRED
            # Cryptographic shredding of temporary identity artifacts
            if app.identity_snapshot:
                app.identity_snapshot.encrypted_full_name = b"SHREDDED"
                app.identity_snapshot.encrypted_dob = b"SHREDDED"
            await self.audit_service.record_event(
                session=session,
                actor_type="SYSTEM",
                actor_id="cleanup_daemon",
                action="APPLICATION_EXPIRED",
                application_id=app.id,
                payload={"reason": "INACTIVE_TTL_EXCEEDED", "expired_at": now.isoformat()},
            )
            count += 1
        await session.commit()
        return count

