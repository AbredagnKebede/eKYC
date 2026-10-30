import asyncio
import time
from typing import Any, Dict
import httpx
import pytest

from src.clients.bank_cbs_client import (
    BankCBSClient,
    BankCBSError,
    BankCBSConnectionError,
    BankCBSTimeoutError,
    BankCBSAuthError,
    BankCBSPayloadError,
    BankCBSUnavailableError,
    BankCBSCircuitBreakerOpenError,
    CircuitBreaker,
    CircuitBreakerState,
    BANK_API_KEY,
    BANK_CBS_SANDBOX_URL,
)
from sandbox.bank_cbs_sandbox import STATE, BankCBSSandboxState


def test_bank_cbs_client_initialization_and_url_normalization() -> None:
    client = BankCBSClient(base_url="http://sandbox.local:8082/cbs/v1", api_key="test-cbs-key")
    assert client.base_url == "http://sandbox.local:8082/cbs/v1"
    assert client.api_key == "test-cbs-key"
    assert client.timeout == 5.0
    assert client.max_retries == 2

    # Normalization when /cbs/v1 is missing
    client_norm = BankCBSClient(base_url="http://sandbox.local:8082")
    assert client_norm.base_url == "http://sandbox.local:8082/cbs/v1"


def test_bank_cbs_client_headers() -> None:
    client = BankCBSClient(api_key="custom-cbs-token")
    headers_no_idem = client._headers()
    assert headers_no_idem["Authorization"] == "Bearer custom-cbs-token"
    assert headers_no_idem["Content-Type"] == "application/json"
    assert "Idempotency-Key" not in headers_no_idem

    headers_idem = client._headers(idempotency_key="key_12345")
    assert headers_idem["Idempotency-Key"] == "key_12345"
    assert headers_idem["Authorization"] == "Bearer custom-cbs-token"


@pytest.mark.asyncio
async def test_bank_cbs_client_payload_validation() -> None:
    client = BankCBSClient()

    with pytest.raises(BankCBSPayloadError) as exc_info1:
        await client.open_account({"bank_id": "bank_awash"})
    assert exc_info1.value.status_code == 422
    assert "application_id and bank_id are mandatory" in str(exc_info1.value)

    with pytest.raises(BankCBSPayloadError) as exc_info2:
        await client.open_account({"application_id": "1234-uuid"})
    assert exc_info2.value.status_code == 422

    with pytest.raises(BankCBSPayloadError) as exc_info3:
        await client.get_account_status("")
    assert exc_info3.value.status_code == 422
    assert "bank_reference cannot be empty" in str(exc_info3.value)


def test_circuit_breaker_state_transitions() -> None:
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.can_execute() is True

    # 1st failure - stays CLOSED
    cb.record_failure()
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.can_execute() is True

    # 2nd failure - transitions to OPEN
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN
    assert cb.can_execute() is False

    # Immediate check while OPEN rejects
    assert cb.can_execute() is False

    # Wait for recovery timeout to elapse
    time.sleep(0.15)
    assert cb.can_execute() is True
    assert cb.state == CircuitBreakerState.HALF_OPEN

    # Failure in HALF_OPEN trips immediately back to OPEN
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN

    # Wait again and test recovery success
    time.sleep(0.15)
    assert cb.can_execute() is True
    assert cb.state == CircuitBreakerState.HALF_OPEN

    cb.record_success()
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.can_execute() is True

    # Test reset and trip
    cb.trip()
    assert cb.state == CircuitBreakerState.OPEN
    cb.reset()
    assert cb.state == CircuitBreakerState.CLOSED


@pytest.mark.asyncio
async def test_bank_cbs_client_circuit_breaker_open_rejection() -> None:
    client = BankCBSClient(failure_threshold=1, recovery_timeout=10.0)
    client.circuit_breaker.trip()

    with pytest.raises(BankCBSCircuitBreakerOpenError) as exc_info:
        await client.open_account({"application_id": "app_1", "bank_id": "bank_awash"})
    assert exc_info.value.status_code == 503
    assert "Circuit breaker open" in exc_info.value.detail

    with pytest.raises(BankCBSCircuitBreakerOpenError):
        await client.get_account_status("AWASH-REF-1")


