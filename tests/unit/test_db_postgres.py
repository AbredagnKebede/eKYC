import uuid
from datetime import datetime, timezone
import pytest

from src.models.application import (
    Application,
    ApplicationStatus,
    IdentitySnapshot,
    VerificationMethod,
    ConsentRecord,
    BankSubmission,
)
from src.models.audit import AuditLog
from src.models.base import Base


def test_application_model_defaults() -> None:
    now = datetime.now(timezone.utc)
    app_id = uuid.uuid4()
    app = Application(
        id=app_id,
        user_ref="device_fingerprint_abc123",
        bank_id="bank_awash",
        tier="standard",
        expires_at=now,
    )
    assert app.id == app_id
    assert app.user_ref == "device_fingerprint_abc123"
    assert app.bank_id == "bank_awash"
    assert app.tier == "standard"
    assert app.status == ApplicationStatus.DRAFT
    assert app.__tablename__ == "applications"


def test_application_status_enum_values() -> None:
    assert ApplicationStatus.DRAFT.value == "DRAFT"
    assert ApplicationStatus.CONSENTED.value == "CONSENTED"
    assert ApplicationStatus.ID_VERIFIED.value == "ID_VERIFIED"
    assert ApplicationStatus.ID_FAILED.value == "ID_FAILED"
    assert ApplicationStatus.LIVENESS_PASSED.value == "LIVENESS_PASSED"
    assert ApplicationStatus.LIVENESS_FAILED.value == "LIVENESS_FAILED"
    assert ApplicationStatus.DATA_COMPLETE.value == "DATA_COMPLETE"
    assert ApplicationStatus.SUBMITTED_TO_BANK.value == "SUBMITTED_TO_BANK"
    assert ApplicationStatus.ACCOUNT_OPENED.value == "ACCOUNT_OPENED"
    assert ApplicationStatus.CANCELLED.value == "CANCELLED"
    assert ApplicationStatus.EXPIRED.value == "EXPIRED"


def test_identity_snapshot_model_attributes() -> None:
    app_id = uuid.uuid4()
    snapshot = IdentitySnapshot(
        application_id=app_id,
        encrypted_full_name=b"ciphertext_fullname",
        encrypted_dob=b"ciphertext_dob",
        gender="MALE",
        fayda_ref_hash="hash_sha256_fin123",
        liveness_score=0.98,
        verification_method=VerificationMethod.OTP,
    )
    assert snapshot.application_id == app_id
    assert snapshot.encrypted_full_name == b"ciphertext_fullname"
    assert snapshot.encrypted_dob == b"ciphertext_dob"
    assert snapshot.gender == "MALE"
    assert snapshot.fayda_ref_hash == "hash_sha256_fin123"
    assert snapshot.liveness_score == 0.98
    assert snapshot.verification_method == VerificationMethod.OTP
    assert snapshot.__tablename__ == "identity_snapshots"


def test_consent_record_model_attributes() -> None:
    consent_id = uuid.uuid4()
    app_id = uuid.uuid4()
    record = ConsentRecord(
        id=consent_id,
        application_id=app_id,
        consent_version="v1.0-2026",
        ip_address="196.188.12.34",
        device_fingerprint="device_sig_xyz789",
    )
    assert record.id == consent_id
    assert record.application_id == app_id
    assert record.consent_version == "v1.0-2026"
    assert record.ip_address == "196.188.12.34"
    assert record.device_fingerprint == "device_sig_xyz789"
    assert record.__tablename__ == "consent_records"


def test_bank_submission_model_attributes() -> None:
    sub_id = uuid.uuid4()
    app_id = uuid.uuid4()
    fields = {"occupation": "Software Engineer", "source_of_funds": "Salary"}
    sub = BankSubmission(
        id=sub_id,
        application_id=app_id,
        bank_id="bank_awash",
        dynamic_fields=fields,
        bank_reference="AWASH-REF-00123",
        account_number="1000987654321",
        retry_count=2,
    )
    assert sub.id == sub_id
    assert sub.application_id == app_id
    assert sub.bank_id == "bank_awash"
    assert sub.dynamic_fields["occupation"] == "Software Engineer"
    assert sub.bank_reference == "AWASH-REF-00123"
    assert sub.account_number == "1000987654321"
    assert sub.retry_count == 2
    assert sub.__tablename__ == "bank_submissions"


def test_audit_log_model_attributes() -> None:
    log = AuditLog(
        id=101,
        actor_type="CUSTOMER",
        actor_id="user_device_99",
        action="CONSENT_GRANTED",
        payload_hash="sha256_payload_hash_abc",
        prev_log_hash="sha256_prev_chain_root",
        hmac_signature="hmac_signature_seal_001",
    )
    assert log.id == 101
    assert log.actor_type == "CUSTOMER"
    assert log.actor_id == "user_device_99"
    assert log.action == "CONSENT_GRANTED"
    assert log.payload_hash == "sha256_payload_hash_abc"
    assert log.prev_log_hash == "sha256_prev_chain_root"
    assert log.hmac_signature == "hmac_signature_seal_001"
    assert log.__tablename__ == "audit_logs"


def test_table_metadata_registration() -> None:
    registered_tables = set(Base.metadata.tables.keys())
    expected_tables = {
        "applications",
        "identity_snapshots",
        "consent_records",
        "bank_submissions",
        "audit_logs",
    }
    assert expected_tables.issubset(registered_tables)
