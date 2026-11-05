import hashlib
import hmac
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional
from urllib import request as urlrequest

PORT = int(os.getenv("PORT", "8082"))
EXPECTED_API_KEY = os.getenv("BANK_API_KEY", "dev-bank-key")
# Platform webhook base, e.g. http://api:8000 — sandbox posts AS-08 callbacks here.
EKYC_WEBHOOK_BASE = os.getenv("EKYC_WEBHOOK_BASE", os.getenv("API_BASE_URL", "http://api:8000")).rstrip("/")
WEBHOOK_DELAY_SECONDS = float(os.getenv("CBS_WEBHOOK_DELAY_SECONDS", "2"))


class BankCBSSandboxState:
    """In-memory state for CBS sandbox simulation."""
    def __init__(self) -> None:
        self.idempotency_store: Dict[str, Dict[str, Any]] = {}
        self.accounts_by_ref: Dict[str, Dict[str, Any]] = {}
        self.simulation_mode: str = "normal"  # normal, maintenance, error, timeout
        self.failure_status_code: int = 503

    def reset(self) -> None:
        self.idempotency_store.clear()
        self.accounts_by_ref.clear()
        self.simulation_mode = "normal"
        self.failure_status_code = 503


STATE = BankCBSSandboxState()


class BankCBSSandboxHandler(BaseHTTPRequestHandler):
    """HTTP handler simulating Commercial Bank Core Banking System (CBS)."""

    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _check_auth(self) -> bool:
        auth_header = self.headers.get("Authorization", "")
        api_key_header = self.headers.get("X-Bank-Api-Key", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif auth_header:
            token = auth_header.strip()
        elif api_key_header:
            token = api_key_header.strip()

        return token == EXPECTED_API_KEY

    def do_GET(self) -> None:
        # Health check
        if self.path in ("/health", "/healthz"):
            self._send_json(200, {"status": "healthy", "service": "cbs-sandbox"})
            return

        # Status check for existing account
        if self.path.startswith("/cbs/v1/accounts/"):
            if not self._check_auth():
                self._send_json(401, {
                    "type": "https://errors.ekyc.et/UNAUTHORIZED",
                    "title": "Unauthorized",
                    "status": 401,
                    "detail": "Invalid or missing Bank API Key",
                })
                return

            bank_ref = self.path.split("/")[-1].split("?")[0]
            if bank_ref in STATE.accounts_by_ref:
                self._send_json(200, STATE.accounts_by_ref[bank_ref])
            else:
                self._send_json(404, {
                    "type": "https://errors.ekyc.et/ACCOUNT_NOT_FOUND",
                    "title": "Account Not Found",
                    "status": 404,
                    "detail": f"Account with reference {bank_ref} not found.",
                })
            return

        self._send_json(404, {"error": "Not Found", "path": self.path})

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        # 1. Admin / Simulation control endpoint
        if self.path == "/cbs/v1/sandbox/mode":
            mode = data.get("mode", "normal")
            status_code = int(data.get("status_code", 503))
            STATE.simulation_mode = mode
            STATE.failure_status_code = status_code
            self._send_json(200, {
                "status": "mode_updated",
                "simulation_mode": STATE.simulation_mode,
                "status_code": STATE.failure_status_code,
            })
            return

        if self.path == "/cbs/v1/sandbox/reset":
            STATE.reset()
            self._send_json(200, {"status": "reset_successful"})
            return

        # 2. Account opening endpoints: /cbs/v1/accounts or /cbs/v1/accounts/open
        if self.path in ("/cbs/v1/accounts", "/cbs/v1/accounts/open"):
            # Check authentication
            if not self._check_auth():
                self._send_json(401, {
                    "type": "https://errors.ekyc.et/UNAUTHORIZED",
                    "title": "Unauthorized",
                    "status": 401,
                    "detail": "Invalid or missing Bank API Key",
                })
                return

            # Check simulated error headers or state
            sim_header = self.headers.get("X-CBS-Simulate-Error", "")
            if sim_header:
                code = int(sim_header)
                self._send_json(code, {
                    "type": "https://errors.ekyc.et/SIMULATED_CBS_OUTAGE",
                    "title": "Simulated CBS Outage",
                    "status": code,
                    "detail": f"Simulated CBS status {code}",
                })
                return

            if STATE.simulation_mode == "maintenance":
                self._send_json(STATE.failure_status_code, {
                    "type": "https://errors.ekyc.et/CBS_MAINTENANCE",
                    "title": "Service Unavailable",
                    "status": STATE.failure_status_code,
                    "detail": "Core Banking System is undergoing scheduled maintenance.",
                })
                return
            elif STATE.simulation_mode == "error":
                self._send_json(STATE.failure_status_code, {
                    "type": "https://errors.ekyc.et/CBS_INTERNAL_ERROR",
                    "title": "CBS Internal Error",
                    "status": STATE.failure_status_code,
                    "detail": "Core Banking System internal processing error.",
                })
                return

            # Validate payload
            application_id = data.get("application_id")
            bank_id = data.get("bank_id")
            if not application_id or not bank_id:
                self._send_json(422, {
                    "type": "https://errors.ekyc.et/INVALID_PAYLOAD",
                    "title": "Invalid Payload",
                    "status": 422,
                    "detail": "Missing required fields: application_id and bank_id are required.",
                })
                return

            # Idempotency handling
            idempotency_key = (
                self.headers.get("Idempotency-Key")
                or self.headers.get("X-Idempotency-Key")
                or data.get("idempotency_key")
                or f"app_{application_id}"
            )

            if idempotency_key in STATE.idempotency_store:
                cached_response = STATE.idempotency_store[idempotency_key]
                self._send_json(200, cached_response)
                return

            # Check if this account needs manual compliance review
            tier = data.get("tier", data.get("account_tier", "standard"))
            dynamic_fields = data.get("dynamic_fields", {})
            requires_review = bool(dynamic_fields.get("requires_review", False) or tier == "enterprise")

            now_iso = datetime.now(timezone.utc).isoformat()
            short_id = str(application_id).replace("-", "")[:8]
            bank_ref = f"CBS-{bank_id.upper()}-{short_id}"

            if requires_review:
                response_payload = {
                    "status": "PENDING_REVIEW",
                    "bank_id": bank_id,
                    "application_id": str(application_id),
                    "bank_reference": bank_ref,
                    "account_number": None,
                    "account_tier": tier,
                    "created_at": now_iso,
                    "message": "Application submitted for AML compliance officer review.",
                }
                # Async callback (sandbox AS-08): after delay, issue account via signed webhook.
                _schedule_review_webhook(
                    bank_id=str(bank_id),
                    application_id=str(application_id),
                    bank_reference=bank_ref,
                )
            else:
                # Deterministic account number based on hash of application_id and bank_id
                acc_seed = int(hashlib.sha256(f"{application_id}:{bank_id}".encode()).hexdigest()[:10], 16)
                account_number = f"1000{acc_seed % 1000000000:09d}"

                response_payload = {
                    "status": "SUCCESS",
                    "bank_id": bank_id,
                    "application_id": str(application_id),
                    "bank_reference": bank_ref,
                    "account_number": account_number,
                    "account_tier": tier,
                    "created_at": now_iso,
                    "message": "Account opened successfully in Core Banking System.",
                }

            # Cache idempotency record
            STATE.idempotency_store[idempotency_key] = response_payload
            STATE.accounts_by_ref[bank_ref] = response_payload

            status_to_return = 202 if requires_review else 200
            self._send_json(status_to_return, response_payload)
            return

        self._send_json(404, {"error": "Not Found", "path": self.path})

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard logs in tests
        pass


def _schedule_review_webhook(*, bank_id: str, application_id: str, bank_reference: str) -> None:
    """Fire a signed ACCOUNT_OPENED webhook after a short delay (sandbox only)."""

    def _worker() -> None:
        time.sleep(WEBHOOK_DELAY_SECONDS)
        acc_seed = int(hashlib.sha256(f"{application_id}:{bank_id}:approved".encode()).hexdigest()[:10], 16)
        account_number = f"2000{acc_seed % 1000000000:09d}"
        body = json.dumps(
            {
                "application_id": application_id,
                "status": "ACCOUNT_OPENED",
                "account_number": account_number,
                "bank_reference": bank_reference,
            }
        ).encode("utf-8")
        sig = hmac.new(EXPECTED_API_KEY.encode(), body, hashlib.sha256).hexdigest()
        url = f"{EKYC_WEBHOOK_BASE}/v1/webhooks/bank/{bank_id}"
        req = urlrequest.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": sig,
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=10) as resp:
                resp.read()
            # Update local sandbox account record for status polls
            STATE.accounts_by_ref[bank_reference] = {
                "status": "SUCCESS",
                "bank_id": bank_id,
                "application_id": application_id,
                "bank_reference": bank_reference,
                "account_number": account_number,
            }
        except Exception as exc:  # noqa: BLE001 — sandbox best-effort
            sys.stderr.write(f"cbs-sandbox webhook failed: {exc}\n")

    threading.Thread(target=_worker, daemon=True).start()


def run_server(port: int = PORT) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), BankCBSSandboxHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server(PORT)
