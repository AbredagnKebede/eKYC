import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest

from src.models.application import (
    Application,
    ApplicationStatus,
    ConsentRecord,
    IdentitySnapshot,
    VerificationMethod,
)
from src.services.onboarding import ApplicationNotFoundError, OnboardingService
from src.state.machine import (
    ApplicationStateMachine,
    StateGuardError,
    StateTransitionError,
    VALID_TRANSITIONS,
)


def test_state_machine_valid_and_invalid_transitions() -> None:
    # 1. Valid transitions
    assert ApplicationStateMachine.can_transition(ApplicationStatus.DRAFT, ApplicationStatus.CONSENTED) is True
    assert ApplicationStateMachine.can_transition(ApplicationStatus.CONSENTED, ApplicationStatus.ID_VERIFIED) is True
    assert ApplicationStateMachine.can_transition(ApplicationStatus.ID_FAILED, ApplicationStatus.ID_VERIFIED) is True
    assert ApplicationStateMachine.can_transition(ApplicationStatus.ID_VERIFIED, ApplicationStatus.LIVENESS_PASSED) is True
    assert ApplicationStateMachine.can_transition(ApplicationStatus.LIVENESS_FAILED, ApplicationStatus.LIVENESS_PASSED) is True
    assert ApplicationStateMachine.can_transition(ApplicationStatus.LIVENESS_PASSED, ApplicationStatus.DATA_COMPLETE) is True
    assert ApplicationStateMachine.can_transition(ApplicationStatus.DATA_COMPLETE, ApplicationStatus.SUBMITTED_TO_BANK) is True
    assert ApplicationStateMachine.can_transition(ApplicationStatus.SUBMITTED_TO_BANK, ApplicationStatus.ACCOUNT_OPENED) is True
    assert ApplicationStateMachine.can_transition(ApplicationStatus.ACCOUNT_OPENED, ApplicationStatus.ACTIVATED) is True

    # 2. Illegal backwards and skip transitions
    assert ApplicationStateMachine.can_transition(ApplicationStatus.DRAFT, ApplicationStatus.DATA_COMPLETE) is False
    assert ApplicationStateMachine.can_transition(ApplicationStatus.CONSENTED, ApplicationStatus.SUBMITTED_TO_BANK) is False
    assert ApplicationStateMachine.can_transition(ApplicationStatus.ACTIVATED, ApplicationStatus.DRAFT) is False

    with pytest.raises(StateTransitionError) as exc_trans:
        ApplicationStateMachine.validate_transition(ApplicationStatus.DRAFT, ApplicationStatus.SUBMITTED_TO_BANK)
    assert exc_trans.value.status_code == 409
    assert "Illegal state transition" in str(exc_trans.value)


def test_state_machine_guards() -> None:
    # 1. Consent guard
    with pytest.raises(StateGuardError) as exc_consent:
        ApplicationStateMachine.check_consent_guard([])
    assert exc_consent.value.status_code == 422
    assert "No active consent record exists" in str(exc_consent.value)

    # 2. ID verified guard
    with pytest.raises(StateGuardError) as exc_id:
        ApplicationStateMachine.check_id_verified_guard(None)
    assert "Missing verified citizen demographic" in str(exc_id.value)

    # 3. Liveness guard (spoof score fail)
    with pytest.raises(StateGuardError) as exc_live:
        ApplicationStateMachine.check_liveness_guard(liveness_score=0.85, face_similarity=0.95)
    assert "below anti-spoofing threshold" in str(exc_live.value)

    # 4. Liveness guard (face similarity fail)
    with pytest.raises(StateGuardError) as exc_sim:
        ApplicationStateMachine.check_liveness_guard(liveness_score=0.95, face_similarity=0.75)
    assert "below identity threshold" in str(exc_sim.value)

    # 5. Data complete guard
    with pytest.raises(StateGuardError) as exc_data:
        ApplicationStateMachine.check_data_complete_guard({})
    assert "cannot be empty" in str(exc_data.value)

    # 6. Submission guard
    with pytest.raises(StateGuardError) as exc_sig:
        ApplicationStateMachine.check_submission_guard("   ")
    assert "signature is required" in str(exc_sig.value)


