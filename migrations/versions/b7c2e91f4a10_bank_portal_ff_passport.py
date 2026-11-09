"""bank portal settings, staff, passport, FF statuses

Revision ID: b7c2e91f4a10
Revises: 13a9a8165587
Create Date: 2026-11-09

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b7c2e91f4a10"
down_revision: Union[str, Sequence[str], None] = "13a9a8165587"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: create any missing ORM tables / enum values via metadata.
    from src.models import Base  # noqa: WPS433

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    # Ensure new application status enum members exist on PostgreSQL.
    for value in ("AWAITING_BANK_OUTBOUND", "CBS_PENDING_BANK_RELEASE"):
        op.execute(f"ALTER TYPE application_status_enum ADD VALUE IF NOT EXISTS '{value}'")
    op.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS fayda_ref_hash VARCHAR(128)")
    op.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS bank_edited_fields JSONB")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_applications_fayda_ref_hash ON applications (fayda_ref_hash)"
    )


def downgrade() -> None:
    # Non-destructive downgrade: leave columns/tables (status enums cannot drop values easily).
    pass
