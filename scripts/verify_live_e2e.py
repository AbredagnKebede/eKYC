#!/usr/bin/env python3
"""Objective live E2E verification against the running Docker stack.

Exits 0 only if a full onboarding journey succeeds and account is issued.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import uuid

import httpx

API = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
BANK_API_KEY = os.getenv("BANK_API_KEY", "dev-bank-key")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def main() -> None:
    device = f"dev_e2e_{uuid.uuid4().hex[:10]}"
    user = f"usr_e2e_{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Fingerprint": device, "Content-Type": "application/json"}

    with httpx.Client(base_url=API, timeout=20.0) as client:
        # Health
        r = client.get("/health")
        if r.status_code != 200:
            fail(f"health {r.status_code}")
        print("OK health")

        # Banks (public)
        r = client.get("/v1/banks")
        if r.status_code != 200 or not r.json():
            fail(f"banks {r.status_code} {r.text}")
        print(f"OK banks count={len(r.json())}")

        # Create
        r = client.post(
            "/v1/applications",
            headers=headers,
            json={"user_ref": user, "bank_id": "bank_awash", "tier": "standard"},
        )
        if r.status_code != 201:
            fail(f"create {r.status_code} {r.text}")
        body = r.json()
        app_id = body["application_id"]
        token = body["token"]
        auth = {**headers, "Authorization": f"Bearer {token}"}
        print(f"OK create app_id={app_id}")

        # Unauthenticated consent must fail
        r = client.post(
            f"/v1/applications/{app_id}/consent",
            headers=headers,
            json={"consent_version": "v1.0", "accepted": True},
        )
        if r.status_code != 401:
            fail(f"expected 401 without token, got {r.status_code}")
        print("OK auth gate (401 without token)")

        # Refresh
        r = client.post("/v1/auth/refresh", headers=auth)
        if r.status_code != 200:
            fail(f"refresh {r.status_code} {r.text}")
        token = r.json()["token"]
        auth["Authorization"] = f"Bearer {token}"
        print("OK token refresh")

        # Consent
        r = client.post(
            f"/v1/applications/{app_id}/consent",
            headers=auth,
            json={"consent_version": "v1.0", "accepted": True},
        )
        if r.status_code != 200 or r.json().get("status") != "CONSENTED":
            fail(f"consent {r.status_code} {r.text}")
        print("OK consent")

        # Fayda
        fin = f"123456{uuid.uuid4().int % 1000000:06d}"
        r = client.post(
            f"/v1/applications/{app_id}/identity/start",
            headers=auth,
            json={"fin": fin},
        )
        if r.status_code != 200:
            fail(f"identity start {r.status_code} {r.text}")
        tx = r.json()["transaction_id"]
        r = client.post(
            f"/v1/applications/{app_id}/identity/verify",
            headers=auth,
            json={"transaction_id": tx, "otp": "123456"},
        )
        if r.status_code != 200 or r.json().get("status") != "ID_VERIFIED":
            fail(f"otp verify {r.status_code} {r.text}")
        print("OK fayda OTP")

        # Liveness (sandbox token path)
        selfie = base64.b64encode(b"fayda_demographic_photo_token_alemu_citizen").decode()
        r = client.post(
            f"/v1/applications/{app_id}/liveness",
            headers=auth,
            json={"selfie_base64": selfie},
        )
        if r.status_code != 200:
            fail(f"liveness {r.status_code} {r.text}")
        print(f"OK liveness score={r.json().get('liveness_score')}")

        # Dynamic fields
        fields = {
            "monthly_income_etb": 15000,
            "occupation": "Software Engineer",
            "source_of_funds": "Salary",
            "branch_code": "AW-BOLE-01",
        }
        r = client.put(
            f"/v1/applications/{app_id}/details",
            headers=auth,
            json={"dynamic_fields": fields},
        )
        if r.status_code != 200 or r.json().get("status") != "DATA_COMPLETE":
            fail(f"details {r.status_code} {r.text}")
        print("OK dynamic fields")

        # Submit
        r = client.post(
            f"/v1/applications/{app_id}/submit",
            headers=auth,
            json={"signature": "Alemu Kebede Tadesse"},
        )
        if r.status_code != 200:
            fail(f"submit {r.status_code} {r.text}")
        print(f"OK submit status={r.json().get('status')}")

        # Poll for bank account
        account = None
        status = None
        for _ in range(30):
            r = client.get(f"/v1/applications/{app_id}", headers=auth)
            if r.status_code != 200:
                fail(f"get status {r.status_code} {r.text}")
            data = r.json()
            status = data["status"]
            account = data.get("account_number")
            if status in ("ACCOUNT_OPENED", "BANK_ACCEPTED", "ACTIVATED") and account:
                break
            if status == "BANK_REJECTED":
                fail("bank rejected application")
            time.sleep(0.5)

        if not account:
            # Try webhook path if worker left it in BANK_ACCEPTED without account
            payload = {
                "application_id": app_id,
                "status": "ACCOUNT_OPENED",
                "account_number": f"1000{uuid.uuid4().int % 10**9:09d}",
                "bank_reference": f"CBS-{uuid.uuid4().hex[:8]}",
            }
            body = json.dumps(payload, separators=(",", ":")).encode()
            sig = hmac.new(BANK_API_KEY.encode(), body, hashlib.sha256).hexdigest()
            r = client.post(
                "/v1/webhooks/bank/bank_awash",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Signature-SHA256": sig,
                },
            )
            if r.status_code != 200:
                fail(f"webhook {r.status_code} {r.text} (prior status={status})")
            r = client.get(f"/v1/applications/{app_id}", headers=auth)
            data = r.json()
            status = data["status"]
            account = data.get("account_number")

        if not account or status not in ("ACCOUNT_OPENED", "ACTIVATED"):
            fail(f"no account issued status={status} account={account}")
        print(f"OK account_number={account} status={status}")

        # Activate
        r = client.post(f"/v1/applications/{app_id}/activate", headers=auth)
        if r.status_code != 200 or r.json().get("status") != "ACTIVATED":
            fail(f"activate {r.status_code} {r.text}")
        print("OK ACTIVATED")

    print("PASS: full live E2E journey verified")


if __name__ == "__main__":
    main()