@pytest.mark.asyncio
async def test_onboarding_service_lifecycle_unit() -> None:
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_audit = MagicMock()
    mock_audit.record_event = AsyncMock()
    mock_queue = MagicMock()
    mock_queue.enqueue = AsyncMock(return_value="msg_123")

    service = OnboardingService(audit_service=mock_audit, queue=mock_queue)

    # 1. Create application
    app = await service.create_application(
        session=mock_session,
        user_ref="user_123",
        bank_id="bank_awash",
        tier="standard",
    )
    assert app.user_ref == "user_123"
    assert app.bank_id == "bank_awash"
    assert app.status == ApplicationStatus.DRAFT
    mock_audit.record_event.assert_awaited()

    # 2. Mock get_application for subsequent steps
    service.get_application = AsyncMock(return_value=app)  # type: ignore

    # 3. Record consent
    app = await service.record_consent(
        session=mock_session,
        application_id=app.id,
        consent_version="v1.0",
        ip_address="196.188.1.1",
        device_fingerprint="device_hash_123",
    )
    assert app.status == ApplicationStatus.CONSENTED
    assert len(app.consents) == 1

    # 4. Attach identity snapshot
    snapshot = IdentitySnapshot(
        application_id=app.id,
        encrypted_full_name=b"enc_name",
        encrypted_dob=b"enc_dob",
        gender="MALE",
        fayda_ref_hash="salted_hash_999",
        liveness_score=0.0,
        verification_method=VerificationMethod.OTP,
    )
    app = await service.attach_identity_snapshot(
        session=mock_session,
        application_id=app.id,
        snapshot=snapshot,
    )
    assert app.status == ApplicationStatus.ID_VERIFIED
    assert app.identity_snapshot is not None

    # 5. Record liveness (pass)
    app = await service.record_liveness(
        session=mock_session,
        application_id=app.id,
        liveness_score=0.96,
        face_similarity=0.91,
    )
    assert app.status == ApplicationStatus.LIVENESS_PASSED
    assert app.identity_snapshot.liveness_score == 0.96

    # 6. Save dynamic fields
    dynamic_fields = {
        "monthly_income_etb": 35000,
        "occupation": "Accountant",
        "source_of_funds": "Salary",
    }
    app = await service.save_dynamic_fields(
        session=mock_session,
        application_id=app.id,
        dynamic_fields=dynamic_fields,
    )
    assert app.status == ApplicationStatus.DATA_COMPLETE
    assert len(app.submissions) == 1
    assert app.submissions[0].dynamic_fields == dynamic_fields

    # 7. Submit application
    app = await service.submit_application(
        session=mock_session,
        application_id=app.id,
        signature="data:image/png;base64,mockSignatureBlob",
    )
    assert app.status == ApplicationStatus.SUBMITTED_TO_BANK
    assert app.idempotency_hash is not None
    mock_queue.enqueue.assert_awaited_once()

    # 8. Update bank status (open account)
    app = await service.update_bank_status(
        session=mock_session,
        application_id=app.id,
        new_status=ApplicationStatus.ACCOUNT_OPENED,
        account_number="1000123456789",
        bank_reference="AWASH-CBS-1234",
    )
    assert app.status == ApplicationStatus.ACCOUNT_OPENED
    assert app.submissions[0].account_number == "1000123456789"
    assert app.submissions[0].bank_reference == "AWASH-CBS-1234"


@pytest.mark.asyncio
async def test_onboarding_service_not_found() -> None:
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    service = OnboardingService()
    non_existent_id = uuid.uuid4()

    with pytest.raises(ApplicationNotFoundError) as exc_info:
        await service.get_application(mock_session, non_existent_id)
    assert exc_info.value.status_code == 404
    assert str(non_existent_id) in exc_info.value.detail