@pytest.mark.asyncio
async def test_bank_cbs_client_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BankCBSClient(max_retries=0)

    async def mock_post_401(*args: Any, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            401,
            json={"detail": "Bad credentials"},
            request=httpx.Request("POST", "http://test/cbs/v1/accounts"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_401)
    with pytest.raises(BankCBSAuthError) as exc_info:
        await client.open_account({"application_id": "app_1", "bank_id": "bank_awash"})
    assert exc_info.value.status_code == 401
    assert "Bad credentials" in exc_info.value.detail


@pytest.mark.asyncio
async def test_bank_cbs_client_payload_error_from_server(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BankCBSClient(max_retries=0)

    async def mock_post_422(*args: Any, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            422,
            json={"detail": "Invalid tier specified"},
            request=httpx.Request("POST", "http://test/cbs/v1/accounts"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_422)
    with pytest.raises(BankCBSPayloadError) as exc_info:
        await client.open_account({"application_id": "app_1", "bank_id": "bank_awash"})
    assert exc_info.value.status_code == 422
    assert "Invalid tier specified" in exc_info.value.detail


@pytest.mark.asyncio
async def test_bank_cbs_client_unavailable_503(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BankCBSClient(max_retries=0)

    async def mock_post_503(*args: Any, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            503,
            json={"detail": "CBS offline for maintenance"},
            request=httpx.Request("POST", "http://test/cbs/v1/accounts"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_503)
    with pytest.raises(BankCBSUnavailableError) as exc_info:
        await client.open_account({"application_id": "app_1", "bank_id": "bank_awash"})
    assert exc_info.value.status_code == 503
    assert "CBS offline for maintenance" in exc_info.value.detail


@pytest.mark.asyncio
async def test_bank_cbs_client_generic_500(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BankCBSClient(max_retries=0)

    async def mock_post_500(*args: Any, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            500,
            text="Internal Server Error",
            request=httpx.Request("POST", "http://test/cbs/v1/accounts"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_500)
    with pytest.raises(BankCBSError) as exc_info:
        await client.open_account({"application_id": "app_1", "bank_id": "bank_awash"})
    assert exc_info.value.status_code == 500
    assert "Internal Server Error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_bank_cbs_client_timeout_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BankCBSClient(max_retries=1, timeout=0.5)
    call_count = 0

    async def mock_post_timeout(*args: Any, **kwargs: Any) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_timeout)
    with pytest.raises(BankCBSTimeoutError) as exc_info:
        await client.open_account({"application_id": "app_1", "bank_id": "bank_awash"})

    assert call_count == 2
    assert exc_info.value.status_code == 504
    assert "timed out after 2 attempts" in str(exc_info.value)


@pytest.mark.asyncio
async def test_bank_cbs_client_get_account_status_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    client = BankCBSClient()

    # Success 200
    async def mock_get_200(*args: Any, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "SUCCESS", "account_number": "1000123456789"},
            request=httpx.Request("GET", "http://test/cbs/v1/accounts/REF1"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_200)
    res = await client.get_account_status("REF1")
    assert res["status"] == "SUCCESS"
    assert res["account_number"] == "1000123456789"

    # 401 Auth Error
    async def mock_get_401(*args: Any, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            401,
            json={"detail": "Bad Key"},
            request=httpx.Request("GET", "http://test/cbs/v1/accounts/REF1"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_401)
    with pytest.raises(BankCBSAuthError) as exc_401:
        await client.get_account_status("REF1")
    assert exc_401.value.status_code == 401

    # 404 Not Found
    async def mock_get_404(*args: Any, **kwargs: Any) -> httpx.Response:
        return httpx.Response(
            404,
            json={"detail": "Not Found"},
            request=httpx.Request("GET", "http://test/cbs/v1/accounts/REF1"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_404)
    with pytest.raises(BankCBSError) as exc_404:
        await client.get_account_status("REF1")
    assert exc_404.value.status_code == 404

    # Network Exception
    async def mock_get_net_err(*args: Any, **kwargs: Any) -> httpx.Response:
        raise httpx.NetworkError("Host unreachable")

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_net_err)
    with pytest.raises(BankCBSConnectionError) as exc_net:
        await client.get_account_status("REF1")
    assert "Host unreachable" in str(exc_net.value)


def test_sandbox_state_management() -> None:
    sandbox_state = BankCBSSandboxState()
    assert sandbox_state.simulation_mode == "normal"
    assert sandbox_state.failure_status_code == 503

    sandbox_state.simulation_mode = "maintenance"
    sandbox_state.failure_status_code = 502
    sandbox_state.idempotency_store["key1"] = {"status": "SUCCESS"}
    sandbox_state.accounts_by_ref["ref1"] = {"account_number": "1000000001"}

    assert sandbox_state.simulation_mode == "maintenance"
    assert len(sandbox_state.idempotency_store) == 1
    assert len(sandbox_state.accounts_by_ref) == 1

    sandbox_state.reset()
    assert sandbox_state.simulation_mode == "normal"
    assert sandbox_state.failure_status_code == 503
    assert len(sandbox_state.idempotency_store) == 0
    assert len(sandbox_state.accounts_by_ref) == 0


@pytest.mark.asyncio
async def test_sandbox_handler_in_process_execution() -> None:
    import threading
    from http.server import ThreadingHTTPServer
    from sandbox.bank_cbs_sandbox import BankCBSSandboxHandler

    STATE.reset()
    server = ThreadingHTTPServer(("127.0.0.1", 0), BankCBSSandboxHandler)
    port = server.server_port
    base_url = f"http://127.0.0.1:{port}"

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        async with httpx.AsyncClient(base_url=base_url) as client:
            # 1. Health check
            h_res = await client.get("/health")
            assert h_res.status_code == 200
            assert h_res.json()["status"] == "healthy"

            # 2. 404 GET
            not_found = await client.get("/invalid/path")
            assert not_found.status_code == 404

            # 3. GET account auth failure
            auth_fail = await client.get("/cbs/v1/accounts/REF123")
            assert auth_fail.status_code == 401

            # 4. GET account 404 with auth
            headers = {"Authorization": f"Bearer {BANK_API_KEY}"}
            acc_404 = await client.get("/cbs/v1/accounts/NONEXISTENT", headers=headers)
            assert acc_404.status_code == 404

            # 5. POST accounts auth failure
            p_auth_fail = await client.post("/cbs/v1/accounts", json={"application_id": "1"})
            assert p_auth_fail.status_code == 401

            # 6. POST accounts invalid payload (missing bank_id)
            p_invalid = await client.post("/cbs/v1/accounts", json={"application_id": "1"}, headers=headers)
            assert p_invalid.status_code == 422

            # 7. POST accounts simulated error header
            sim_headers = {**headers, "X-CBS-Simulate-Error": "500"}
            p_sim = await client.post("/cbs/v1/accounts", json={"application_id": "1", "bank_id": "bank_awash"}, headers=sim_headers)
            assert p_sim.status_code == 500

            # 8. POST accounts enterprise review tier
            p_review = await client.post(
                "/cbs/v1/accounts",
                json={"application_id": "app_rev_1", "bank_id": "bank_awash", "tier": "enterprise"},
                headers=headers,
            )
            assert p_review.status_code == 202
            assert p_review.json()["status"] == "PENDING_REVIEW"
            assert p_review.json()["account_number"] is None

            # 9. GET created account by bank_reference
            b_ref = p_review.json()["bank_reference"]
            acc_get = await client.get(f"/cbs/v1/accounts/{b_ref}", headers=headers)
            assert acc_get.status_code == 200
            assert acc_get.json()["bank_reference"] == b_ref

            # 10. POST simulated modes: maintenance and error
            await client.post("/cbs/v1/sandbox/mode", json={"mode": "maintenance", "status_code": 503})
            p_maint = await client.post("/cbs/v1/accounts", json={"application_id": "1", "bank_id": "bank_awash"}, headers=headers)
            assert p_maint.status_code == 503

            await client.post("/cbs/v1/sandbox/mode", json={"mode": "error", "status_code": 500})
            p_err = await client.post("/cbs/v1/accounts", json={"application_id": "1", "bank_id": "bank_awash"}, headers=headers)
            assert p_err.status_code == 500

            # Reset mode
            await client.post("/cbs/v1/sandbox/reset")
            p_reset = await client.post(
                "/cbs/v1/accounts",
                json={"application_id": "app_norm_1", "bank_id": "bank_awash"},
                headers=headers,
            )
            assert p_reset.status_code == 200
            assert p_reset.json()["status"] == "SUCCESS"

            # 11. 404 POST
            p_not_found = await client.post("/cbs/v1/unknown", json={})
            assert p_not_found.status_code == 404

    finally:
        server.shutdown()
        server.server_close()

