import os
import uuid
import httpx
import pytest

from src.clients.bank_cbs_client import (
    BankCBSClient,
    BankCBSAuthError,
    BankCBSPayloadError,
    BankCBSUnavailableError,
    BANK_API_KEY,
    BANK_CBS_SANDBOX_URL,
)


@pytest.mark.asyncio
async def test_real_bank_cbs_sandbox_account_opening_and_idempotency() -> None:
    # Real external_api sandbox boundary verification
    sandbox_base = os.getenv("BANK_CBS_SANDBOX_URL", "http://127.0.0.1:8082/cbs/v1")
    assert "sandbox" in sandbox_base.lower() or "8082" in sandbox_base

    client = BankCBSClient(base_url=sandbox_base, api_key=BANK_API_KEY)

    app_id = str(uuid.uuid4())
    idem_key = f"idem_test_{app_id}"
    payload = {
        "application_id": app_id,
        "bank_id": "bank_awash",
        "tier": "standard",
        "customer_details": {
            "full_name": "Tadesse Chala Desta",
            "gender": "MALE",
            "date_of_birth": "1990-01-01",
        },
        "dynamic_fields": {
            "source_of_funds": "Salary",
            "monthly_income_etb": 25000,
        },
    }

    # 1. Open account via live sandbox
    res1 = await client.open_account(payload, idempotency_key=idem_key)
    assert res1["status"] == "SUCCESS"
    assert res1["bank_id"] == "bank_awash"
    assert res1["application_id"] == app_id
    assert res1["account_tier"] == "standard"
    assert "account_number" in res1
    assert res1["account_number"].startswith("1000")
    assert len(res1["account_number"]) == 13
    assert "bank_reference" in res1
    bank_ref = res1["bank_reference"]
    assert bank_ref.startswith("CBS-BANK_AWASH-")

    # 2. Test Idempotency: exact same idempotency_key must return identical account number
    res2 = await client.open_account(payload, idempotency_key=idem_key)
    assert res2["status"] == "SUCCESS"
    assert res2["account_number"] == res1["account_number"]
    assert res2["bank_reference"] == res1["bank_reference"]

    # 3. Query account status by bank_reference
    status_res = await client.get_account_status(bank_ref)
    assert status_res["status"] == "SUCCESS"
    assert status_res["bank_reference"] == bank_ref
    assert status_res["account_number"] == res1["account_number"]


@pytest.mark.asyncio
async def test_real_bank_cbs_sandbox_auth_and_validation_rejection() -> None:
    sandbox_base = os.getenv("BANK_CBS_SANDBOX_URL", "http://127.0.0.1:8082/cbs/v1")
    assert "sandbox" in sandbox_base.lower() or "8082" in sandbox_base

    # 1. Unauthorized API Key
    bad_client = BankCBSClient(base_url=sandbox_base, api_key="invalid-unauthorized-key")
    app_id = str(uuid.uuid4())
    with pytest.raises(BankCBSAuthError) as exc_auth:
        await bad_client.open_account({
            "application_id": app_id,
            "bank_id": "bank_awash",
        })
    assert exc_auth.value.status_code == 401
    assert "Unauthorized" in exc_auth.value.detail or "Invalid or missing" in exc_auth.value.detail

    # 2. Missing bank_id or application_id
    valid_client = BankCBSClient(base_url=sandbox_base, api_key=BANK_API_KEY)
    with pytest.raises(BankCBSPayloadError) as exc_payload:
        await valid_client.open_account({"tier": "standard"})
    assert exc_payload.value.status_code == 422


@pytest.mark.asyncio
async def test_real_bank_cbs_sandbox_outage_simulation_and_recovery() -> None:
    sandbox_base = os.getenv("BANK_CBS_SANDBOX_URL", "http://127.0.0.1:8082/cbs/v1")
    assert "sandbox" in sandbox_base.lower() or "8082" in sandbox_base

    client = BankCBSClient(base_url=sandbox_base, api_key=BANK_API_KEY, max_retries=0)

    # 1. Switch sandbox mode to maintenance (HTTP 503)
    async with httpx.AsyncClient() as http_client:
        mode_res = await http_client.post(
            f"{sandbox_base}/sandbox/mode",
            json={"mode": "maintenance", "status_code": 503},
        )
        assert mode_res.status_code == 200
        assert mode_res.json()["simulation_mode"] == "maintenance"

    # 2. Request should fail with BankCBSUnavailableError (503)
    app_id = str(uuid.uuid4())
    with pytest.raises(BankCBSUnavailableError) as exc_503:
        await client.open_account({
            "application_id": app_id,
            "bank_id": "bank_awash",
            "tier": "standard",
        })
    assert exc_503.value.status_code == 503
    assert "maintenance" in exc_503.value.detail.lower()

    # 3. Restore sandbox mode to normal
    async with httpx.AsyncClient() as http_client:
        reset_res = await http_client.post(
            f"{sandbox_base}/sandbox/mode",
            json={"mode": "normal"},
        )
        assert reset_res.status_code == 200
        assert reset_res.json()["simulation_mode"] == "normal"

    # Reset client circuit breaker for fresh test
    client.circuit_breaker.reset()

    # 4. Request now succeeds
    success_res = await client.open_account({
        "application_id": app_id,
        "bank_id": "bank_awash",
        "tier": "standard",
    })
    assert success_res["status"] == "SUCCESS"
    assert success_res["account_number"].startswith("1000")
