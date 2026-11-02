import pytest
import uuid
from pydantic import ValidationError
from src.events.application_submitted import (
    ApplicationSubmittedEvent,
    compute_event_signature,
    verify_event_signature,
)


def test_application_submitted_event_consumer_contract() -> None:
    """Contract test verifying consumer correctly deserializes and validates ApplicationSubmittedEvent."""
    app_id = str(uuid.uuid4())
    secret = "production-grade-internal-signing-secret"
    
    # 1. Consumer parses valid raw JSON wire format
    raw_payload = {
        "event_name": "application_submitted_event",
        "application_id": app_id,
        "bank_id": "bank_awash",
        "timestamp": "2026-11-03T00:00:00+00:00",
        "tier": "standard",
        "idempotency_key": f"idem_{app_id}_bank_awash",
        "dynamic_fields": {"monthly_income_etb": 50000.0, "source_of_funds": "employment"},
    }
    raw_payload["payload_signature"] = compute_event_signature(secret, raw_payload)

    # Extra field to test forward compatibility
    wire_payload = dict(raw_payload)
    wire_payload["unknown_extra_metadata"] = "ignored_safely"

    event = ApplicationSubmittedEvent.model_validate(wire_payload)
    assert event.application_id == app_id
    assert event.bank_id == "bank_awash"
    assert event.verify_signature(secret) is True

    # 2. Tampered payload fails verification
    assert event.verify_signature("wrong-signing-secret") is False
    tampered_dict = event.model_dump()
    tampered_dict["bank_id"] = "bank_cbe"
    assert verify_event_signature(secret, tampered_dict, event.payload_signature) is False

    # 3. Malformed payload missing required fields triggers validation error
    with pytest.raises(ValidationError):
        ApplicationSubmittedEvent.model_validate({
            "event_name": "application_submitted_event",
            "bank_id": "bank_awash",
        })

    # 4. Invalid UUID format triggers validation error
    with pytest.raises(ValidationError):
        ApplicationSubmittedEvent.model_validate({
            "event_name": "application_submitted_event",
            "application_id": "invalid-uuid-format",
            "bank_id": "bank_awash",
            "payload_signature": "sig",
        })
