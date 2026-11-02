import asyncio
import os
import uuid
from typing import Any, Dict

import httpx
import pytest
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.models.application import Application, ApplicationStatus, BankSubmission

pytestmark = [pytest.mark.asyncio, pytest.mark.black_box]


@pytest.mark.black_box
async def test_journey_06_dynamic_fields_validation_e2e() -> None:
    """
    End-to-end user journey test for dynamic partner bank field schema validation (J-06).

    Covers architectural requirements AS-06:
    - Real PostgreSQL connection via DATABASE_URL and asyncpg (no mocks).
    - Real Redis queue connection via REDIS_URL (no mocks).
    - Validation against partner bank's JSONSchema specification (Awash Bank Finacle).
    - HTTP 400 Problem Details with exact field-level validation errors.
    - Application status strictly held at LIVENESS_PASSED without advancing to DATA_COMPLETE.
    - Zero rows created in bank_submissions table.
    - Zero messages dispatched to bank_submission_queue.

    Assertion Points Verified:
    - AP-1 API response: PUT /v1/applications/{id}/details returns HTTP 400 Bad Request with field-level validation errors.
    - AP-2 Database: applications status remains LIVENESS_PASSED; does not advance to DATA_COMPLETE.
    - AP-3 Database: bank_submissions has 0 rows for this application ID.
    - AP-4 Queue: Zero messages are enqueued onto bank_submission_queue.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = aioredis.from_url(redis_url, decode_responses=True)

    test_user_ref = f"usr_j06_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_j06_{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Fingerprint": device_fp}

    async with httpx.AsyncClient(base_url=api_base_url, timeout=10.0) as client:
        # Step 1: Create application
        create_resp = await client.post(
            "/v1/applications",
            json={"user_ref": test_user_ref, "bank_id": "bank_awash", "tier": "standard"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        app_id_str = create_resp.json()["application_id"]
        app_uuid = uuid.UUID(app_id_str)
        session_token = create_resp.json()["token"]

        auth_headers = {
            "Authorization": f"Bearer {session_token}",
            "X-Device-Fingerprint": device_fp,
        }

        # Step 2: Consent
        consent_resp = await client.post(
            f"/v1/applications/{app_id_str}/consent",
            json={"consent_version": "v1.0", "accepted": True},
            headers=auth_headers,
        )
        assert consent_resp.status_code == 200

        # Step 3: Advance state to LIVENESS_PASSED directly in PostgreSQL
        async with session_maker() as session:
            stmt = select(Application).where(Application.id == app_uuid)
            app_obj = (await session.execute(stmt)).scalar_one()
            app_obj.status = ApplicationStatus.LIVENESS_PASSED
            await session.commit()

        # Record initial queue depth
        initial_queue_len = await redis_client.xlen("bank_submission_queue")

        # Step 4: Submit invalid dynamic fields
        # Awash Bank requires monthly_income_etb (number >= 0), occupation (string minLength 2), source_of_funds (enum)
        # We provide:
        # - monthly_income_etb: string instead of number
        # - occupation: single char (too short)
        # - source_of_funds: omitted completely
        invalid_dynamic_fields = {
            "monthly_income_etb": "fifty_thousand_birr",
            "occupation": "A",
        }

        # -------------------------------------------------------------------------
        # AP-1 API response: PUT /v1/applications/{id}/details returns HTTP 400 Bad Request with field-level validation errors
        # -------------------------------------------------------------------------
        details_resp = await client.put(
            f"/v1/applications/{app_id_str}/details",
            json={"dynamic_fields": invalid_dynamic_fields},
            headers=auth_headers,
        )
        assert details_resp.status_code == 400
        error_data = details_resp.json()
        assert error_data.get("status") == 400
        assert "INVALID_DYNAMIC_FIELDS" in error_data.get("type", "")
        assert "field_errors" in error_data
        field_errors = error_data["field_errors"]
        assert isinstance(field_errors, dict)
        assert "source_of_funds" in field_errors
        assert "Field is required" in field_errors["source_of_funds"]

        # -------------------------------------------------------------------------
        # AP-2 Database: applications status remains LIVENESS_PASSED; does not advance to DATA_COMPLETE
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            stmt = select(Application).where(Application.id == app_uuid)
            app_rec = (await session.execute(stmt)).scalar_one_or_none()
            assert app_rec is not None
            assert app_rec.status == ApplicationStatus.LIVENESS_PASSED
            assert app_rec.status != ApplicationStatus.DATA_COMPLETE
            assert app_rec.status.value == "LIVENESS_PASSED"

        # -------------------------------------------------------------------------
        # AP-3 Database: bank_submissions has 0 rows for this application ID
        # -------------------------------------------------------------------------
        async with session_maker() as session:
            sub_stmt = select(BankSubmission).where(BankSubmission.application_id == app_uuid)
            submissions = list((await session.execute(sub_stmt)).scalars().all())
            assert len(submissions) == 0

        # -------------------------------------------------------------------------
        # AP-4 Queue: Zero messages are enqueued onto bank_submission_queue
        # -------------------------------------------------------------------------
        current_queue_len = await redis_client.xlen("bank_submission_queue")
        assert current_queue_len == initial_queue_len

    await redis_client.aclose()
    await engine.dispose()


@pytest.mark.black_box
async def test_journey_06_ch03_dynamic_schema_modification_in_flight() -> None:
    """
    CH-03: Modifying bank JSONSchema definition dynamically while an application is in flight
    safely triggers re-validation against the updated schema version.
    """
    api_base_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8005")
    db_url = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/ekyc_db")

    engine = create_async_engine(db_url, echo=False)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    test_user_ref = f"usr_j06_ch03_{uuid.uuid4().hex[:8]}"
    device_fp = f"dev_fp_j06_ch03_{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Fingerprint": device_fp}

    async with httpx.AsyncClient(base_url=api_base_url, timeout=10.0) as client:
        # Step 1: Create and consent application
        create_resp = await client.post(
            "/v1/applications",
            json={"user_ref": test_user_ref, "bank_id": "bank_awash", "tier": "standard"},
            headers=headers,
        )
        assert create_resp.status_code == 201
        app_id_str = create_resp.json()["application_id"]
        app_uuid = uuid.UUID(app_id_str)
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

        # Step 2: Set status to LIVENESS_PASSED
        async with session_maker() as session:
            stmt = select(Application).where(Application.id == app_uuid)
            app_obj = (await session.execute(stmt)).scalar_one()
            app_obj.status = ApplicationStatus.LIVENESS_PASSED
            await session.commit()

        # Step 3: Fetch active original schema for Awash Bank
        bank_meta_resp = await client.get("/v1/banks/bank_awash")
        assert bank_meta_resp.status_code == 200
        original_schema = bank_meta_resp.json()["dynamic_schema"]

        # Step 4: Dynamically update bank schema while application is in flight
        # Add required field 'tax_identification_number'
        updated_schema = dict(original_schema)
        updated_schema["required"] = list(original_schema.get("required", [])) + ["tax_identification_number"]
        updated_schema["properties"] = dict(original_schema.get("properties", {}))
        updated_schema["properties"]["tax_identification_number"] = {
            "type": "string",
            "minLength": 8,
            "description": "Ethiopian Ministry of Revenues Taxpayer Identification Number.",
        }

        update_resp = await client.put(
            "/v1/banks/bank_awash/schema",
            json={"dynamic_schema": updated_schema},
        )
        assert update_resp.status_code == 200
        assert "tax_identification_number" in update_resp.json()["dynamic_schema"]["required"]

        try:
            # Step 5: Applicant submits payload matching OLD schema (missing tax_identification_number)
            old_schema_fields = {
                "monthly_income_etb": 35000.0,
                "occupation": "Accountant",
                "source_of_funds": "Salary",
            }
            rejected_resp = await client.put(
                f"/v1/applications/{app_id_str}/details",
                json={"dynamic_fields": old_schema_fields},
                headers=auth_headers,
            )
            # Must safely trigger re-validation against the updated schema version
            assert rejected_resp.status_code == 400
            err_json = rejected_resp.json()
            assert "tax_identification_number" in err_json.get("field_errors", {})

            # Step 6: Applicant provides the newly required field
            new_schema_fields = {
                "monthly_income_etb": 35000.0,
                "occupation": "Accountant",
                "source_of_funds": "Salary",
                "tax_identification_number": "TIN-ET-12345678",
            }
            accepted_resp = await client.put(
                f"/v1/applications/{app_id_str}/details",
                json={"dynamic_fields": new_schema_fields},
                headers=auth_headers,
            )
            assert accepted_resp.status_code == 200
            assert accepted_resp.json()["status"] == "DATA_COMPLETE"

            # Verify database advanced to DATA_COMPLETE
            async with session_maker() as session:
                stmt = select(Application).where(Application.id == app_uuid)
                app_db = (await session.execute(stmt)).scalar_one()
                assert app_db.status == ApplicationStatus.DATA_COMPLETE

        finally:
            # Step 7: Restore original Awash Bank schema
            restore_resp = await client.put(
                "/v1/banks/bank_awash/schema",
                json={"dynamic_schema": original_schema},
            )
            assert restore_resp.status_code == 200

    await engine.dispose()
