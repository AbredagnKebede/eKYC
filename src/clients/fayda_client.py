import asyncio
import os
import re
from typing import Any, Dict, Optional
import httpx

FAYDA_API_KEY = os.getenv("FAYDA_API_KEY", "dev-fayda-key")
FAYDA_SANDBOX_URL = os.getenv("FAYDA_SANDBOX_URL", "http://127.0.0.1:8081/fayda/v2")


class FaydaError(Exception):
    """Base exception for Fayda eKYC integration errors."""
    def __init__(self, message: str, status_code: int = 500, detail: Optional[str] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class FaydaFormatError(FaydaError):
    """Raised when Fayda FIN/FAN identifier format is invalid."""
    pass


class FaydaTimeoutError(FaydaError):
    """Raised when external Fayda API call times out after retries."""
    pass


class FaydaVerificationError(FaydaError):
    """Raised when OTP is invalid or verification challenge failed."""
    pass


class FaydaClient:
    """Asynchronous client communicating with EthSwitch VeriFayda 2 eKYC Gateway."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 5.0,
        max_retries: int = 2,
    ) -> None:
        self.base_url = (base_url or FAYDA_SANDBOX_URL).rstrip("/")
        # Ensure base_url contains version path
        if not self.base_url.endswith("/v2"):
            self.base_url = f"{self.base_url}/fayda/v2" if "fayda" not in self.base_url else f"{self.base_url}/v2"
        self.api_key = api_key or FAYDA_API_KEY
        self.timeout = timeout
        self.max_retries = max_retries

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post_with_retry(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload, headers=self._headers())

                if response.status_code == 200:
                    return response.json()

                error_data = {}
                try:
                    error_data = response.json()
                except Exception:
                    pass

                detail = error_data.get("detail", response.text)

                if response.status_code == 422:
                    raise FaydaFormatError(f"Fayda format error: {detail}", status_code=422, detail=detail)
                elif response.status_code in (400, 403, 410):
                    raise FaydaVerificationError(f"Fayda verification failure: {detail}", status_code=response.status_code, detail=detail)
                else:
                    raise FaydaError(f"Fayda API error {response.status_code}: {detail}", status_code=response.status_code, detail=detail)

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    # Exponential backoff with jitter
                    backoff = 0.1 * (2 ** attempt)
                    await asyncio.sleep(backoff)
                else:
                    raise FaydaTimeoutError(
                        f"Fayda API request timed out after {self.max_retries + 1} attempts: {exc}",
                        status_code=504,
                    ) from exc

        raise FaydaError(f"Unexpected request failure: {last_exc}")

    async def generate_otp(self, fin: str) -> Dict[str, Any]:
        """Initiates an eKYC session by dispatching an SMS OTP to the citizen."""
        clean_fin = fin.strip().replace("-", "").replace(" ", "")
        if not re.fullmatch(r"\d{12}", clean_fin):
            raise FaydaFormatError(
                f"Fayda FIN must be exactly 12 numeric digits (got {len(clean_fin)} characters)",
                status_code=422,
                detail="12 numeric digits required",
            )

        return await self._post_with_retry("/otp/generate", {"fin": clean_fin})

    async def verify_otp(self, transaction_id: str, otp: str) -> Dict[str, Any]:
        """Submits citizen OTP and receives signed demographic assertions."""
        clean_otp = otp.strip()
        if not clean_otp:
            raise FaydaVerificationError("OTP code cannot be empty", status_code=400)

        return await self._post_with_retry(
            "/otp/verify",
            {"transaction_id": transaction_id, "otp": clean_otp},
        )
