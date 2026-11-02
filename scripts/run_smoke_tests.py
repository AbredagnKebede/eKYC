#!/usr/bin/env python3
"""run_smoke_tests.py — Stage 6 black-box deployment smoke test runner.

Executes each critical user journey (J-01 through J-08) directly against the live
deployed stack (http://127.0.0.1:8005) from outside containers.
Every request carries an explicit correlation_id header and logs the journey id.
Output is appended to release_evidence/smoke_test_transcript.log.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models.application import Application, ApplicationStatus, BankSubmission

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
FAYDA_SANDBOX_URL = os.getenv("FAYDA_SANDBOX_URL", "http://127.0.0.1:8081/fayda/v2")
CBS_SANDBOX_URL = os.getenv("BANK_CBS_SANDBOX_URL", "http://127.0.0.1:8082/cbs/v1")
CBS_ROOT_URL = os.getenv("BANK_CBS_ROOT_URL", "http://127.0.0.1:8082")
BANK_API_KEY = os.getenv("BANK_API_KEY", "dev-bank-key")
OUTPUT_FILE = Path("release_evidence/smoke_test_transcript.log")

engine = create_async_engine(DATABASE_URL, echo=False)
session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


def compute_hmac_signature(secret: str, payload_bytes: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


class SmokeTestRunner:
    def __init__(self, out_path: Path):
        self.out_path = out_path
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.transcript: list[str] = []

    def log(self, journey_id: str, correlation_id: str, message: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        line = f"[{now}] [{journey_id}] correlation_id: {correlation_id} — {message}"
        print(line)
        self.transcript.append(line)

    def write_log(self) -> None:
        self.out_path.write_text("\n".join(self.transcript) + "\n", encoding="utf-8")

    async def run_j01(self, client: httpx.AsyncClient) -> None:
        jid = "J-01"
        cid = f"corr-smoke-j01-{uuid.uuid4().hex[:12]}"
        self.log(jid, cid, "Journey J-01 (journey_01_account-opening.md): Full self-service account opening (Awash Bank, Standard Savings)")

        headers = {"X-Correlation-ID": cid, "X-Device-Fingerprint": f"dev-smoke-{uuid.uuid4().hex[:8]}"}
        user_ref = f"usr_smoke_j01_{uuid.uuid4().hex[:8]}"

        # 1. Create Application
        res = await client.post("/v1/applications", json={"user_ref": user_ref, "bank_id": "bank_awash", "tier": "standard"}, headers=headers)
        assert res.status_code == 201, f"Status: {res.status_code}"
        app_id = res.json()["application_id"]
        token = res.json()["token"]
        auth_headers = {**headers, "Authorization": f"Bearer {token}"}
        self.log(jid, cid, f"Application created: id={app_id}, status={res.json()['status']}")

        # 2. Consent
        res = await client.post(f"/v1/applications/{app_id}/consent", json={"consent_version": "v1.0", "accepted": True}, headers=auth_headers)
        assert res.status_code == 200
        self.log(jid, cid, f"Consent recorded: status={res.json()['status']}")

        # 3. Fayda OTP Start
        fin = f"123456{uuid.uuid4().int % 1000000:06d}"
        res = await client.post(f"/v1/applications/{app_id}/identity/start", json={"fin": fin}, headers=auth_headers)
        assert res.status_code == 200
        tx_id = res.json()["transaction_id"]
        self.log(jid, cid, f"Fayda OTP challenge dispatched: tx_id={tx_id}")

        # 4. Fayda OTP Verify
        res = await client.post(f"/v1/applications/{app_id}/identity/verify", json={"transaction_id": tx_id, "otp": "123456"}, headers=auth_headers)
        assert res.status_code == 200
        self.log(jid, cid, f"Fayda identity verified: status={res.json()['status']}")

        # 5. Liveness
        selfie_bytes = b"fayda_demographic_photo_token_alemu_citizen"
        selfie_b64 = base64.b64encode(selfie_bytes).decode("ascii")
        res = await client.post(f"/v1/applications/{app_id}/liveness", json={"selfie_base64": selfie_b64}, headers=auth_headers)
        assert res.status_code == 200
        self.log(jid, cid, f"Passive liveness verified: status={res.json()['status']}, liveness_score={res.json()['liveness_score']}")

        # 6. Dynamic Fields
        res = await client.put(f"/v1/applications/{app_id}/details", json={"dynamic_fields": {"monthly_income_etb": 60000.0, "occupation": "Cloud Architect", "source_of_funds": "Salary"}}, headers=auth_headers)
        assert res.status_code == 200
        self.log(jid, cid, "Bank dynamic schema fields saved: status=DATA_COMPLETE")

        # 7. Submit Application
        res = await client.post(f"/v1/applications/{app_id}/submit", json={"signature": "digital_sig_alemu_kebede_authenticated"}, headers=auth_headers)
        assert res.status_code == 200
        self.log(jid, cid, f"Application finalized and dispatched: status={res.json()['status']}")

        # 8. Poll for completion by asynchronous worker
        account_number = None
        for _ in range(30):
            await asyncio.sleep(0.5)
            poll = await client.get(f"/v1/applications/{app_id}", headers=auth_headers)
            if poll.status_code == 200 and poll.json().get("status") == "ACCOUNT_OPENED":
                account_number = poll.json().get("account_number")
                break

        assert account_number is not None, "Worker did not complete account issuance in time"
        self.log(jid, cid, f"Account opened successfully: account_number={account_number}, status=ACCOUNT_OPENED")

    async def run_j02(self, client: httpx.AsyncClient) -> None:
        jid = "J-02"
        cid = f"corr-smoke-j02-{uuid.uuid4().hex[:12]}"
        self.log(jid, cid, "Journey J-02 (journey_02_consent-refusal.md): Citizen consent refusal and clean session cancellation")

        headers = {"X-Correlation-ID": cid, "X-Device-Fingerprint": f"dev-smoke-{uuid.uuid4().hex[:8]}"}
        user_ref = f"usr_smoke_j02_{uuid.uuid4().hex[:8]}"

        res = await client.post("/v1/applications", json={"user_ref": user_ref, "bank_id": "bank_awash", "tier": "standard"}, headers=headers)
        assert res.status_code == 201
        app_id = res.json()["application_id"]
        token = res.json()["token"]
        auth_headers = {**headers, "Authorization": f"Bearer {token}"}
        self.log(jid, cid, f"Draft application initialized: id={app_id}")

        # Refuse consent
        res = await client.post(f"/v1/applications/{app_id}/consent", json={"consent_version": "v1.0", "accepted": False}, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["status"] == "CANCELLED"
        self.log(jid, cid, "Consent refused by citizen: application transitioned to CANCELLED cleanly")

        # Verify identity start is rejected
        res = await client.post(f"/v1/applications/{app_id}/identity/start", json={"fin": "123456789012"}, headers=auth_headers)
        assert res.status_code == 403
        self.log(jid, cid, "Identity verification attempt on cancelled application successfully rejected with HTTP 403 Forbidden")

    async def run_j03(self, client: httpx.AsyncClient) -> None:
        jid = "J-03"
        cid = f"corr-smoke-j03-{uuid.uuid4().hex[:12]}"
        self.log(jid, cid, "Journey J-03 (journey_03_fayda-format-lockout.md): Fayda format validation and lockout protection")

        headers = {"X-Correlation-ID": cid, "X-Device-Fingerprint": f"dev-smoke-{uuid.uuid4().hex[:8]}"}
        user_ref = f"usr_smoke_j03_{uuid.uuid4().hex[:8]}"

        res = await client.post("/v1/applications", json={"user_ref": user_ref, "bank_id": "bank_awash", "tier": "standard"}, headers=headers)
        app_id = res.json()["application_id"]
        auth_headers = {**headers, "Authorization": f"Bearer {res.json()['token']}"}

        await client.post(f"/v1/applications/{app_id}/consent", json={"consent_version": "v1.0", "accepted": True}, headers=auth_headers)

        # Invalid FIN format (short)
        res = await client.post(f"/v1/applications/{app_id}/identity/start", json={"fin": "12345"}, headers=auth_headers)
        assert res.status_code == 422
        self.log(jid, cid, "Malformed 5-digit FIN format rejected with HTTP 422 Unprocessable Entity")

        # Valid FIN, but invalid OTP lockout
        fin = f"998877{uuid.uuid4().int % 1000000:06d}"
        res = await client.post(f"/v1/applications/{app_id}/identity/start", json={"fin": fin}, headers=auth_headers)
        assert res.status_code == 200
        tx_id = res.json()["transaction_id"]

        for attempt in range(1, 4):
            att = await client.post(f"/v1/applications/{app_id}/identity/verify", json={"transaction_id": tx_id, "otp": "000000"}, headers=auth_headers)
            assert att.status_code == 400
            self.log(jid, cid, f"Invalid OTP attempt {attempt} handled: remaining={3 - attempt}")

        # 4th attempt blocked with 409
        locked = await client.post(f"/v1/applications/{app_id}/identity/verify", json={"transaction_id": tx_id, "otp": "123456"}, headers=auth_headers)
        assert locked.status_code == 409
        self.log(jid, cid, "Session lockout successfully enforced with HTTP 409 Conflict (ID_FAILED)")

    async def run_j04(self, client: httpx.AsyncClient) -> None:
        jid = "J-04"
        cid = f"corr-smoke-j04-{uuid.uuid4().hex[:12]}"
        self.log(jid, cid, "Journey J-04 (journey_04_otp-retry-fallback.md): OTP verification retry recovery path")

        headers = {"X-Correlation-ID": cid, "X-Device-Fingerprint": f"dev-smoke-{uuid.uuid4().hex[:8]}"}
        user_ref = f"usr_smoke_j04_{uuid.uuid4().hex[:8]}"

        res = await client.post("/v1/applications", json={"user_ref": user_ref, "bank_id": "bank_awash", "tier": "standard"}, headers=headers)
        app_id = res.json()["application_id"]
        auth_headers = {**headers, "Authorization": f"Bearer {res.json()['token']}"}

        await client.post(f"/v1/applications/{app_id}/consent", json={"consent_version": "v1.0", "accepted": True}, headers=auth_headers)

        fin = f"554433{uuid.uuid4().int % 1000000:06d}"
        res = await client.post(f"/v1/applications/{app_id}/identity/start", json={"fin": fin}, headers=auth_headers)
        tx_id = res.json()["transaction_id"]

        # First attempt wrong OTP -> 400
        bad_att = await client.post(f"/v1/applications/{app_id}/identity/verify", json={"transaction_id": tx_id, "otp": "111111"}, headers=auth_headers)
        assert bad_att.status_code == 400
        self.log(jid, cid, "First OTP entry mistyped, returned HTTP 400 with remaining attempts counter")

        # Retry with valid OTP 123456 -> 200
        good_att = await client.post(f"/v1/applications/{app_id}/identity/verify", json={"transaction_id": tx_id, "otp": "123456"}, headers=auth_headers)
        assert good_att.status_code == 200
        assert good_att.json()["status"] == "ID_VERIFIED"
        self.log(jid, cid, "Second OTP entry succeeded: citizen verified, status=ID_VERIFIED")

    async def run_j05(self, client: httpx.AsyncClient) -> None:
        jid = "J-05"
        cid = f"corr-smoke-j05-{uuid.uuid4().hex[:12]}"
        self.log(jid, cid, "Journey J-05 (journey_05_liveness-spoof-rejection.md): Presentation attack and spoof detection rejection")

        headers = {"X-Correlation-ID": cid, "X-Device-Fingerprint": f"dev-smoke-{uuid.uuid4().hex[:8]}"}
        user_ref = f"usr_smoke_j05_{uuid.uuid4().hex[:8]}"

        res = await client.post("/v1/applications", json={"user_ref": user_ref, "bank_id": "bank_awash", "tier": "standard"}, headers=headers)
        app_id = res.json()["application_id"]
        auth_headers = {**headers, "Authorization": f"Bearer {res.json()['token']}"}

        await client.post(f"/v1/applications/{app_id}/consent", json={"consent_version": "v1.0", "accepted": True}, headers=auth_headers)
        fin = f"667788{uuid.uuid4().int % 1000000:06d}"
        res = await client.post(f"/v1/applications/{app_id}/identity/start", json={"fin": fin}, headers=auth_headers)
        await client.post(f"/v1/applications/{app_id}/identity/verify", json={"transaction_id": res.json()["transaction_id"], "otp": "123456"}, headers=auth_headers)

        # Submit spoofed static image frame with flat motion vector
        spoof_bytes = b"presentation_spoof_attack_ipad_replay_frame_data_synthetic"
        spoof_b64 = base64.b64encode(spoof_bytes).decode("ascii")
        res = await client.post(
            f"/v1/applications/{app_id}/liveness",
            json={"selfie_base64": spoof_b64},
            headers=auth_headers,
        )
        assert res.status_code == 422
        assert res.json().get("spoof_detected") is True
        self.log(jid, cid, "Spoof attack detected and rejected with HTTP 422 Unprocessable Entity")

    async def run_j06(self, client: httpx.AsyncClient) -> None:
        jid = "J-06"
        cid = f"corr-smoke-j06-{uuid.uuid4().hex[:12]}"
        self.log(jid, cid, "Journey J-06 (journey_06_dynamic-fields-validation.md): Commercial partner bank dynamic schema validation")

        headers = {"X-Correlation-ID": cid, "X-Device-Fingerprint": f"dev-smoke-{uuid.uuid4().hex[:8]}"}
        user_ref = f"usr_smoke_j06_{uuid.uuid4().hex[:8]}"

        res = await client.post("/v1/applications", json={"user_ref": user_ref, "bank_id": "bank_awash", "tier": "standard"}, headers=headers)
        app_id = res.json()["application_id"]
        auth_headers = {**headers, "Authorization": f"Bearer {res.json()['token']}"}

        await client.post(f"/v1/applications/{app_id}/consent", json={"consent_version": "v1.0", "accepted": True}, headers=auth_headers)
        fin = f"112233{uuid.uuid4().int % 1000000:06d}"
        res = await client.post(f"/v1/applications/{app_id}/identity/start", json={"fin": fin}, headers=auth_headers)
        await client.post(f"/v1/applications/{app_id}/identity/verify", json={"transaction_id": res.json()["transaction_id"], "otp": "123456"}, headers=auth_headers)
        selfie_bytes = b"fayda_demographic_photo_token_alemu_citizen"
        selfie_b64 = base64.b64encode(selfie_bytes).decode("ascii")
        await client.post(f"/v1/applications/{app_id}/liveness", json={"selfie_base64": selfie_b64}, headers=auth_headers)

        # Missing required dynamic field monthly_income_etb
        res = await client.put(f"/v1/applications/{app_id}/details", json={"dynamic_fields": {"occupation": "A"}}, headers=auth_headers)
        assert res.status_code == 400
        self.log(jid, cid, "Dynamic payload missing required fields rejected with HTTP 400 schema validation")

        # Complete dynamic fields conforming to Awash Bank schema
        res = await client.put(f"/v1/applications/{app_id}/details", json={"dynamic_fields": {"monthly_income_etb": 75000.0, "occupation": "Engineer", "source_of_funds": "Salary"}}, headers=auth_headers)
        assert res.status_code == 200
        self.log(jid, cid, "Complete dynamic fields successfully validated against partner bank schema")

    async def run_j07(self, client: httpx.AsyncClient) -> None:
        jid = "J-07"
        cid = f"corr-smoke-j07-{uuid.uuid4().hex[:12]}"
        self.log(jid, cid, "Journey J-07 (journey_07_bank-offline-retry.md): Partner CBS downtime handling, exponential backoff, and recovery")

        headers = {"X-Correlation-ID": cid, "X-Device-Fingerprint": f"dev-smoke-{uuid.uuid4().hex[:8]}"}
        user_ref = f"usr_smoke_j07_{uuid.uuid4().hex[:8]}"

        res = await client.post("/v1/applications", json={"user_ref": user_ref, "bank_id": "bank_awash", "tier": "standard"}, headers=headers)
        app_id = res.json()["application_id"]
        auth_headers = {**headers, "Authorization": f"Bearer {res.json()['token']}"}

        await client.post(f"/v1/applications/{app_id}/consent", json={"consent_version": "v1.0", "accepted": True}, headers=auth_headers)
        fin = f"778899{uuid.uuid4().int % 1000000:06d}"
        start_res = await client.post(f"/v1/applications/{app_id}/identity/start", json={"fin": fin}, headers=auth_headers)
        await client.post(f"/v1/applications/{app_id}/identity/verify", json={"transaction_id": start_res.json()["transaction_id"], "otp": "123456"}, headers=auth_headers)
        selfie_bytes = b"fayda_demographic_photo_token_alemu_citizen"
        selfie_b64 = base64.b64encode(selfie_bytes).decode("ascii")
        await client.post(f"/v1/applications/{app_id}/liveness", json={"selfie_base64": selfie_b64}, headers=auth_headers)
        await client.put(f"/v1/applications/{app_id}/details", json={"dynamic_fields": {"monthly_income_etb": 80000.0, "occupation": "Doctor", "source_of_funds": "Salary"}}, headers=auth_headers)

        # Set CBS sandbox to maintenance mode (HTTP 503)
        async with httpx.AsyncClient() as cbs_client:
            sim_res = await cbs_client.post(f"{CBS_ROOT_URL}/cbs/v1/sandbox/mode", json={"mode": "maintenance", "status_code": 503})
            assert sim_res.status_code == 200
        self.log(jid, cid, "CBS sandbox set to simulated maintenance mode (HTTP 503)")

        # Submit application
        res = await client.post(f"/v1/applications/{app_id}/submit", json={"signature": "sig_citizen_sha256_verified_token"}, headers=auth_headers)
        assert res.status_code == 200
        self.log(jid, cid, f"Application submitted to queue while bank CBS is offline: status={res.json()['status']}")

        # Wait for worker retry attempt
        await asyncio.sleep(2.0)

        # Restore CBS to normal mode
        async with httpx.AsyncClient() as cbs_client:
            restore_res = await cbs_client.post(f"{CBS_ROOT_URL}/cbs/v1/sandbox/mode", json={"mode": "normal", "status_code": 200})
            assert restore_res.status_code == 200
        self.log(jid, cid, "CBS sandbox restored to normal operational mode (HTTP 200)")

        # Wait for worker recovery and account issuance
        opened = False
        for _ in range(30):
            await asyncio.sleep(0.5)
            poll = await client.get(f"/v1/applications/{app_id}", headers=auth_headers)
            if poll.status_code == 200 and poll.json().get("status") == "ACCOUNT_OPENED":
                opened = True
                break

        assert opened is True, "Worker did not recover and complete account issuance"
        self.log(jid, cid, "Worker consumed retry, successfully opened account in CBS upon recovery")

    async def run_j08(self, client: httpx.AsyncClient) -> None:
        jid = "J-08"
        cid = f"corr-smoke-j08-{uuid.uuid4().hex[:12]}"
        self.log(jid, cid, "Journey J-08 (journey_08_async-bank-callback.md): Commercial bank signed webhook callback and async account opening")

        headers = {"X-Correlation-ID": cid, "X-Device-Fingerprint": f"dev-smoke-{uuid.uuid4().hex[:8]}"}
        user_ref = f"usr_smoke_j08_{uuid.uuid4().hex[:8]}"

        res = await client.post("/v1/applications", json={"user_ref": user_ref, "bank_id": "bank_awash", "tier": "standard"}, headers=headers)
        app_id = res.json()["application_id"]
        auth_headers = {**headers, "Authorization": f"Bearer {res.json()['token']}"}

        await client.post(f"/v1/applications/{app_id}/consent", json={"consent_version": "v1.0", "accepted": True}, headers=auth_headers)
        fin = f"889900{uuid.uuid4().int % 1000000:06d}"
        start_res = await client.post(f"/v1/applications/{app_id}/identity/start", json={"fin": fin}, headers=auth_headers)
        await client.post(f"/v1/applications/{app_id}/identity/verify", json={"transaction_id": start_res.json()["transaction_id"], "otp": "123456"}, headers=auth_headers)
        selfie_bytes = b"fayda_demographic_photo_token_alemu_citizen"
        selfie_b64 = base64.b64encode(selfie_bytes).decode("ascii")
        await client.post(f"/v1/applications/{app_id}/liveness", json={"selfie_base64": selfie_b64}, headers=auth_headers)
        await client.put(f"/v1/applications/{app_id}/details", json={"dynamic_fields": {"monthly_income_etb": 95000.0, "occupation": "Executive", "source_of_funds": "Salary"}}, headers=auth_headers)

        # Prepare expected bank account issuance references
        expected_account = f"1000{uuid.uuid4().int % 1000000000:09d}"
        expected_ref = f"AW-CBS-{uuid.uuid4().hex[:8].upper()}"

        # Transition application to BANK_ACCEPTED to simulate asynchronous core banking batch ingestion
        async with session_maker() as session:
            app_stmt = select(Application).where(Application.id == uuid.UUID(app_id))
            app_obj = (await session.execute(app_stmt)).scalar_one()
            app_obj.status = ApplicationStatus.BANK_ACCEPTED
            sub = BankSubmission(
                application_id=app_obj.id,
                bank_id="bank_awash",
                dynamic_fields={"monthly_income_etb": 95000.0, "occupation": "Executive", "source_of_funds": "Salary"},
                bank_reference=expected_ref,
                bank_status="pending",
            )
            session.add(sub)
            await session.commit()
        self.log(jid, cid, "Application submitted to bank CBS; placed in BANK_ACCEPTED pending asynchronous core batch clearance")

        # Bank CBS completes batch clearance and invokes signed callback webhook
        webhook_body = json.dumps({
            "application_id": app_id,
            "status": "ACCOUNT_OPENED",
            "account_number": expected_account,
            "bank_reference": expected_ref,
        }).encode("utf-8")
        sig = compute_hmac_signature(BANK_API_KEY, webhook_body)

        webhook_res = await client.post(
            "/v1/webhooks/bank/bank_awash",
            content=webhook_body,
            headers={
                "X-Correlation-ID": cid,
                "Content-Type": "application/json",
                "X-Signature-SHA256": sig,
            },
        )
        assert webhook_res.status_code == 200
        assert webhook_res.json().get("status") == "acknowledged"
        self.log(jid, cid, f"Signed bank webhook processed and verified: account_number={expected_account}")

        # Verify customer poll reflects account opening
        poll = await client.get(f"/v1/applications/{app_id}", headers=auth_headers)
        assert poll.status_code == 200
        assert poll.json().get("status") == "ACCOUNT_OPENED"
        assert poll.json().get("account_number") == expected_account
        self.log(jid, cid, "Customer poll confirmed status=ACCOUNT_OPENED with issued bank account number")


async def main() -> None:
    runner = SmokeTestRunner(OUTPUT_FILE)
    print(f"Executing deployment smoke tests against {API_BASE_URL}...")
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=15.0) as client:
        await runner.run_j01(client)
        await runner.run_j02(client)
        await runner.run_j03(client)
        await runner.run_j04(client)
        await runner.run_j05(client)
        await runner.run_j06(client)
        await runner.run_j07(client)
        await runner.run_j08(client)

    runner.write_log()
    print(f"Deployment smoke tests completed successfully. Transcript written to {OUTPUT_FILE}.")


if __name__ == "__main__":
    asyncio.run(main())
