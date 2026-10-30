import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_event_signature(secret_key: str, payload: Dict[str, Any]) -> str:
    """Computes deterministic HMAC-SHA256 hexadecimal signature over canonical JSON."""
    clean_dict = {k: v for k, v in payload.items() if k != "payload_signature"}
    canonical_json = json.dumps(clean_dict, sort_keys=True, default=str)
    return hmac.new(
        secret_key.encode("utf-8"),
        canonical_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_event_signature(secret_key: str, payload: Dict[str, Any], signature: str) -> bool:
    """Verifies HMAC-SHA256 signature using constant-time comparison."""
    expected = compute_event_signature(secret_key, payload)
    return hmac.compare_digest(expected, signature)


class ApplicationSubmittedEvent(BaseModel):
    """Event contract published when a customer finalizes and signs an application."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    event_name: Literal["application_submitted_event"] = "application_submitted_event"
    application_id: str = Field(..., description="UUID identifying the application session")
    bank_id: str = Field(..., min_length=2, description="Target commercial partner bank ID")
    timestamp: str = Field(default_factory=utc_now_iso, description="ISO 8601 UTC event timestamp")
    payload_signature: str = Field(..., min_length=16, description="Cryptographic HMAC-SHA256 signature")
    tier: str = Field(default="standard", description="Account tier selected by applicant")
    idempotency_key: Optional[str] = Field(default=None, description="Unique idempotency deduplication key")
    dynamic_fields: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Bank-specific dynamic attributes")

    @field_validator("application_id")
    @classmethod
    def validate_uuid_format(cls, v: str) -> str:
        try:
            return str(uuid.UUID(str(v)))
        except (ValueError, AttributeError):
            raise ValueError(f"application_id must be a valid UUID string, got: '{v}'")

    @field_validator("timestamp")
    @classmethod
    def validate_iso_timestamp(cls, v: str) -> str:
        try:
            # Validate parsing
            datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return str(v)
        except Exception:
            raise ValueError(f"timestamp must be a valid ISO 8601 datetime string, got: '{v}'")

    def verify_signature(self, secret_key: str) -> bool:
        """Verifies this event's signature against the provided secret key."""
        return verify_event_signature(secret_key, self.model_dump(), self.payload_signature)

    @classmethod
    def create(
        cls,
        application_id: str,
        bank_id: str,
        secret_key: str,
        tier: str = "standard",
        idempotency_key: Optional[str] = None,
        dynamic_fields: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> "ApplicationSubmittedEvent":
        """Factory creating and signing an ApplicationSubmittedEvent."""
        event_dict: Dict[str, Any] = {
            "event_name": "application_submitted_event",
            "application_id": str(uuid.UUID(str(application_id))),
            "bank_id": bank_id,
            "timestamp": timestamp or utc_now_iso(),
            "tier": tier,
            "idempotency_key": idempotency_key or f"idem_{application_id}_{bank_id}",
            "dynamic_fields": dynamic_fields or {},
        }
        sig = compute_event_signature(secret_key, event_dict)
        event_dict["payload_signature"] = sig
        return cls(**event_dict)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, data_str: str) -> "ApplicationSubmittedEvent":
        return cls.model_validate_json(data_str)


class ApplicationStatusUpdatedEvent(BaseModel):
    """Event contract published when onboarding status mutates asynchronously."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    event_name: Literal["application_status_updated_event"] = "application_status_updated_event"
    application_id: str = Field(..., description="UUID identifying the application")
    previous_status: str = Field(..., description="Prior state machine status")
    new_status: str = Field(..., description="Newly transitioned state machine status")
    account_number: Optional[str] = Field(default=None, description="Issued bank account number if opened")
    timestamp: str = Field(default_factory=utc_now_iso, description="ISO 8601 UTC timestamp")

    @field_validator("application_id")
    @classmethod
    def validate_uuid_format(cls, v: str) -> str:
        try:
            return str(uuid.UUID(str(v)))
        except (ValueError, AttributeError):
            raise ValueError(f"application_id must be a valid UUID string, got: '{v}'")

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, data_str: str) -> "ApplicationStatusUpdatedEvent":
        return cls.model_validate_json(data_str)
