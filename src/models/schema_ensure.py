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
            """
            CREATE TABLE IF NOT EXISTS partner_banks (
                bank_id VARCHAR(64) PRIMARY KEY,
                bank_name VARCHAR(255) NOT NULL,
                short_code VARCHAR(32) NOT NULL,
                hq_city VARCHAR(128),
                supported_tiers JSONB NOT NULL DEFAULT '["standard"]'::jsonb,
                use_legacy_awash BOOLEAN NOT NULL DEFAULT FALSE,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_partner_banks_active ON partner_banks (active)",
            """
            CREATE TABLE IF NOT EXISTS platform_operators (
                id UUID PRIMARY KEY,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_platform_operators_email ON platform_operators (email)",
        ):
            await conn.execute(text(stmt))
