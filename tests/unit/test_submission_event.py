import uuid
import pytest
from pydantic import ValidationError

from src.events.application_submitted import (
    ApplicationStatusUpdatedEvent,
    ApplicationSubmittedEvent,
    compute_event_signature,
    verify_event_signature,
)


def test_application_submitted_event_factory_and_signature() -> None:
    secret = "super-secret-hmac-key"
    app_id = str(uuid.uuid4())

    event = ApplicationSubmittedEvent.create(
        application_id=app_id,
        bank_id="bank_awash",
        secret_key=secret,
        tier="standard",
        dynamic_fields={"monthly_income_etb": 25000},
    )

    assert event.event_name == "application_submitted_event"
    assert event.application_id == app_id
    assert event.bank_id == "bank_awash"
    assert event.tier == "standard"
    assert event.idempotency_key == f"idem_{app_id}_bank_awash"
    assert len(event.payload_signature) == 64  # SHA-256 hex string

    # Signature verification
    assert event.verify_signature(secret) is True
    assert event.verify_signature("wrong-secret") is False

    # Tampered payload fails verification
    tampered_dict = event.model_dump()
    tampered_dict["bank_id"] = "bank_cbe"
    assert verify_event_signature(secret, tampered_dict, event.payload_signature) is False


def test_application_submitted_event_validation_errors() -> None:
    # 1. Invalid UUID
    with pytest.raises(ValidationError) as exc_uuid:
        ApplicationSubmittedEvent(
            application_id="not-a-valid-uuid",
            bank_id="bank_awash",
            payload_signature="a" * 64,
        )
    assert "valid UUID" in str(exc_uuid.value)

    # 2. Invalid timestamp
    with pytest.raises(ValidationError) as exc_time:
        ApplicationSubmittedEvent(
            application_id=str(uuid.uuid4()),
            bank_id="bank_awash",
            timestamp="invalid-date-format",
            payload_signature="a" * 64,
        )
    assert "ISO 8601" in str(exc_time.value)

    # 3. Missing bank_id or signature
    with pytest.raises(ValidationError):
        ApplicationSubmittedEvent(
            application_id=str(uuid.uuid4()),
            bank_id="",
            payload_signature="",
        )


def test_application_submitted_event_json_serialization() -> None:
    secret = "secret-key"
    app_id = str(uuid.uuid4())
    event = ApplicationSubmittedEvent.create(
        application_id=app_id,
        bank_id="bank_awash",
        secret_key=secret,
    )

    json_str = event.to_json()
    assert '"application_id"' in json_str
    assert '"payload_signature"' in json_str

    deserialized = ApplicationSubmittedEvent.from_json(json_str)
    assert deserialized.application_id == app_id
    assert deserialized.bank_id == "bank_awash"
    assert deserialized.payload_signature == event.payload_signature


def test_application_status_updated_event() -> None:
    app_id = str(uuid.uuid4())
    status_event = ApplicationStatusUpdatedEvent(
        application_id=app_id,
        previous_status="SUBMITTED_TO_BANK",
        new_status="ACCOUNT_OPENED",
        account_number="1000123456789",
    )

    assert status_event.event_name == "application_status_updated_event"
    assert status_event.application_id == app_id
    assert status_event.previous_status == "SUBMITTED_TO_BANK"
    assert status_event.new_status == "ACCOUNT_OPENED"
    assert status_event.account_number == "1000123456789"
    assert "T" in status_event.timestamp

    # Test JSON round-trip
    json_str = status_event.to_json()
    recovered = ApplicationStatusUpdatedEvent.from_json(json_str)
    assert recovered.application_id == app_id
    assert recovered.account_number == "1000123456789"

    # Invalid UUID
    with pytest.raises(ValidationError):
        ApplicationStatusUpdatedEvent(
            application_id="invalid-uuid",
            previous_status="DRAFT",
            new_status="CONSENTED",
        )
