"""Mobile UI module for eKYC Customer Onboarding Application."""

from src.ui.i18n import Locale, get_translation, SUPPORTED_LOCALES
from src.ui.consent import ConsentManager, ConsentState
from src.ui.fayda import FaydaInputValidator, OTPManager, OTPState
from src.ui.liveness import LivenessCaptureSession, LivenessState, ChallengeType
from src.ui.form_renderer import DynamicFormRenderer, FormField
from src.ui.app import MobileOnboardingCoordinator, Step

__all__ = [
    "Locale",
    "get_translation",
    "SUPPORTED_LOCALES",
    "ConsentManager",
    "ConsentState",
    "FaydaInputValidator",
    "OTPManager",
    "OTPState",
    "LivenessCaptureSession",
    "LivenessState",
    "ChallengeType",
    "DynamicFormRenderer",
    "FormField",
    "MobileOnboardingCoordinator",
    "Step",
]
