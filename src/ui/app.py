"""Mobile Application Flow Coordinator.

Orchestrates the entire multi-step onboarding journey on the client side:
Bank Selection -> Plain-Language Consent -> Fayda FIN -> OTP Verification ->
Liveness -> Dynamic Bank Fields -> Digital Signature -> Core Banking Submission.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple

from src.ui.i18n import Locale, get_translation
from src.ui.consent import ConsentManager, ConsentState
from src.ui.fayda import OTPManager, OTPState
from src.ui.liveness import LivenessCaptureSession, LivenessState
from src.ui.form_renderer import DynamicFormRenderer


class Step(str, Enum):
    SELECT_BANK = "SELECT_BANK"
    CONSENT = "CONSENT"
    FAYDA_FIN = "FAYDA_FIN"
    OTP_VERIFY = "OTP_VERIFY"
    LIVENESS = "LIVENESS"
    DYNAMIC_FIELDS = "DYNAMIC_FIELDS"
    SIGNATURE = "SIGNATURE"
    SUBMITTED = "SUBMITTED"
    REFUSED = "REFUSED"


@dataclass
class BankOption:
    bank_id: str
    name: str
    supported_tiers: List[str]
    dynamic_schema: Dict[str, Any]


@dataclass
class ApplicationDraft:
    application_id: Optional[str] = None
    bank_id: Optional[str] = None
    tier: str = "standard"
    user_ref: str = "dev-client-uuid-001"
    fin: Optional[str] = None
    demographics: Dict[str, Any] = field(default_factory=dict)
    dynamic_values: Dict[str, Any] = field(default_factory=dict)
    signature_base64: Optional[str] = None
    account_number: Optional[str] = None
    bank_reference: Optional[str] = None


class MobileOnboardingCoordinator:
    """End-to-end client onboarding state coordinator."""

    def __init__(self, locale: Locale = Locale.EN, device_info: str = "android-arm64"):
        self.locale = locale
        self.step: Step = Step.SELECT_BANK
        self.draft = ApplicationDraft()
        self.consent_manager = ConsentManager(locale=locale, device_info=device_info)
        self.otp_manager = OTPManager(locale=locale)
        self.liveness_session = LivenessCaptureSession(locale=locale)
        self.form_renderer: Optional[DynamicFormRenderer] = None
        self.available_banks: List[BankOption] = self._default_bank_options()

    def set_locale(self, locale: Locale) -> None:
        """Switch active language dynamically across all active sub-components."""
        self.locale = locale
        self.consent_manager.locale = locale
        self.otp_manager.locale = locale
        self.liveness_session.locale = locale
        if self.form_renderer:
            self.form_renderer.locale = locale

    @staticmethod
    def _default_bank_options() -> List[BankOption]:
        return [
            BankOption(
                bank_id="awash",
                name="Awash Bank",
                supported_tiers=["standard", "premier"],
                dynamic_schema={
                    "type": "object",
                    "required": ["mother_maiden_name", "occupation"],
                    "properties": {
                        "mother_maiden_name": {
                            "type": "string",
                            "title": "Mother's Maiden Name",
                            "minLength": 2,
                            "maxLength": 60,
                        },
                        "occupation": {
                            "type": "string",
                            "title": "Occupation / Line of Work",
                            "enum": ["Employed", "Self-Employed", "Student", "Merchant"],
                        },
                        "tin_number": {
                            "type": "string",
                            "title": "Tax Identification Number (TIN)",
                            "pattern": r"^\d{10}$",
                            "description": "Optional 10-digit TIN",
                        },
                    },
                },
            ),
            BankOption(
                bank_id="cbe",
                name="Commercial Bank of Ethiopia (CBE)",
                supported_tiers=["standard", "interest_free"],
                dynamic_schema={
                    "type": "object",
                    "required": ["branch_preference"],
                    "properties": {
                        "branch_preference": {
                            "type": "string",
                            "title": "Preferred Branch Location",
                            "minLength": 3,
                        }
                    },
                },
            ),
        ]

    # ---- Navigation & State Machine Transitions ----

    def select_bank(self, bank_id: str, tier: str = "standard") -> Tuple[bool, str]:
        bank = next((b for b in self.available_banks if b.bank_id == bank_id), None)
        if not bank:
            return False, f"Bank {bank_id} not recognized"
        if tier not in bank.supported_tiers:
            return False, f"Tier {tier} not supported by {bank.name}"

        self.draft.bank_id = bank_id
        self.draft.tier = tier
        self.form_renderer = DynamicFormRenderer(bank.dynamic_schema, self.locale)
        self.step = Step.CONSENT
        return True, "Bank selected"

    def handle_consent(self, agreed: bool) -> Tuple[bool, str]:
        if agreed:
            self.consent_manager.record_consent()
            self.step = Step.FAYDA_FIN
            return True, "Consent recorded"
        else:
            self.consent_manager.record_refusal()
            self.step = Step.REFUSED
            return False, get_translation("consent.refusal_notice", self.locale)

    def submit_fayda_fin(self, fin_raw: str) -> Tuple[bool, str]:
        if self.step != Step.FAYDA_FIN:
            return False, f"Invalid step transition from {self.step}"
        ok, msg = self.otp_manager.start_verification(fin_raw)
        if ok:
            self.draft.fin = self.otp_manager.current_challenge.fin if self.otp_manager.current_challenge else None
            self.step = Step.OTP_VERIFY
        return ok, msg

    def submit_otp(self, otp_raw: str) -> Tuple[bool, str]:
        if self.step != Step.OTP_VERIFY:
            return False, f"Invalid step transition from {self.step}"
        ok, msg = self.otp_manager.verify_otp_input(otp_raw)
        if ok:
            self.otp_manager.mark_verified()
            self.draft.demographics = {
                "full_name": "Abebe Kebede Bikila",
                "dob": "1992-04-18",
                "gender": "M",
            }
            self.step = Step.LIVENESS
            self.liveness_session.start_camera()
        return ok, msg

    def complete_liveness_check(self, raw_jpeg_bytes: Optional[bytes] = None) -> Tuple[bool, str]:
        if self.step != Step.LIVENESS:
            return False, f"Invalid step transition from {self.step}"
        self.liveness_session.advance_to_challenge()
        self.liveness_session.capture_selfie(raw_jpeg_bytes)
        ok, msg = self.liveness_session.complete_liveness(score=0.95)
        if ok:
            self.step = Step.DYNAMIC_FIELDS
        return ok, msg

    def submit_dynamic_fields(self, field_values: Dict[str, Any]) -> Tuple[bool, str]:
        if self.step != Step.DYNAMIC_FIELDS:
            return False, f"Invalid step transition from {self.step}"
        if not self.form_renderer:
            return False, "Form renderer uninitialized"

        for k, v in field_values.items():
            self.form_renderer.set_value(k, v)

        ok, errors = self.form_renderer.validate_all()
        if not ok:
            return False, f"Validation errors: {errors}"

        self.draft.dynamic_values = self.form_renderer.get_form_values()
        self.step = Step.SIGNATURE
        return True, "Fields validated"

    def submit_signature(self, signature_b64_or_bytes: Any) -> Tuple[bool, str]:
        if self.step != Step.SIGNATURE:
            return False, f"Invalid step transition from {self.step}"

        if isinstance(signature_b64_or_bytes, bytes):
            sig_b64 = base64.b64encode(signature_b64_or_bytes).decode("utf-8")
        elif isinstance(signature_b64_or_bytes, str) and len(signature_b64_or_bytes) > 10:
            sig_b64 = signature_b64_or_bytes
        else:
            return False, get_translation("signature.err_empty", self.locale)

        self.draft.signature_base64 = sig_b64
        self.step = Step.SUBMITTED
        return True, "Application packaged for CBS submission"

    def record_bank_issuance(self, account_number: str, bank_reference: str) -> None:
        self.draft.account_number = account_number
        self.draft.bank_reference = bank_reference
        # Purge biometric buffers upon bank confirmation
        self.liveness_session.purge_biometrics()

    def to_submit_api_payload(self) -> Dict[str, Any]:
        """Packages full payload for POST /v1/applications/{id}/submit."""
        if not self.draft.signature_base64:
            raise ValueError("Signature required for submission")
        return {
            "signature_base64": self.draft.signature_base64,
            "bank_id": self.draft.bank_id,
            "tier": self.draft.tier,
            "dynamic_fields": self.draft.dynamic_values,
        }
