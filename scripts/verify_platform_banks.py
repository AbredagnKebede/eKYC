#!/usr/bin/env python3
"""Objective checks: DB-backed banks, platform onboarding, cross-scope JWT isolation.

Exits 0 only when every check prints OK.
Requires a running API (default http://127.0.0.1:8005).
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import httpx

API = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
PLATFORM_EMAIL = os.getenv("PLATFORM_OPERATOR_EMAIL", "platform@ekyc.local")
PLATFORM_PASSWORD = os.getenv("PLATFORM_OPERATOR_PASSWORD", "ChangeMePlatform!1")
PORTAL_PASSWORD = os.getenv("BANK_PORTAL_BOOTSTRAP_PASSWORD", "ChangeMeBankPortal1!")
ROOT = Path(__file__).resolve().parents[1]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"OK {msg}")


def static_portal_no_hardcoded_banks() -> None:
    portal = ROOT / "bank-portal" / "src" / "components" / "PortalApp.tsx"
    text = portal.read_text(encoding="utf-8")
    if "const BANKS" in text or "BANKS: { id: string" in text:
        fail("PortalApp still hardcodes BANKS catalogue")
    if "fetchPublicBanks" not in text:
        fail("PortalApp does not fetch banks from API")
    ok("portal login banks fetched via fetchPublicBanks (no hardcoded BANKS)")


def main() -> None:
    static_portal_no_hardcoded_banks()

    with httpx.Client(base_url=API, timeout=60.0) as client:
        r = client.get("/health")
        if r.status_code != 200:
            fail(f"API health {r.status_code} at {API}")
        ok(f"API healthy at {API}")

        r = client.get("/v1/banks")
        if r.status_code != 200:
            fail(f"GET /v1/banks {r.status_code} {r.text}")
        banks = r.json()
        if not isinstance(banks, list) or len(banks) < 8:
            fail(f"expected seeded active banks (>=8), got {len(banks) if isinstance(banks, list) else banks}")
        public_ids = {b["bank_id"] for b in banks}
        ok(f"GET /v1/banks returns {len(banks)} active banks")

        # Platform login
        r = client.post(
            "/v1/platform/auth/login",
            json={"email": PLATFORM_EMAIL, "password": PLATFORM_PASSWORD},
        )
        if r.status_code != 200:
            fail(f"platform login {r.status_code} {r.text}")
        platform_token = r.json()["token"]
        platform_headers = {"Authorization": f"Bearer {platform_token}"}
        ok("platform operator login")

        # Create unique test bank
        suffix = uuid.uuid4().hex[:8]
        bank_id = f"bank_test_portal_{suffix}"
        r = client.post(
            "/v1/platform/banks",
            headers=platform_headers,
            json={
                "bank_id": bank_id,
                "bank_name": f"Test Portal Bank {suffix}",
                "short_code": "TPB",
                "hq_city": "Addis Ababa",
                "supported_tiers": ["standard", "diaspora"],
                "super_admin_email": f"admin@{suffix}.test.local",
            },
        )
        if r.status_code != 201:
            fail(f"create bank {r.status_code} {r.text}")
        body = r.json()
        admin_email = body["super_admin_email"]
        temp_password = body["temporary_password"]
        if not temp_password or len(temp_password) < 8:
            fail("temporary_password missing from create response")
        ok(f"platform created {bank_id} with one-time Super Admin password")

        # Appears in public list
        r = client.get("/v1/banks")
        ids = {b["bank_id"] for b in r.json()}
        if bank_id not in ids:
            fail(f"new bank {bank_id} missing from public GET /v1/banks")
        ok("new bank appears in public GET /v1/banks")

        # Super Admin can login to bank portal
        r = client.post(
            "/v1/bank-portal/auth/login",
            json={"email": admin_email, "password": temp_password, "bank_id": bank_id},
        )
        if r.status_code != 200:
            fail(f"bank portal login with issued creds {r.status_code} {r.text}")
        bank_token = r.json()["token"]
        bank_headers = {"Authorization": f"Bearer {bank_token}"}
        ok("issued Super Admin can sign into bank portal")

        # Cross-scope: platform token rejected on bank-portal queues
        r = client.get("/v1/bank-portal/queues/outbound", headers=platform_headers)
        if r.status_code not in (401, 403):
            fail(f"platform token should be rejected on bank queues, got {r.status_code}")
        ok("platform token rejected on bank-portal queues")

        # Cross-scope: bank token rejected on platform banks
        r = client.get("/v1/platform/banks", headers=bank_headers)
        if r.status_code not in (401, 403):
            fail(f"bank token should be rejected on platform banks, got {r.status_code}")
        ok("bank token rejected on platform banks")

        # Deactivate → public list excludes
        r = client.patch(
            f"/v1/platform/banks/{bank_id}",
            headers=platform_headers,
            json={"active": False},
        )
        if r.status_code != 200:
            fail(f"deactivate {r.status_code} {r.text}")
        time.sleep(0.2)
        r = client.get("/v1/banks")
        ids = {b["bank_id"] for b in r.json()}
        if bank_id in ids:
            fail(f"inactive bank {bank_id} still in public list")
        ok("deactivated bank excluded from public GET /v1/banks")

        # Seeded banks still present (minus our deactivated test)
        still = public_ids & ids
        if len(still) < min(8, len(public_ids)):
            fail("seeded catalogue shrank unexpectedly after deactivate")
        ok("seeded active catalogue intact after test bank deactivate")

        # Schema PUT requires platform auth
        r = client.put(
            f"/v1/banks/{next(iter(public_ids))}/schema",
            json={"dynamic_schema": {"type": "object", "properties": {}}},
        )
        if r.status_code not in (401, 403):
            fail(f"unauthenticated schema PUT should fail, got {r.status_code}")
        ok("PUT /v1/banks/{{id}}/schema requires platform auth")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
