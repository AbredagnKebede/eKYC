from typing import Any, Dict, List, Optional, Set

from src.models.application import Application, ApplicationStatus, ConsentRecord, IdentitySnapshot


class StateMachineError(Exception):
    """Base exception for application state machine violations."""

    def __init__(self, message: str, status_code: int = 409, detail: Optional[str] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or message


class StateTransitionError(StateMachineError):
    """Raised when an illegal state transition is attempted."""

    def __init__(self, current_status: ApplicationStatus, target_status: ApplicationStatus) -> None:
        message = f"Illegal state transition from '{current_status.value}' to '{target_status.value}'."
        super().__init__(
            message,
            status_code=409,
            detail=message,
        )


class StateGuardError(StateMachineError):
    """Raised when transition precondition or invariant guard is not satisfied."""

    def __init__(self, target_status: ApplicationStatus, reason: str) -> None:
        message = f"Guard condition for state '{target_status.value}' failed: {reason}"
        super().__init__(
            message,
            status_code=422,
            detail=message,
        )


VALID_TRANSITIONS: Dict[ApplicationStatus, Set[ApplicationStatus]] = {
    ApplicationStatus.DRAFT: {
        ApplicationStatus.CONSENTED,
        ApplicationStatus.CANCELLED,
        ApplicationStatus.EXPIRED,
    },
    ApplicationStatus.CONSENTED: {
        ApplicationStatus.ID_VERIFIED,
        ApplicationStatus.ID_FAILED,
        ApplicationStatus.CANCELLED,
        ApplicationStatus.EXPIRED,
    },
    ApplicationStatus.ID_FAILED: {
        ApplicationStatus.ID_VERIFIED,
        ApplicationStatus.CANCELLED,
        ApplicationStatus.EXPIRED,
    },
    ApplicationStatus.ID_VERIFIED: {
        ApplicationStatus.LIVENESS_PASSED,
        ApplicationStatus.LIVENESS_FAILED,
        ApplicationStatus.CANCELLED,
        ApplicationStatus.EXPIRED,
    },
    ApplicationStatus.LIVENESS_FAILED: {
        ApplicationStatus.LIVENESS_PASSED,
        ApplicationStatus.CANCELLED,
        ApplicationStatus.EXPIRED,
    },
    ApplicationStatus.LIVENESS_PASSED: {
        ApplicationStatus.DATA_COMPLETE,
        ApplicationStatus.CANCELLED,
        ApplicationStatus.EXPIRED,
    },
    ApplicationStatus.DATA_COMPLETE: {
        ApplicationStatus.SUBMITTED_TO_BANK,
        ApplicationStatus.CANCELLED,
        ApplicationStatus.EXPIRED,
    },
    ApplicationStatus.SUBMITTED_TO_BANK: {
        ApplicationStatus.BANK_ACCEPTED,
        ApplicationStatus.BANK_REJECTED,
        ApplicationStatus.ACCOUNT_OPENED,
    },
    ApplicationStatus.BANK_ACCEPTED: {
        ApplicationStatus.ACCOUNT_OPENED,
        ApplicationStatus.BANK_REJECTED,
    },
    ApplicationStatus.ACCOUNT_OPENED: {
        ApplicationStatus.ACTIVATED,
    },
    ApplicationStatus.ACTIVATED: set(),
    ApplicationStatus.BANK_REJECTED: set(),
    ApplicationStatus.CANCELLED: set(),
    ApplicationStatus.EXPIRED: set(),
}


class ApplicationStateMachine:
    """Encapsulates state transition validation and domain invariant guards."""

    LIVENESS_THRESHOLD: float = 0.90
    SIMILARITY_THRESHOLD: float = 0.82

    @classmethod
    def can_transition(cls, current: ApplicationStatus, target: ApplicationStatus) -> bool:
        """Checks if a transition from current to target is allowed by the DAG."""
        return target in VALID_TRANSITIONS.get(current, set())

    @classmethod
    def validate_transition(cls, current: ApplicationStatus, target: ApplicationStatus) -> None:
        """Validates transition and raises StateTransitionError if prohibited."""
        if not cls.can_transition(current, target):
            raise StateTransitionError(current, target)

    @classmethod
    def check_consent_guard(cls, consents: List[ConsentRecord]) -> None:
        """Guard for CONSENTED: requires at least one recorded consent entry."""
        if not consents:
            raise StateGuardError(
                ApplicationStatus.CONSENTED,
                "No active consent record exists for this application.",
            )

    @classmethod
    def check_id_verified_guard(cls, snapshot: Optional[IdentitySnapshot]) -> None:
        """Guard for ID_VERIFIED: demographic record must exist and be hashed."""
        if not snapshot or not snapshot.fayda_ref_hash:
            raise StateGuardError(
                ApplicationStatus.ID_VERIFIED,
                "Missing verified citizen demographic snapshot or Fayda hash.",
            )

    @classmethod
    def check_liveness_guard(
        cls,
        liveness_score: float,
        face_similarity: float = 1.0,
    ) -> None:
        """Guard for LIVENESS_PASSED: scores must exceed anti-spoofing and match thresholds."""
        if liveness_score < cls.LIVENESS_THRESHOLD:
            raise StateGuardError(
                ApplicationStatus.LIVENESS_PASSED,
                f"Liveness score {liveness_score:.2f} is below anti-spoofing threshold ({cls.LIVENESS_THRESHOLD}).",
            )
        if face_similarity < cls.SIMILARITY_THRESHOLD:
            raise StateGuardError(
                ApplicationStatus.LIVENESS_PASSED,
                f"Face cosine similarity {face_similarity:.2f} is below identity threshold ({cls.SIMILARITY_THRESHOLD}).",
            )

    @classmethod
    def check_data_complete_guard(cls, dynamic_fields: Optional[Dict[str, Any]]) -> None:
        """Guard for DATA_COMPLETE: bank dynamic attributes must not be empty."""
        if not dynamic_fields or len(dynamic_fields) == 0:
            raise StateGuardError(
                ApplicationStatus.DATA_COMPLETE,
                "Dynamic bank intake form attributes cannot be empty.",
            )

    @classmethod
    def check_submission_guard(cls, signature: Optional[str]) -> None:
        """Guard for SUBMITTED_TO_BANK: digital touchscreen signature is mandatory."""
        if not signature or not signature.strip():
            raise StateGuardError(
                ApplicationStatus.SUBMITTED_TO_BANK,
                "Customer digital signature is required before bank submission.",
            )
