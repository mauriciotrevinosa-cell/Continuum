"""M3 W6 follow-up: stage-scoped garment condition on outfit_wear.

Revision ID: 0011_m3_wardrobe_condition
Revises: 0010_m3_wardrobe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_m3_wardrobe_condition"
down_revision: str | None = "0010_m3_wardrobe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A garment's condition is stage-scoped on the wear assignment, so
    # clean -> dirty -> damaged -> repaired can be represented without
    # rewriting the garment's identity or earlier continuity. Backfill
    # existing rows with '' (the model's Python-side default), then drop the
    # server default so the final schema matches the ORM exactly.
    op.add_column(
        "outfit_wear",
        sa.Column("condition", sa.String(120), nullable=False, server_default=""),
    )
    op.alter_column("outfit_wear", "condition", server_default=None)


def downgrade() -> None:
    op.drop_column("outfit_wear", "condition")