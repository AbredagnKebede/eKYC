import os
import uuid
import pytest

from src.adapters.awash_finacle import AwashFinacleAdapter
from src.clients.bank_cbs_client import BankCBSClient, BANK_API_KEY, BANK_CBS_SANDBOX_URL
from src.services.bank_adapter import (
    BankAdapterService,
    BankSchemaValidationError,
)


@pytest.mark.asyncio
async def test_real_bank_adapter_dispatch_against_cbs_sandbox() -> None:
    # Real external_api sandbox boundary verification
    sandbox_base = os.getenv("BANK_CBS_SANDBOX_URL", "http://127.0.0.1:8082/cbs/v1")
    assert "sandbox" in sandbox_base.lower() or "8082" in sandbox_base

    client = BankCBSClient(base_url=sandbox_base, api_key=BANK_API_KEY)
    adapter = AwashFinacleAdapter(client=client)
    service = BankAdapterService()
    service.register_adapter(adapter)

    app_id = str(uuid.uuid4())
    idem_key = f"idem_adapter_{app_id}"
    app_data = {
        "application_id": app_id,
        "bank_id": "bank_awash",
        "tier": "standard",
        "demographics": {
            "full_name": "Derartu Tulu Kenenisa",
            "gender": "FEMALE",
            "date_of_birth": "1988-11-20",
        },
        "dynamic_fields": {
            "monthly_income_etb": 35000,
            "occupation": "Athlete",
            "source_of_funds": "Salary",
            "branch_code": "AW-BOLE-01",
        },
    }

    # 1. Execute live verified dispatch via adapter service
    result = await service.submit("bank_awash", app_data, idempotency_key=idem_key)
    assert result["status"] == "SUCCESS"
    assert result["bank_id"] == "bank_awash"
    assert result["account_tier"] == "standard"
    assert "account_number" in result
    assert result["account_number"].startswith("1000")
    assert len(result["account_number"]) == 13
    assert "bank_reference" in result
    bank_ref = result["bank_reference"]
    assert bank_ref.startswith("CBS-BANK_AWASH-")

    # 2. Idempotency test: resubmission returns identical account number and reference
    res2 = await service.submit("bank_awash", app_data, idempotency_key=idem_key)
    assert res2["status"] == "SUCCESS"
    assert res2["account_number"] == result["account_number"]
    assert res2["bank_reference"] == result["bank_reference"]


@pytest.mark.asyncio
async def test_real_bank_adapter_enterprise_review_and_validation() -> None:
    sandbox_base = os.getenv("BANK_CBS_SANDBOX_URL", "http://127.0.0.1:8082/cbs/v1")
    assert "sandbox" in sandbox_base.lower() or "8082" in sandbox_base

    client = BankCBSClient(base_url=sandbox_base, api_key=BANK_API_KEY)
    adapter = AwashFinacleAdapter(client=client)
    service = BankAdapterService()
    service.register_adapter(adapter)

    # 1. Validation failure: missing required occupation
    bad_app_data = {
        "application_id": str(uuid.uuid4()),
        "bank_id": "bank_awash",
        "tier": "standard",
        "dynamic_fields": {
            "monthly_income_etb": 10000,
            "source_of_funds": "Savings",
        },
    }
    with pytest.raises(BankSchemaValidationError) as exc_val:
        await service.submit("bank_awash", bad_app_data)
    assert "occupation" in exc_val.value.field_errors

    # 2. Enterprise account tier triggers PENDING_REVIEW in live sandbox
    app_id = str(uuid.uuid4())
    ent_data = {
        "application_id": app_id,
        "bank_id": "bank_awash",
        "tier": "enterprise",
        "demographics": {
            "full_name": "Addis Trading Enterprise",
            "gender": "OTHER",
            "date_of_birth": "2010-01-01",
        },
        "dynamic_fields": {
            "monthly_income_etb": 500000,
            "occupation": "Import Export",
            "source_of_funds": "Business",
            "requires_review": True,
        },
    }

    ent_result = await service.submit("bank_awash", ent_data)
    assert ent_result["status"] == "PENDING_REVIEW"
    assert ent_result["bank_id"] == "bank_awash"
    assert ent_result["account_number"] is None
    assert ent_result["account_tier"] == "enterprise"
    assert "bank_reference" in ent_result
