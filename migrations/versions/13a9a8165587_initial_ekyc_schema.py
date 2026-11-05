"""initial_ekyc_schema

Revision ID: 13a9a8165587
Revises:
Create Date: 2026-11-03 01:13:51.920542

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "13a9a8165587"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create all ORM tables (idempotent for already-bootstrapped environments).
    from src.models import Base  # noqa: WPS433 — alembic runtime import

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from src.models import Base  # noqa: WPS433

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
