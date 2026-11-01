"""Fayda Identity Input & OTP Verification Engine for Mobile Client."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Tuple, Dict, Any

from src.ui.i18n import Locale, get_translation


class OTPState(str, Enum):
    IDLE = "IDLE"
    REQUESTING = "REQUESTING"
    CHALLENGE_ACTIVE = "CHALLENGE_ACTIVE"
    VERIFIED = "VERIFIED"
    LOCKED_OUT = "LOCKED_OUT"


class FaydaInputValidator:
    """Validates and formats 12-digit Ethiopian Fayda FIN / FAN identifiers."""

    FIN_REGEX = re.compile(r"^\d{12}$")
    OTP_REGEX = re.compile(r"^\d{6}$")

    @classmethod
    def clean_fin(cls, raw: str) -> str:
        """Strip non-numeric characters (spaces, dashes)."""
        return re.sub(r"\D", "", raw)

    @classmethod
    def format_fin(cls, raw: str) -> str:
        """Format 12-digit FIN as 'XXXX XXXX XXXX'."""
        cleaned = cls.clean_fin(raw)[:12]
        groups = [cleaned[i : i + 4] for i in range(0, len(cleaned), 4) if cleaned[i : i + 4]]
        return " ".join(groups)

    @classmethod
    def validate_fin(cls, raw: str, locale: Locale = Locale.EN) -> Tuple[bool, Optional[str]]:
        cleaned = cls.clean_fin(raw)
        if not cls.FIN_REGEX.match(cleaned):
            return False, get_translation("fayda.err_invalid_fin", locale)
        return True, None

    @classmethod
    def validate_otp(cls, raw: str, locale: Locale = Locale.EN) -> Tuple[bool, Optional[str]]:
        cleaned = re.sub(r"\D", "", raw)
        if not cls.OTP_REGEX.match(cleaned):
            return False, get_translation("fayda.err_invalid_otp", locale)
        return True, None


@dataclass
class OTPChallenge:
    fin: str
    state: OTPState = OTPState.IDLE
    otp_code: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    resend_available_at: Optional[datetime] = None
    attempts: int = 0
    max_attempts: int = 3
    cool_down_seconds: int = 60


class OTPManager:
    """Orchestrates OTP dispatch, countdown timers, and client-side retry guards."""

    def __init__(self, locale: Locale = Locale.EN, max_attempts: int = 3):
        self.locale = locale
        self.max_attempts = max_attempts
        self.current_challenge: Optional[OTPChallenge] = None

    def start_verification(self, fin_raw: str) -> Tuple[bool, str]:
        """Initiate OTP challenge for given FIN."""
        valid, err = FaydaInputValidator.validate_fin(fin_raw, self.locale)
        if not valid or err:
            return False, err or "Invalid FIN"

        cleaned_fin = FaydaInputValidator.clean_fin(fin_raw)
        now = datetime.now(timezone.utc)
        self.current_challenge = OTPChallenge(
            fin=cleaned_fin,
            state=OTPState.CHALLENGE_ACTIVE,
            created_at=now,
            expires_at=now + timedelta(minutes=5),
            resend_available_at=now + timedelta(seconds=60),
            attempts=0,
            max_attempts=self.max_attempts,
        )
        return True, get_translation("fayda.otp_label", self.locale)

    def get_remaining_resend_seconds(self) -> int:
        """Seconds left before customer can tap 'Resend OTP'."""
        if not self.current_challenge or not self.current_challenge.resend_available_at:
            return 0
        now = datetime.now(timezone.utc)
        remaining = (self.current_challenge.resend_available_at - now).total_seconds()
        return max(0, int(remaining))

    def resend_otp(self) -> Tuple[bool, str]:
        """Resend OTP if cooldown has elapsed and not locked out."""
        if not self.current_challenge:
            return False, "No active challenge"
        if self.current_challenge.state == OTPState.LOCKED_OUT:
            return False, get_translation("fayda.err_lockout", self.locale)

        remaining = self.get_remaining_resend_seconds()
        if remaining > 0:
            return False, get_translation("fayda.otp_timer", self.locale, seconds=remaining)

        now = datetime.now(timezone.utc)
        self.current_challenge.created_at = now
        self.current_challenge.expires_at = now + timedelta(minutes=5)
        self.current_challenge.resend_available_at = now + timedelta(seconds=60)
        return True, "OTP resent"

    def verify_otp_input(self, otp_raw: str) -> Tuple[bool, str]:
        """Validate format and record attempt."""
        if not self.current_challenge:
            return False, "No active challenge"
        if self.current_challenge.state == OTPState.LOCKED_OUT:
            return False, get_translation("fayda.err_lockout", self.locale)

        valid, err = FaydaInputValidator.validate_otp(otp_raw, self.locale)
        if not valid or err:
            self.current_challenge.attempts += 1
            if self.current_challenge.attempts >= self.current_challenge.max_attempts:
                self.current_challenge.state = OTPState.LOCKED_OUT
                return False, get_translation("fayda.err_lockout", self.locale)
            return False, err or "Invalid OTP"

        self.current_challenge.otp_code = re.sub(r"\D", "", otp_raw)
        return True, "Valid OTP format"

    def mark_verified(self) -> None:
        if self.current_challenge:
            self.current_challenge.state = OTPState.VERIFIED

    def to_start_api_payload(self) -> Dict[str, Any]:
        if not self.current_challenge:
            raise ValueError("No active challenge")
        return {"fin": self.current_challenge.fin}

    def to_verify_api_payload(self) -> Dict[str, Any]:
        if not self.current_challenge or not self.current_challenge.otp_code:
            raise ValueError("No verified OTP code present")
        return {
            "fin": self.current_challenge.fin,
            "otp": self.current_challenge.otp_code,
        }
