import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict

PORT = int(os.getenv("PORT", "8081"))


class FaydaSandboxHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path in ("/health", "/healthz"):
            self._send_json(200, {"status": "healthy", "service": "fayda-sandbox"})
        else:
            self._send_json(404, {"error": "Not Found", "path": self.path})

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        auth_header = self.headers.get("Authorization", "")

        # 1. OTP Challenge Generation
        if self.path == "/fayda/v2/otp/generate":
            fin = str(data.get("fin", "")).strip()
            if not re.fullmatch(r"\d{12}", fin):
                self._send_json(422, {
                    "type": "https://errors.ekyc.et/INVALID_FAYDA_FORMAT",
                    "title": "Invalid Fayda Identifier",
                    "status": 422,
                    "detail": "Fayda FIN must be exactly 12 numeric digits.",
                })
                return

            self._send_json(200, {
                "status": "OTP_SENT",
                "transaction_id": f"tx_fayda_{fin[-4:]}",
                "fin_last4": fin[-4:],
                "expires_in": 180,
                "mock_otp_hint": "123456",
            })
            return

        # 2. OTP Verification & Identity Assertions
        elif self.path == "/fayda/v2/otp/verify":
            tx_id = data.get("transaction_id", "")
            otp = str(data.get("otp", "")).strip()

            if otp == "999999":
                self._send_json(410, {
                    "type": "https://errors.ekyc.et/OTP_EXPIRED",
                    "title": "OTP Expired",
                    "status": 410,
                    "detail": "The OTP challenge has expired.",
                })
                return

            if otp != "123456":
                self._send_json(400, {
                    "type": "https://errors.ekyc.et/INVALID_OTP",
                    "title": "Invalid OTP",
                    "status": 400,
                    "detail": "The supplied OTP code is incorrect.",
                })
                return

            self._send_json(200, {
                "status": "VERIFIED",
                "transaction_id": tx_id,
                "demographics": {
                    "full_name": "Alemu Kebede Tadesse",
                    "date_of_birth": "1992-05-18",
                    "gender": "MALE",
                    "address": "Bole Subcity, Woreda 03, Addis Ababa",
                    "fayda_id_hash": "fayda_sha256_mock_hash_889900",
                },
                "photo_token": "photo_blob_fayda_citizen_verified_base64",
                "signature": "fayda_nidp_signed_assertion_token_rsa2048",
            })
            return

        self._send_json(404, {"error": "Not Found", "path": self.path})

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard logs in tests
        pass


def run_server(port: int = PORT) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), FaydaSandboxHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server(PORT)
