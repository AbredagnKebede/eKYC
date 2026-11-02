import uuid
from src.events.application_submitted import ApplicationSubmittedEvent


def test_application_submitted_event_publisher_contract() -> None:
    """Contract test verifying that publisher formats schema conforming to system_guide.md §5.2."""
    app_id = str(uuid.uuid4())
    event = ApplicationSubmittedEvent.create(
        application_id=app_id,
        bank_id="bank_awash",
        secret_key="test-secret-signing-key",
        tier="standard",
        idempotency_key=f"idem_{app_id}_bank_awash",
        dynamic_fields={"monthly_income_etb": 45000.0},
    )

    # Verify required contract attributes exported by publisher
    dumped = event.model_dump()
    assert dumped["event_name"] == "application_submitted_event"
    assert dumped["application_id"] == app_id
    assert dumped["bank_id"] == "bank_awash"
    assert "payload_signature" in dumped
    assert len(dumped["payload_signature"]) >= 64
    assert dumped["idempotency_key"] == f"idem_{app_id}_bank_awash"
