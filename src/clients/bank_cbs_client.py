import asyncio
import os
import time
from enum import Enum
from typing import Any, Dict, Optional
import httpx

BANK_API_KEY = os.getenv("BANK_API_KEY", "dev-bank-key")
BANK_CBS_SANDBOX_URL = os.getenv("BANK_CBS_SANDBOX_URL", "http://127.0.0.1:8082/cbs/v1")


class CircuitBreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class BankCBSError(Exception):
    """Base exception for Bank Core Banking System integration failures."""

    def __init__(self, message: str, status_code: int = 500, detail: Optional[str] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class BankCBSConnectionError(BankCBSError):
    """Raised when CBS network communication fails or times out."""
    pass


class BankCBSTimeoutError(BankCBSConnectionError):
    """Raised when external CBS request times out."""
    pass


class BankCBSAuthError(BankCBSError):
    """Raised when API key is unauthorized or rejected by CBS."""
    pass


class BankCBSPayloadError(BankCBSError):
    """Raised when submitted payload fails schema validation at CBS."""
    pass


class BankCBSUnavailableError(BankCBSError):
    """Raised when CBS is down or undergoing scheduled maintenance (e.g. HTTP 503)."""
    pass


class BankCBSCircuitBreakerOpenError(BankCBSError):
    """Raised when outbound requests are rejected because the CBS circuit breaker is OPEN."""

    def __init__(self, message: str = "CBS circuit breaker is OPEN; request rejected.") -> None:
        super().__init__(message, status_code=503, detail="Circuit breaker open")


class CircuitBreaker:
    """Thread-safe / async-safe circuit breaker preventing cascade failure during CBS outages."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 10.0,
        half_open_success_threshold: int = 1,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold

        self.state: CircuitBreakerState = CircuitBreakerState.CLOSED
        self.failure_count: int = 0
        self.success_count: int = 0
        self.last_failure_time: float = 0.0

    def can_execute(self) -> bool:
        """Determines whether a request may proceed through the breaker."""
        now = time.monotonic()
        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            if (now - self.last_failure_time) >= self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                return True
            return False
        elif self.state == CircuitBreakerState.HALF_OPEN:
            return True
        return False

    def record_success(self) -> None:
        """Records a successful operation, transitioning HALF_OPEN to CLOSED if threshold met."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0

    def record_failure(self) -> None:
        """Records an outage or communication failure, potentially opening the circuit."""
        now = time.monotonic()
        self.last_failure_time = now
        if self.state == CircuitBreakerState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
        elif self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            self.failure_count = self.failure_threshold

    def reset(self) -> None:
        """Resets the circuit breaker to closed state."""
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0

    def trip(self) -> None:
        """Forcibly trips the circuit breaker to OPEN state."""
        self.state = CircuitBreakerState.OPEN
        self.failure_count = self.failure_threshold
        self.last_failure_time = time.monotonic()


class BankCBSClient:
    """Asynchronous client for Core Banking System (CBS) integration and account creation."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 5.0,
        max_retries: int = 2,
        failure_threshold: int = 3,
        recovery_timeout: float = 5.0,
    ) -> None:
        url = (base_url or BANK_CBS_SANDBOX_URL).rstrip("/")
        if not url.endswith("/cbs/v1") and "cbs" not in url:
            url = f"{url}/cbs/v1"
        self.base_url = url
        self.api_key = api_key or BANK_API_KEY
        self.timeout = timeout
        self.max_retries = max_retries

        self.circuit_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )

    def _headers(self, idempotency_key: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def open_account(
        self,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches verified customer application to Core Banking System to issue an account."""
        if not payload.get("application_id") or not payload.get("bank_id"):
            raise BankCBSPayloadError(
                "Missing required attributes: application_id and bank_id are mandatory.",
                status_code=422,
                detail="application_id and bank_id required",
            )

        idem_key = idempotency_key or f"app_{payload['application_id']}"
        endpoint = f"{self.base_url}/accounts"

        if not self.circuit_breaker.can_execute():
            raise BankCBSCircuitBreakerOpenError()

        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        endpoint,
                        json=payload,
                        headers=self._headers(idem_key),
                    )

                if response.status_code in (200, 202):
                    self.circuit_breaker.record_success()
                    return response.json()

                error_data: Dict[str, Any] = {}
                try:
                    error_data = response.json()
                except Exception:
                    pass

                detail = error_data.get("detail", response.text)

                if response.status_code in (401, 403):
                    raise BankCBSAuthError(
                        f"Bank CBS authentication/authorization failed: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )
                elif response.status_code in (400, 422):
                    raise BankCBSPayloadError(
                        f"Bank CBS payload rejected: {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )
                elif response.status_code in (502, 503, 504):
                    self.circuit_breaker.record_failure()
                    raise BankCBSUnavailableError(
                        f"Bank CBS service unavailable ({response.status_code}): {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )
                else:
                    self.circuit_breaker.record_failure()
                    raise BankCBSError(
                        f"Bank CBS error ({response.status_code}): {detail}",
                        status_code=response.status_code,
                        detail=detail,
                    )

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                self.circuit_breaker.record_failure()

                if attempt < self.max_retries:
                    backoff = 0.1 * (2 ** attempt)
                    await asyncio.sleep(backoff)
                else:
                    raise BankCBSTimeoutError(
                        f"Bank CBS request timed out after {self.max_retries + 1} attempts: {exc}",
                        status_code=504,
                    ) from exc

        raise BankCBSConnectionError(f"Unexpected connection failure: {last_exc}")

    async def get_account_status(self, bank_reference: str) -> Dict[str, Any]:
        """Queries account status and issuance details by bank reference."""
        if not bank_reference:
            raise BankCBSPayloadError("bank_reference cannot be empty", status_code=422)

        endpoint = f"{self.base_url}/accounts/{bank_reference}"

        if not self.circuit_breaker.can_execute():
            raise BankCBSCircuitBreakerOpenError()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(endpoint, headers=self._headers())

            if response.status_code == 200:
                self.circuit_breaker.record_success()
                return response.json()

            error_data: Dict[str, Any] = {}
            try:
                error_data = response.json()
            except Exception:
                pass

            detail = error_data.get("detail", response.text)
            if response.status_code == 401:
                raise BankCBSAuthError(f"CBS auth error: {detail}", status_code=401)
            elif response.status_code == 404:
                raise BankCBSError(f"CBS account not found: {detail}", status_code=404)
            else:
                self.circuit_breaker.record_failure()
                raise BankCBSError(f"CBS error ({response.status_code}): {detail}", status_code=response.status_code)

        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            self.circuit_breaker.record_failure()
            raise BankCBSConnectionError(f"CBS connection failure: {exc}") from exc
