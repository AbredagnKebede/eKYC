import pytest

from src.clients.fayda_client import (
    FaydaClient,
    FaydaFormatError,
    FaydaVerificationError,
    FAYDA_API_KEY,
    FAYDA_SANDBOX_URL,
)


def test_fayda_client_initialization_and_url_normalization() -> None:
    client = FaydaClient(base_url="http://sandbox.local:8081/fayda/v2", api_key="secret-key-123")
    assert client.base_url == "http://sandbox.local:8081/fayda/v2"
    assert client.api_key == "secret-key-123"
    assert client.timeout == 5.0
    assert client.max_retries == 2

    client_normalized = FaydaClient(base_url="http://sandbox.local:8081/fayda")
    assert client_normalized.base_url == "http://sandbox.local:8081/fayda/v2"


def test_fayda_client_headers() -> None:
    client = FaydaClient(api_key="custom-fayda-bearer-token")
    headers = client._headers()
    assert headers["Authorization"] == "Bearer custom-fayda-bearer-token"
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json"


@pytest.mark.asyncio
async def test_fayda_client_format_validation_rejects_invalid_fin() -> None:
    client = FaydaClient()

    with pytest.raises(FaydaFormatError) as exc_info1:
        await client.generate_otp("12345")
    assert exc_info1.value.status_code == 422
    assert "12 numeric digits required" in exc_info1.value.detail

    with pytest.raises(FaydaFormatError) as exc_info2:
        await client.generate_otp("1234567890123")
    assert exc_info2.value.status_code == 422

    with pytest.raises(FaydaFormatError) as exc_info3:
        await client.generate_otp("lettersnotnum")
    assert exc_info3.value.status_code == 422


@pytest.mark.asyncio
async def test_fayda_client_empty_otp_validation() -> None:
    client = FaydaClient()
    with pytest.raises(FaydaVerificationError) as exc_info:
        await client.verify_otp("tx_1234", "   ")
    assert exc_info.value.status_code == 400
    assert "cannot be empty" in str(exc_info.value)


@pytest.mark.asyncio
async def test_fayda_client_upstream_422_and_500(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    from src.clients.fayda_client import FaydaError

    client = FaydaClient(max_retries=0)

    # Mock 422 response
    async def mock_post_422(*args, **kwargs):
        return httpx.Response(422, json={"detail": "Bad checksum"}, request=httpx.Request("POST", "http://test"))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_422)
    with pytest.raises(FaydaFormatError) as exc_422:
        await client.generate_otp("123456789012")
    assert exc_422.value.status_code == 422
    assert "Bad checksum" in exc_422.value.detail

    # Mock 500 response with non-json
    async def mock_post_500(*args, **kwargs):
        return httpx.Response(500, text="Internal Server Error", request=httpx.Request("POST", "http://test"))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_500)
    with pytest.raises(FaydaError) as exc_500:
        await client.generate_otp("123456789012")
    assert exc_500.value.status_code == 500
    assert "Internal Server Error" in str(exc_500.value)


@pytest.mark.asyncio
async def test_fayda_client_timeout_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    from src.clients.fayda_client import FaydaTimeoutError

    client = FaydaClient(max_retries=1)
    call_count = 0

    async def mock_post_timeout(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise httpx.TimeoutException("Read timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_timeout)
    with pytest.raises(FaydaTimeoutError) as exc_timeout:
        await client.generate_otp("123456789012")

    assert call_count == 2
    assert exc_timeout.value.status_code == 504
    assert "timed out after 2 attempts" in str(exc_timeout.value)
