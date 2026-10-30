import uuid
from typing import Any, Dict
import pytest

from src.adapters.awash_finacle import AwashFinacleAdapter
from src.clients.bank_cbs_client import BankCBSClient
from src.services.bank_adapter import (
    BankAdapter,
    BankAdapterExecutionError,
    BankAdapterService,
    BankNotFoundError,
    BankSchemaValidationError,
    validate_json_schema,
)


def test_bank_adapter_service_registration_and_lookup() -> None:
    service = BankAdapterService()
    adapter = AwashFinacleAdapter()

    assert len(service.list_supported_banks()) == 0

    service.register_adapter(adapter)
    assert len(service.list_supported_banks()) == 1

    resolved = service.get_adapter("bank_awash")
    assert resolved.bank_id == "bank_awash"
    assert resolved.bank_name == "Awash Bank"

    with pytest.raises(BankNotFoundError) as exc_info:
        service.get_adapter("bank_cbe")
    assert exc_info.value.status_code == 404
    assert "bank_cbe" in exc_info.value.detail


def test_bank_adapter_service_list_banks() -> None:
    service = BankAdapterService()
    service.register_adapter(AwashFinacleAdapter())

    banks = service.list_supported_banks()
    assert len(banks) == 1
    bank = banks[0]
    assert bank["bank_id"] == "bank_awash"
    assert bank["bank_name"] == "Awash Bank"
    assert "standard" in bank["supported_tiers"]
    assert "diaspora" in bank["supported_tiers"]
    assert bank["dynamic_schema"]["type"] == "object"
    assert "monthly_income_etb" in bank["dynamic_schema"]["required"]


def test_json_schema_validation_success_and_errors() -> None:
    schema = {
        "type": "object",
        "required": ["full_name", "age", "is_resident", "income", "source"],
        "properties": {
            "full_name": {"type": "string", "minLength": 3, "maxLength": 50},
            "age": {"type": "integer", "minimum": 18, "maximum": 120},
            "is_resident": {"type": "boolean"},
            "income": {"type": "number", "minimum": 0},
            "source": {"type": "string", "enum": ["Salary", "Business"]},
        },
        "additionalProperties": False,
    }

    # 1. Non-dict input
    with pytest.raises(BankSchemaValidationError) as exc_type:
        validate_json_schema(schema, "not a dict")  # type: ignore
    assert "Expected object/dictionary" in str(exc_type.value)

    # 2. Missing required
    with pytest.raises(BankSchemaValidationError) as exc_req:
        validate_json_schema(schema, {"full_name": "John"})
    assert "Missing required dynamic field(s)" in str(exc_req.value)
    assert "age" in exc_req.value.field_errors

    # 3. Unknown property
    with pytest.raises(BankSchemaValidationError) as exc_unk:
        validate_json_schema(schema, {
            "full_name": "John Doe",
            "age": 25,
            "is_resident": True,
            "income": 1000.0,
            "source": "Salary",
            "unknown_extra": 123,
        })
    assert "Unknown dynamic field(s)" in str(exc_unk.value)

    # 4. String length error
    with pytest.raises(BankSchemaValidationError) as exc_str:
        validate_json_schema(schema, {
            "full_name": "J",
            "age": 25,
            "is_resident": True,
            "income": 1000.0,
            "source": "Salary",
        })
    assert "Length must be at least 3 characters" in exc_str.value.field_errors["full_name"]

    # 5. Type mismatches
    with pytest.raises(BankSchemaValidationError) as exc_types:
        validate_json_schema(schema, {
            "full_name": 12345,
            "age": "twenty",
            "is_resident": "yes",
            "income": "many",
            "source": "Salary",
        })
    assert "Expected string" in exc_types.value.field_errors["full_name"]
    assert "Expected integer" in exc_types.value.field_errors["age"]
    assert "Expected boolean" in exc_types.value.field_errors["is_resident"]
    assert "Expected number" in exc_types.value.field_errors["income"]

    # 6. Numeric limits
    with pytest.raises(BankSchemaValidationError) as exc_limits:
        validate_json_schema(schema, {
            "full_name": "John Doe",
            "age": 15,
            "is_resident": True,
            "income": -100,
            "source": "Salary",
        })
    assert "greater than or equal to 18" in exc_limits.value.field_errors["age"]
    assert "greater than or equal to 0" in exc_limits.value.field_errors["income"]

    # 7. Enum error
    with pytest.raises(BankSchemaValidationError) as exc_enum:
        validate_json_schema(schema, {
            "full_name": "John Doe",
            "age": 25,
            "is_resident": True,
            "income": 5000,
            "source": "Gambling",
        })
    assert "must be one of ['Salary', 'Business']" in exc_enum.value.field_errors["source"]

    # 8. Valid data passes with no exception
    validate_json_schema(schema, {
        "full_name": "John Doe",
        "age": 25,
        "is_resident": True,
        "income": 5000.5,
        "source": "Salary",
    })


