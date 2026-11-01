"""Consent management for mobile onboarding.

Handles explicit customer consent disclosure, device fingerprinting,
and state transition to CONSENTED or REFUSED.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any
import hashlib

from src.ui.i18n import Locale, get_translation


class ConsentState(str, Enum):
    PENDING = "PENDING"
    CONSENTED = "CONSENTED"
    REFUSED = "REFUSED"


@dataclass
class ConsentRecord:
    state: ConsentState
    consent_version: str
    locale: Locale
    accepted_at: Optional[datetime] = None
    refused_at: Optional[datetime] = None
    device_fingerprint: str = ""
    ip_address: str = "127.0.0.1"
    disclosures_acknowledged: list[str] = field(default_factory=list)


class ConsentManager:
    """Manages customer consent disclosure, recording, and refusal flows."""

    CURRENT_VERSION = "2026.1"

    def __init__(self, locale: Locale = Locale.EN, device_info: Optional[str] = None):
        self.locale = locale
        self.device_fingerprint = self._compute_fingerprint(device_info or "generic-mobile-android-arm64")
        self.record: Optional[ConsentRecord] = None

    @staticmethod
    def _compute_fingerprint(device_raw: str) -> str:
        return hashlib.sha256(f"dev-{device_raw}".encode()).hexdigest()[:32]

    def get_disclosure_text(self) -> Dict[str, str]:
        """Returns plain-language disclosure strings for the current locale."""
        return {
            "title": get_translation("consent.title", self.locale),
            "fayda_disclosure": get_translation("consent.disclosure_fayda", self.locale),
            "bank_disclosure": get_translation("consent.disclosure_bank", self.locale),
            "device_binding": get_translation("consent.device_binding", self.locale),
            "agree_label": get_translation("consent.btn_agree", self.locale),
            "refuse_label": get_translation("consent.btn_refuse", self.locale),
        }

    def record_consent(self, ip_address: str = "127.0.0.1") -> ConsentRecord:
        """User explicitly accepts consent terms."""
        now = datetime.now(timezone.utc)
        self.record = ConsentRecord(
            state=ConsentState.CONSENTED,
            consent_version=self.CURRENT_VERSION,
            locale=self.locale,
            accepted_at=now,
            device_fingerprint=self.device_fingerprint,
            ip_address=ip_address,
            disclosures_acknowledged=["fayda_npid", "bank_sharing", "device_binding"],
        )
        return self.record

    def record_refusal(self) -> ConsentRecord:
        """User refuses or declines consent terms."""
        now = datetime.now(timezone.utc)
        self.record = ConsentRecord(
            state=ConsentState.REFUSED,
            consent_version=self.CURRENT_VERSION,
            locale=self.locale,
            refused_at=now,
            device_fingerprint=self.device_fingerprint,
        )
        return self.record

    def to_api_payload(self) -> Dict[str, Any]:
        """Serializes consent record for the API gateway endpoint."""
        if not self.record or self.record.state != ConsentState.CONSENTED:
            raise ValueError("Cannot serialize unconsented record for API submission")
        return {
            "consent_version": self.record.consent_version,
            "device_fingerprint": self.record.device_fingerprint,
            "ip_address": self.record.ip_address,
            "accepted_at": self.record.accepted_at.isoformat() if self.record.accepted_at else None,
        }
