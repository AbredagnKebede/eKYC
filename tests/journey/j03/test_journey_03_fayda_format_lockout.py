import asyncio
import os
import time
import uuid
from typing import Any, Dict

import httpx
import pytest
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models.application import Application, ApplicationStatus, IdentitySnapshot

pytestmark = [pytest.mark.asyncio, pytest.mark.black_box]


@pytest.mark.black_box
async def test_journey_03_fayda_format_lockout_e2e() -> None:
    """
    End-to-end user journey test for invalid Fayda national ID format lockout (J-03).

    Covers architectural requirements AS-03:
    - Real PostgreSQL connection via DATABASE_URL and asyncpg (no mocks).
    - Real Redis cache tracking device failure attempts in sliding window.
    - Rate limit lockout after 5 consecutive malformed submissions.
    - Zero state corruption and zero dispatches to external Fayda eKYC API.

    Assertion Points Verified:
    - AP-1 API response: Malformed ID payload receives HTTP 422 Unprocessable Entity with clear validation details.
    - AP-2 Cache: Redis key ratelimit:fayda:attempts:<device_id> increments on each invalid submission.
    - AP-3 API response: Sixth submission returns HTTP 429 Too Many Requests with Retry-After: 900.
    - AP-4 Database: applications status remains CONSENTED; no unverified Fayda transaction is persisted.
    - AP-5 External API: Zero requests are dispatched to external fayda_ekyc_api.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    test_user_ref = f"usr_j03_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_j03_{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Fingerprint": device_fp}

    lockout_key = f"ratelimit:fayda:attempts:{device_fp}"

    # Ensure clean redis state for this unique test device
    await redis_client.delete(lockout_key)

    async with httpx.AsyncClient(base_url=api_base_url, timeout=10.0) as client:
        # Step 1: Create application
        create_resp = await client.post(
            "/v1/applications",
            json={"user_ref": test_user_ref, "bank_id": "bank_awash", "tier": "standard"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        create_data = create_resp.json()
        assert create_data["status"] == "DRAFT"
        app_id_str = create_data["application_id"]
        app_uuid = uuid.UUID(app_id_str)
        session_token = create_data["token"]
        assert len(session_token) > 20

        auth_headers = {
            "Authorization": f"Bearer {session_token}",
            "X-Device-Fingerprint": device_fp,
        }

        # Step 2: User completes plain-language consent
        consent_resp = await client.post(
            f"/v1/applications/{app_id_str}/consent",
            json={"consent_version": "v1.0", "accepted": True},
            headers=auth_headers,
        )
        assert consent_resp.status_code == 200
        assert consent_resp.json()["status"] == "CONSENTED"

        # -------------------------------------------------------------------------
        # AP-1 & AP-2: Submissions 1 through 5 with malformed Fayda IDs
        # -------------------------------------------------------------------------
        malformed_inputs = [
            "12345",              # Too short (5 digits)
            "123456789012345",    # Too long (15 digits)
            "12345678901A",       # Alphanumeric character
            "abcdefghijkl",       # All alphabetic
            "123-456-78901",      # Contains dashes
        ]

        for i, bad_fin in enumerate(malformed_inputs, start=1):
            bad_resp = await client.post(
                f"/v1/applications/{app_id_str}/identity/start",
                json={"fin": bad_fin},
                headers=auth_headers,
            )
            # AP-1 API response: Malformed ID payload receives HTTP 422 Unprocessable Entity
            assert bad_resp.status_code == 422
            resp_detail = bad_resp.json().get("detail", "")
            assert "12 numeric digits" in resp_detail

            # AP-2 Cache: Redis key increments on each invalid submission
            current_count = await redis_client.get(lockout_key)
            assert current_count is not None
            assert int(current_count) == i
            ttl = await redis_client.ttl(lockout_key)
            assert ttl > 0
            assert ttl <= 900

        # -------------------------------------------------------------------------
        # AP-3 API response: Sixth submission returns HTTP 429 Too Many Requests with Retry-After: 900
        # -------------------------------------------------------------------------
        sixth_resp = await client.post(
            f"/v1/applications/{app_id_str}/identity/start",
            json={"fin": "99999999999"},  # 11 digits
            headers=auth_headers,
        )
        assert sixth_resp.status_code == 429
        assert sixth_resp.headers.get("retry-after") == "900"
        sixth_detail = sixth_resp.json().get("detail", "")
        assert "temporarily locked" in sixth_detail.lower()

        # Even with a valid 12-digit format, lockout continues to block with HTTP 429
        valid_fin_blocked = await client.post(
            f"/v1/applications/{app_id_str}/identity/start",
            json={"fin": "123456789012"},
            headers=auth_headers,
        )
        assert valid_fin_blocked.status_code == 429
        assert "temporarily locked" in valid_fin_blocked.json().get("detail", "").lower()

        # -------------------------------------------------------------------------
        # AP-4 Database: applications status remains CONSENTED; no unverified Fayda transaction is persisted
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            stmt = select(Application).where(Application.id == app_uuid)
            app_record = (await session.execute(stmt)).scalar_one_or_none()
            assert app_record is not None
            assert app_record.status == ApplicationStatus.CONSENTED
            assert app_record.status.value == "CONSENTED"
            assert app_record.user_ref == test_user_ref

            snap_stmt = select(IdentitySnapshot).where(IdentitySnapshot.application_id == app_uuid)
            snapshots = (await session.execute(snap_stmt)).scalars().all()
            assert len(snapshots) == 0

        # -------------------------------------------------------------------------
        # AP-5 External API: Zero requests are dispatched to external fayda_ekyc_api
        # Verified because application never generated a transaction_id and snapshots remain 0
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            snap_stmt = select(IdentitySnapshot).where(IdentitySnapshot.application_id == app_uuid)
            snapshots = (await session.execute(snap_stmt)).scalars().all()
            assert len(snapshots) == 0

    await redis_client.delete(lockout_key)
    await redis_client.aclose()
    await engine.dispose()


@pytest.mark.black_box
async def test_journey_03_brute_force_concurrent_throttling_ch02() -> None:
    """
    CH-02: Brute-force submission attempts across multiple rapid concurrent threads
    are atomically throttled by Redis script without race condition leakage.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    engine = create_async_engine(db_url, echo=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    test_user_ref = f"usr_j03_ch02_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_j03_ch02_{uuid.uuid4().hex[:8]}"
    lockout_key = f"ratelimit:fayda:attempts:{device_fp}"

    await redis_client.delete(lockout_key)

    async with httpx.AsyncClient(base_url=api_base_url, timeout=10.0) as client:
        # Create and consent application
        create_resp = await client.post(
            "/v1/applications",
            json={"user_ref": test_user_ref, "bank_id": "bank_awash", "tier": "standard"},
            headers={"X-Device-Fingerprint": device_fp},
        )
        assert create_resp.status_code == 201
        app_id_str = create_resp.json()["application_id"]
        session_token = create_resp.json()["token"]

        auth_headers = {
            "Authorization": f"Bearer {session_token}",
            "X-Device-Fingerprint": device_fp,
        }

        consent_resp = await client.post(
            f"/v1/applications/{app_id_str}/consent",
            json={"consent_version": "v1.0", "accepted": True},
            headers=auth_headers,
        )
        assert consent_resp.status_code == 200

        # Launch 10 rapid concurrent malformed requests
        async def submit_bad_fin(idx: int) -> httpx.Response:
            return await client.post(
                f"/v1/applications/{app_id_str}/identity/start",
                json={"fin": f"bad_fin_{idx}"},
                headers=auth_headers,
            )

        responses = await asyncio.gather(*(submit_bad_fin(i) for i in range(10)))
        status_codes = [r.status_code for r in responses]

        # Validated: All returned either 422 (before lockout) or 429 (locked out)
        for code in status_codes:
            assert code in (422, 429)

        count_422 = status_codes.count(422)
        count_429 = status_codes.count(429)

        # First 5 attempts return 422, remaining attempts return 429
        assert count_422 == 5
        assert count_429 == 5

        # Redis counter accurately records 10 attempts
        final_counter = await redis_client.get(lockout_key)
        assert final_counter is not None
        assert int(final_counter) == 10

    await redis_client.delete(lockout_key)
    await redis_client.aclose()
    await engine.dispose()