def test_awash_finacle_adapter_transformation() -> None:
    adapter = AwashFinacleAdapter()
    app_id = str(uuid.uuid4())

    # Missing application_id
    with pytest.raises(BankSchemaValidationError) as exc_no_id:
        adapter.transform_payload({})
    assert "application_id is mandatory" in str(exc_no_id.value)

    # Unsupported tier
    with pytest.raises(BankSchemaValidationError) as exc_tier:
        adapter.transform_payload({
            "application_id": app_id,
            "tier": "platinum_vip",
        })
    assert "Unsupported account tier 'platinum_vip'" in str(exc_tier.value)

    # Valid standard transformation
    transformed_std = adapter.transform_payload({
        "application_id": app_id,
        "tier": "standard",
        "demographics": {
            "full_name": "Chala Bekele",
            "gender": "MALE",
            "date_of_birth": "1995-04-12",
        },
        "dynamic_fields": {
            "monthly_income_etb": 20000,
            "occupation": "Engineer",
            "source_of_funds": "Salary",
        },
    })

    assert transformed_std["application_id"] == app_id
    assert transformed_std["bank_id"] == "bank_awash"
    assert transformed_std["tier"] == "standard"
    assert transformed_std["finacle_scheme_code"] == "AW-SB-STD"
    assert transformed_std["customer_details"]["full_name"] == "Chala Bekele"
    assert transformed_std["dynamic_fields"]["monthly_income_etb"] == 20000

    # Valid diaspora transformation
    transformed_dia = adapter.transform_payload({
        "application_id": app_id,
        "tier": "diaspora",
        "dynamic_fields": {
            "monthly_income_etb": 50000,
            "occupation": "Doctor",
            "source_of_funds": "Remittance",
        },
    })
    assert transformed_dia["finacle_scheme_code"] == "AW-SB-DIA"


@pytest.mark.asyncio
async def test_awash_finacle_adapter_submit_application_mocked() -> None:
    client = BankCBSClient()
    adapter = AwashFinacleAdapter(client=client)

    app_id = str(uuid.uuid4())
    payload = {
        "application_id": app_id,
        "tier": "standard",
        "dynamic_fields": {
            "monthly_income_etb": 30000,
            "occupation": "Teacher",
            "source_of_funds": "Salary",
        },
    }

    # 1. Success execution
    async def mock_open_account(data: Dict[str, Any], idempotency_key: Any = None) -> Dict[str, Any]:
        return {
            "status": "SUCCESS",
            "bank_id": "bank_awash",
            "bank_reference": f"CBS-AWASH-{app_id[:8]}",
            "account_number": "1000555666777",
            "created_at": "2026-10-30T19:00:00Z",
            "message": "Account opened successfully.",
        }

    client.open_account = mock_open_account  # type: ignore
    result = await adapter.submit_application(payload)

    assert result["status"] == "SUCCESS"
    assert result["bank_id"] == "bank_awash"
    assert result["account_number"] == "1000555666777"
    assert result["account_tier"] == "standard"
    assert result["bank_reference"].startswith("CBS-AWASH-")

    # 2. Client exception wrapped in BankAdapterExecutionError
    async def mock_open_account_fail(data: Dict[str, Any], idempotency_key: Any = None) -> Dict[str, Any]:
        raise RuntimeError("CBS Connection Dropped")

    client.open_account = mock_open_account_fail  # type: ignore
    with pytest.raises(BankAdapterExecutionError) as exc_info:
        await adapter.submit_application(payload)
    assert "Awash Finacle submission failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_bank_adapter_service_validate_and_submit() -> None:
    service = BankAdapterService()
    adapter = AwashFinacleAdapter()
    service.register_adapter(adapter)

    # 1. Validate fields delegation
    with pytest.raises(BankSchemaValidationError) as exc_fields:
        service.validate_fields("bank_awash", {"occupation": "Dev"})
    assert "monthly_income_etb" in exc_fields.value.field_errors

    # Valid dynamic fields pass
    service.validate_fields("bank_awash", {
        "monthly_income_etb": 45000,
        "occupation": "Manager",
        "source_of_funds": "Business",
    })

    # 2. Submit delegation
    app_id = str(uuid.uuid4())

    async def mock_submit(data: Dict[str, Any], idempotency_key: Any = None) -> Dict[str, Any]:
        return {
            "status": "SUCCESS",
            "bank_id": "bank_awash",
            "bank_reference": f"CBS-AWASH-{app_id[:8]}",
            "account_number": "1000999888777",
            "account_tier": "standard",
            "created_at": "2026-10-30T19:00:00Z",
            "message": "Success",
        }

    adapter.submit_application = mock_submit  # type: ignore

    res = await service.submit("bank_awash", {"application_id": app_id})
    assert res["status"] == "SUCCESS"
    assert res["account_number"] == "1000999888777"
