import os
import pytest

from src.clients.fayda_client import (
    FaydaClient,
    FaydaError,
    FaydaVerificationError,
    FAYDA_API_KEY,
    FAYDA_SANDBOX_URL,
)


@pytest.mark.asyncio
async def test_real_fayda_sandbox_otp_generation_and_verification() -> None:
    # Real external_api sandbox endpoint verification
    sandbox_base = os.getenv("FAYDA_SANDBOX_URL", "http://127.0.0.1:8081/fayda/v2")
    assert "sandbox" in sandbox_base.lower() or "8081" in sandbox_base

    client = FaydaClient(base_url=sandbox_base, api_key=FAYDA_API_KEY)

    # 1. Generate OTP challenge via live sandbox
    gen_res = await client.generate_otp("123456789012")
    assert gen_res["status"] == "OTP_SENT"
    assert gen_res["expires_in"] == 180
    assert "transaction_id" in gen_res
    tx_id = gen_res["transaction_id"]
    assert tx_id.startswith("tx_fayda_")

    # 2. Verify valid OTP ("123456") against live sandbox
    ver_res = await client.verify_otp(tx_id, "123456")
    assert ver_res["status"] == "VERIFIED"
    assert ver_res["transaction_id"] == tx_id
    demographics = ver_res["demographics"]
    assert demographics["full_name"] == "Alemu Kebede Tadesse"
    assert demographics["gender"] == "MALE"
    assert demographics["date_of_birth"] == "1992-05-18"
    assert "signature" in ver_res

    # 3. Test wrong OTP rejection from live sandbox
    with pytest.raises(FaydaVerificationError) as exc_wrong:
        await client.verify_otp(tx_id, "000000")
    assert exc_wrong.value.status_code == 400
    assert "incorrect" in str(exc_wrong.value).lower()

    # 4. Test expired OTP response (code 999999 in sandbox triggers 410)
    with pytest.raises(FaydaVerificationError) as exc_expired:
        await client.verify_otp(tx_id, "999999")
    assert exc_expired.value.status_code == 410
    assert "expired" in str(exc_expired.value).lower()
