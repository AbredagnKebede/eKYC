"""Unit tests for Mobile Customer Onboarding UI application (§1)."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from src.ui.i18n import Locale, get_translation, SUPPORTED_LOCALES, LOCALE_NAMES
from src.ui.consent import ConsentManager, ConsentState
from src.ui.fayda import FaydaInputValidator, OTPManager, OTPState
from src.ui.liveness import LivenessCaptureSession, LivenessState, ChallengeType
from src.ui.form_renderer import DynamicFormRenderer, FieldType
from src.ui.app import MobileOnboardingCoordinator, Step


# ============================================================================
# 1. Localization & Multilingual Tests
# ============================================================================

def test_supported_locales_count_and_display_names():
    assert len(SUPPORTED_LOCALES) == 4
    assert Locale.EN in SUPPORTED_LOCALES
    assert Locale.AM in SUPPORTED_LOCALES
    assert Locale.OM in SUPPORTED_LOCALES
    assert Locale.TI in SUPPORTED_LOCALES

    assert LOCALE_NAMES[Locale.EN] == "English"
    assert LOCALE_NAMES[Locale.AM] == "አማርኛ"
    assert LOCALE_NAMES[Locale.OM] == "Afaan Oromoo"
    assert LOCALE_NAMES[Locale.TI] == "ትግርኛ"


def test_translation_retrieval_and_fallbacks():
    # English translation
    en_title = get_translation("app.title", Locale.EN)
    assert en_title == "Ethiopian eKYC Digital Bank Onboarding"

    # Amharic translation in Ge'ez script
    am_title = get_translation("app.title", Locale.AM)
    assert am_title == "የኢትዮጵያ ዲጂታል የባንክ አካውንት መክፈቻ"

    # Afaan Oromo translation
    om_title = get_translation("app.title", Locale.OM)
    assert om_title == "Baninsa Herrega Baankii Dijitaalaa Itoophiyaa"

    # Tigrinya translation in Ge'ez script
    ti_title = get_translation("app.title", Locale.TI)
    assert ti_title == "ናይ ኢትዮጵያ ዲጂታል ናይ ባንኪ ሒሳብ መኽፈቲ"

    # String locale coercion
    assert get_translation("app.title", "am") == am_title
    # Unknown locale falls back to English
    assert get_translation("app.title", "fr") == en_title

    # Fallback to key when translation missing completely
    missing = get_translation("non.existent.key", Locale.EN)
    assert missing == "non.existent.key"


def test_translation_parameter_interpolation():
    msg = get_translation("fayda.otp_timer", Locale.EN, seconds=45)
    assert msg == "Resend code in 45s"

    am_msg = get_translation("fayda.otp_timer", Locale.AM, seconds=30)
    assert am_msg == "ኮዱን በ30 ሰከንድ ውስጥ እንደገና ይላኩ"

    # Missing param leaves template unchanged
    fallback_msg = get_translation("fayda.otp_timer", Locale.EN)
    assert "{seconds}" in fallback_msg


# ============================================================================
# 2. Plain-Language Consent Screen Tests
# ============================================================================

def test_consent_manager_disclosure_text():
    mgr_en = ConsentManager(locale=Locale.EN)
    disc_en = mgr_en.get_disclosure_text()
    assert disc_en["title"] == "Consent to Identity Verification & Data Sharing"
    assert "EthSwitch VeriFayda" in disc_en["fayda_disclosure"]
    assert "commercial bank" in disc_en["bank_disclosure"]
    assert "fingerprint" in disc_en["device_binding"]
    assert disc_en["agree_label"] == "Agree & Continue"
    assert disc_en["refuse_label"] == "Decline & Exit"

    mgr_am = ConsentManager(locale=Locale.AM)
    disc_am = mgr_am.get_disclosure_text()
    assert disc_am["title"] == "የግል መረጃ ማረጋገጫ እና ማጋሪያ ስምምነት"
    assert "ተስማምቻለሁ፤ ይቀጥሉ" == disc_am["agree_label"]


def test_consent_manager_agree_flow():
    mgr = ConsentManager(locale=Locale.EN, device_info="pixel-7-android-14")
    assert len(mgr.device_fingerprint) == 32

    rec = mgr.record_consent(ip_address="196.188.42.10")
    assert rec.state == ConsentState.CONSENTED
    assert rec.consent_version == "2026.1"
    assert rec.ip_address == "196.188.42.10"
    assert rec.accepted_at is not None
    assert rec.refused_at is None
    assert "fayda_npid" in rec.disclosures_acknowledged

    payload = mgr.to_api_payload()
    assert payload["consent_version"] == "2026.1"
    assert payload["device_fingerprint"] == mgr.device_fingerprint
    assert payload["ip_address"] == "196.188.42.10"
    assert payload["accepted_at"] is not None


def test_consent_manager_refusal_flow():
    mgr = ConsentManager(locale=Locale.EN)
    rec = mgr.record_refusal()
    assert rec.state == ConsentState.REFUSED
    assert rec.refused_at is not None
    assert rec.accepted_at is None

    with pytest.raises(ValueError, match="Cannot serialize unconsented record"):
        mgr.to_api_payload()


# ============================================================================
# 3. Fayda FIN & OTP Verification Tests
# ============================================================================

def test_fayda_input_validator_formatting():
    # Raw FIN with spaces and dashes
    raw = " 1234-5678-9012 "
    cleaned = FaydaInputValidator.clean_fin(raw)
    assert cleaned == "123456789012"

    formatted = FaydaInputValidator.format_fin("123456789012")
    assert formatted == "1234 5678 9012"

    partial = FaydaInputValidator.format_fin("1234567")
    assert partial == "1234 567"


def test_fayda_input_validator_validation():
    # Valid 12 digits
    ok, err = FaydaInputValidator.validate_fin("123456789012", Locale.EN)
    assert ok is True
    assert err is None

    # Too short (11 digits)
    ok_short, err_short = FaydaInputValidator.validate_fin("12345678901", Locale.EN)
    assert ok_short is False
    assert err_short == "FIN must be exactly 12 numeric digits."

    # Non-numeric
    ok_alpha, err_alpha = FaydaInputValidator.validate_fin("12345678901A", Locale.EN)
    assert ok_alpha is False
    assert err_alpha == "FIN must be exactly 12 numeric digits."

    # Amharic error message
    ok_am, err_am = FaydaInputValidator.validate_fin("999", Locale.AM)
    assert ok_am is False
    assert err_am == "የፋይዳ ቁጥር በትክክል 12 የቁጥር አሃዞች መሆን አለበት።"


def test_otp_validator():
    ok, err = FaydaInputValidator.validate_otp("123456", Locale.EN)
    assert ok is True
    assert err is None

    ok_bad, err_bad = FaydaInputValidator.validate_otp("12345", Locale.EN)
    assert ok_bad is False
    assert err_bad == "OTP must be 6 numeric digits."


def test_otp_manager_challenge_lifecycle():
    otp_mgr = OTPManager(locale=Locale.EN, max_attempts=3)

    # Rejects invalid FIN
    ok_inv, msg_inv = otp_mgr.start_verification("123")
    assert ok_inv is False
    assert msg_inv == "FIN must be exactly 12 numeric digits."

    # Starts valid challenge
    ok, msg = otp_mgr.start_verification("123456789012")
    assert ok is True
    assert otp_mgr.current_challenge is not None
    assert otp_mgr.current_challenge.fin == "123456789012"
    assert otp_mgr.current_challenge.state == OTPState.CHALLENGE_ACTIVE

    # Cooldown timer
    remaining = otp_mgr.get_remaining_resend_seconds()
    assert 55 <= remaining <= 60

    # Resend denied during cooldown
    resend_ok, resend_msg = otp_mgr.resend_otp()
    assert resend_ok is False
    assert "Resend code in" in resend_msg

    # Resend allowed after simulated expiry
    otp_mgr.current_challenge.resend_available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    resend_after_ok, resend_after_msg = otp_mgr.resend_otp()
    assert resend_after_ok is True
    assert resend_after_msg == "OTP resent"

    # Valid OTP input
    verify_ok, verify_msg = otp_mgr.verify_otp_input("654321")
    assert verify_ok is True
    assert otp_mgr.current_challenge.otp_code == "654321"

    otp_mgr.mark_verified()
    assert otp_mgr.current_challenge.state == OTPState.VERIFIED

    # Check payload serialization
    start_payload = otp_mgr.to_start_api_payload()
    assert start_payload == {"fin": "123456789012"}

    verify_payload = otp_mgr.to_verify_api_payload()
    assert verify_payload == {"fin": "123456789012", "otp": "654321"}


def test_otp_manager_lockout_after_max_attempts():
    otp_mgr = OTPManager(locale=Locale.EN, max_attempts=3)
    otp_mgr.start_verification("123456789012")

    # Attempt 1 failed
    ok1, _ = otp_mgr.verify_otp_input("123")
    assert ok1 is False
    assert otp_mgr.current_challenge.attempts == 1
    assert otp_mgr.current_challenge.state == OTPState.CHALLENGE_ACTIVE

    # Attempt 2 failed
    ok2, _ = otp_mgr.verify_otp_input("abc")
    assert ok2 is False
    assert otp_mgr.current_challenge.attempts == 2

    # Attempt 3 failed -> lockout
    ok3, msg3 = otp_mgr.verify_otp_input("000")
    assert ok3 is False
    assert otp_mgr.current_challenge.attempts == 3
    assert otp_mgr.current_challenge.state == OTPState.LOCKED_OUT
    assert "temporarily locked" in msg3

    # Subsequent verification denied
    ok4, msg4 = otp_mgr.verify_otp_input("123456")
    assert ok4 is False
    assert "temporarily locked" in msg4


# ============================================================================
# 4. Facial Liveness & Camera Frame Capture Tests
# ============================================================================

def test_liveness_session_lifecycle():
    session = LivenessCaptureSession(locale=Locale.EN, challenge=ChallengeType.BLINK)
    assert session.state == LivenessState.IDLE
    assert "Center your face inside the oval frame" in session.get_current_instruction()

    session.start_camera()
    assert session.state == LivenessState.ALIGNING

    session.advance_to_challenge()
    assert session.state == LivenessState.CHALLENGING
    assert "blink your eyes" in session.get_current_instruction()

    # Capture selfie
    fake_frame = b"\xff\xd8\xff\xe0JFIF" + b"\x00" * 32
    b64 = session.capture_selfie(fake_frame)
    assert session.state == LivenessState.CAPTURED
    assert len(b64) > 10
    assert len(session.frames) == 1
    assert session.frames[0].is_keyframe is True

    # High score pass
    pass_ok, pass_msg = session.complete_liveness(score=0.97)
    assert pass_ok is True
    assert session.state == LivenessState.PASSED
    assert "0.97" in pass_msg

    # API payload
    payload = session.to_api_payload()
    assert payload["selfie_base64"] == b64
    assert payload["challenge_type"] == "BLINK"
    assert payload["frame_count"] == 1

    # Zero-retention biometrics purge
    session.purge_biometrics()
    assert len(session.frames) == 0
    assert session.captured_selfie_b64 is None


def test_liveness_session_spoof_failure():
    session = LivenessCaptureSession(locale=Locale.EN)
    session.start_camera()
    session.capture_selfie(b"fake-bytes")

    fail_ok, fail_msg = session.complete_liveness(score=0.42)
    assert fail_ok is False
    assert session.state == LivenessState.FAILED
    assert "Spoof" in fail_msg


def test_liveness_instructions_localized():
    for loc, expected_word in [
        (Locale.AM, "ዓይንዎን"),
        (Locale.OM, "sassaabaa"),
        (Locale.TI, "ኣርግብግቡ"),
    ]:
        s = LivenessCaptureSession(locale=loc, challenge=ChallengeType.BLINK)
        s.advance_to_challenge()
        assert expected_word in s.get_current_instruction()


# ============================================================================
# 5. Dynamic Form Renderer Tests
# ============================================================================

def test_dynamic_form_renderer_schema_parsing():
    schema = {
        "title": "Awash KYC",
        "required": ["mother_maiden_name", "tier", "age"],
        "properties": {
            "mother_maiden_name": {
                "type": "string",
                "title": "Mother's Maiden Name",
                "minLength": 3,
                "maxLength": 50,
            },
            "tier": {
                "type": "string",
                "enum": ["Standard", "Premier"],
            },
            "age": {
                "type": "integer",
                "title": "Customer Age",
            },
            "tin_number": {
                "type": "string",
                "pattern": r"^\d{10}$",
                "description": "Optional 10-digit TIN",
            },
        },
    }

    renderer = DynamicFormRenderer(schema, Locale.EN)
    assert len(renderer.fields) == 4
    assert renderer.fields["mother_maiden_name"].field_type == FieldType.TEXT
    assert renderer.fields["mother_maiden_name"].required is True
    assert renderer.fields["tier"].field_type == FieldType.SELECT
    assert renderer.fields["tier"].options == ["Standard", "Premier"]
    assert renderer.fields["age"].field_type == FieldType.NUMBER
    assert renderer.fields["tin_number"].required is False


def test_dynamic_form_renderer_validation():
    schema = {
        "required": ["full_address", "account_tier", "tin"],
        "properties": {
            "full_address": {"type": "string", "minLength": 5},
            "account_tier": {"type": "string", "enum": ["Silver", "Gold"]},
            "tin": {"type": "string", "pattern": r"^\d{10}$"},
        },
    }

    renderer = DynamicFormRenderer(schema, Locale.EN)

    # Initial state fails because required fields are empty
    valid, errors = renderer.validate_all()
    assert valid is False
    assert "full_address" in errors
    assert "account_tier" in errors

    # Set invalid values
    renderer.set_value("full_address", "Addis")  # Length 5 == minLength 5 -> OK
    renderer.set_value("account_tier", "Platinum")  # Not in enum -> Fail
    renderer.set_value("tin", "12345")  # Not 10 digits -> Fail

    valid2, errors2 = renderer.validate_all()
    assert valid2 is False
    assert "account_tier" in errors2
    assert "tin" in errors2
    assert "full_address" not in errors2

    # Set all valid values
    renderer.set_value("account_tier", "Gold")
    renderer.set_value("tin", "1234567890")

    valid3, errors3 = renderer.validate_all()
    assert valid3 is True
    assert len(errors3) == 0

    values = renderer.get_form_values()
    assert values["full_address"] == "Addis"
    assert values["account_tier"] == "Gold"
    assert values["tin"] == "1234567890"


# ============================================================================
# 6. End-to-End Mobile Onboarding Coordinator Tests
# ============================================================================

def test_mobile_coordinator_full_successful_flow():
    coord = MobileOnboardingCoordinator(locale=Locale.EN, device_info="samsung-galaxy-s23")
    assert coord.step == Step.SELECT_BANK
    assert len(coord.available_banks) >= 2

    # 1. Select Awash Bank
    ok_bank, _ = coord.select_bank("awash", "standard")
    assert ok_bank is True
    assert coord.step == Step.CONSENT
    assert coord.draft.bank_id == "awash"

    # 2. Grant Consent
    ok_consent, _ = coord.handle_consent(agreed=True)
    assert ok_consent is True
    assert coord.step == Step.FAYDA_FIN
    assert coord.consent_manager.record.state == ConsentState.CONSENTED

    # 3. Enter 12-digit Fayda FIN
    ok_fin, _ = coord.submit_fayda_fin("123456789012")
    assert ok_fin is True
    assert coord.step == Step.OTP_VERIFY
    assert coord.draft.fin == "123456789012"

    # 4. Verify 6-digit OTP
    ok_otp, _ = coord.submit_otp("654321")
    assert ok_otp is True
    assert coord.step == Step.LIVENESS
    assert coord.liveness_session.state == LivenessState.ALIGNING
    assert coord.draft.demographics["full_name"] == "Abebe Kebede Bikila"

    # 5. Capture Selfie & Pass Liveness
    ok_live, _ = coord.complete_liveness_check(b"valid-jpeg-bytes")
    assert ok_live is True
    assert coord.step == Step.DYNAMIC_FIELDS

    # 6. Fill Bank Dynamic Fields
    ok_fields, _ = coord.submit_dynamic_fields({
        "mother_maiden_name": "Almaz Bekele",
        "occupation": "Employed",
        "tin_number": "1234567890",
    })
    assert ok_fields is True
    assert coord.step == Step.SIGNATURE
    assert coord.draft.dynamic_values["mother_maiden_name"] == "Almaz Bekele"

    # 7. Submit Signature
    ok_sig, _ = coord.submit_signature("Digital Signature: Abebe Kebede Bikila (Accepted)")
    assert ok_sig is True
    assert coord.step == Step.SUBMITTED
    assert coord.draft.signature_base64 is not None

    # Check packaged API payload
    submit_payload = coord.to_submit_api_payload()
    assert submit_payload["bank_id"] == "awash"
    assert submit_payload["tier"] == "standard"
    assert submit_payload["dynamic_fields"]["occupation"] == "Employed"

    # 8. Record CBS account issuance
    coord.record_bank_issuance(account_number="AWASH-100293847", bank_reference="CBS-TXN-984712")
    assert coord.draft.account_number == "AWASH-100293847"
    assert coord.draft.bank_reference == "CBS-TXN-984712"
    # Biometric buffers purged
    assert len(coord.liveness_session.frames) == 0


def test_mobile_coordinator_consent_refusal():
    coord = MobileOnboardingCoordinator(locale=Locale.EN)
    coord.select_bank("awash", "standard")

    # User declines consent
    ok, msg = coord.handle_consent(agreed=False)
    assert ok is False
    assert coord.step == Step.REFUSED
    assert "Consent was declined" in msg

    # Cannot proceed to FIN from REFUSED
    ok_fin, _ = coord.submit_fayda_fin("123456789012")
    assert ok_fin is False


def test_mobile_coordinator_language_switch():
    coord = MobileOnboardingCoordinator(locale=Locale.EN)
    assert coord.consent_manager.locale == Locale.EN

    coord.set_locale(Locale.AM)
    assert coord.locale == Locale.AM
    assert coord.consent_manager.locale == Locale.AM
    assert coord.otp_manager.locale == Locale.AM
    assert coord.liveness_session.locale == Locale.AM


def test_mobile_coordinator_invalid_bank_and_signature():
    coord = MobileOnboardingCoordinator(locale=Locale.EN)

    # Invalid bank
    ok_bad_bank, msg_bad = coord.select_bank("nonexistent_bank")
    assert ok_bad_bank is False
    assert "not recognized" in msg_bad

    # Invalid tier
    ok_bad_tier, msg_tier = coord.select_bank("awash", "gold_diamond")
    assert ok_bad_tier is False
    assert "not supported" in msg_tier

    # Signature validation when empty
    coord.step = Step.SIGNATURE
    ok_sig_empty, msg_sig = coord.submit_signature("")
    assert ok_sig_empty is False
    assert "valid signature" in msg_sig
