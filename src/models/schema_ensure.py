"""Ensure Postgres enum values and additive columns exist (idempotent)."""
from __future__ import annotations

from sqlalchemy import text

from src.models.base import engine


async def ensure_schema_extensions() -> None:
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        for value in ("AWAITING_BANK_OUTBOUND", "CBS_PENDING_BANK_RELEASE"):
            await conn.execute(
                text(f"ALTER TYPE application_status_enum ADD VALUE IF NOT EXISTS '{value}'")
            )
        for stmt in (
            "ALTER TABLE applications ADD COLUMN IF NOT EXISTS fayda_ref_hash VARCHAR(128)",
            "ALTER TABLE applications ADD COLUMN IF NOT EXISTS bank_edited_fields JSONB",
            "CREATE INDEX IF NOT EXISTS ix_applications_fayda_ref_hash ON applications (fayda_ref_hash)",
        ):
            await conn.execute(text(stmt))
