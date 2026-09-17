"""Persist presentation controls for the Studio Continue shelf.

Revision ID: 0014_continue_controls
Revises: 0013_m3_calibration_purpose
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_continue_controls"
down_revision: str | None = "0013_m3_calibration_purpose"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_progress_dismissal",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_key", sa.String(length=40), nullable=False),
        sa.Column("project_key", sa.String(length=80), nullable=False),
        sa.Column("group_key", sa.String(length=120), nullable=False),
        sa.Column("medium", sa.String(length=16), nullable=False),
        sa.Column(
            "hidden_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "medium IN ('READING', 'WATCHING')",
            name=op.f("ck_media_progress_dismissal_medium_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_progress_dismissal")),
        sa.UniqueConstraint(
            "profile_key",
            "project_key",
            "group_key",
            "medium",
            name=op.f(
                "uq_media_progress_dismissal_profile_key_project_key_group_key_medium"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_table("media_progress_dismissal")
