import json
import uuid
from src.events.application_submitted import (
    ApplicationStatusUpdatedEvent,
    ApplicationSubmittedEvent,
)


def test_application_submitted_event_spec_parity_contract() -> None:
    # Contract test verifying parity with system_guide.md §5.2 schema specification
    spec_example = {
        "event_name": "application_submitted_event",
        "application_id": "c4b3a1a0-7f24-4b5c-8d12-1f48f4a7c001",
        "bank_id": "bank_awash",
        "timestamp": "2026-10-28T15:00:00Z",
        "payload_signature": "sha256-hex-signature-1234567890abcdef",
    }

    # Verify consumer parses the exact spec example
    event = ApplicationSubmittedEvent.model_validate(spec_example)
    assert event.event_name == "application_submitted_event"
    assert event.application_id == "c4b3a1a0-7f24-4b5c-8d12-1f48f4a7c001"
    assert event.bank_id == "bank_awash"
    assert event.timestamp == "2026-10-28T15:00:00Z"
    assert event.payload_signature == "sha256-hex-signature-1234567890abcdef"

    # Verify producer exports compatible payload keys
    dumped = event.model_dump()
    assert "event_name" in dumped
    assert "application_id" in dumped
    assert "bank_id" in dumped
    assert "timestamp" in dumped
    assert "payload_signature" in dumped


def test_application_submitted_event_consumer_backward_compatibility() -> None:
    # Verify consumer safely ignores additional/evolved publisher attributes
    evolved_payload = {
        "event_name": "application_submitted_event",
        "application_id": str(uuid.uuid4()),
        "bank_id": "bank_awash",
        "timestamp": "2026-10-30T12:00:00Z",
        "payload_signature": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "future_field_protocol_v3": "some_value",
        "extra_tracing_headers": {"trace_id": "trace-123"},
    }

    event = ApplicationSubmittedEvent.model_validate(evolved_payload)
    assert event.event_name == "application_submitted_event"
    assert event.bank_id == "bank_awash"


def test_application_status_updated_event_spec_parity_contract() -> None:
    # Contract test verifying parity with system_guide.md §5.2 schema specification
    spec_example = {
        "event_name": "application_status_updated_event",
        "application_id": "c4b3a1a0-7f24-4b5c-8d12-1f48f4a7c001",
        "previous_status": "SUBMITTED_TO_BANK",
        "new_status": "ACCOUNT_OPENED",
        "account_number": "1000123456789",
        "timestamp": "2026-10-28T15:01:00Z",
    }

    event = ApplicationStatusUpdatedEvent.model_validate(spec_example)
    assert event.event_name == "application_status_updated_event"
    assert event.application_id == "c4b3a1a0-7f24-4b5c-8d12-1f48f4a7c001"
    assert event.previous_status == "SUBMITTED_TO_BANK"
    assert event.new_status == "ACCOUNT_OPENED"
    assert event.account_number == "1000123456789"
