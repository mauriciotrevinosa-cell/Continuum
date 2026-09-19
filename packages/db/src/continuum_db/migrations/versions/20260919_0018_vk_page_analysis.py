"""M3 Visual Knowledge: persisted page analysis per analyzer version.

Revision ID: 0018_vk_page_analysis
Revises: 0017_layered_panel_stages
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_vk_page_analysis"
down_revision: str | None = "0017_layered_panel_stages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "page_analysis",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("analyzer_id", sa.String(length=80), nullable=False),
        sa.Column("analyzer_version", sa.String(length=40), nullable=False),
        sa.Column("model_sha256", sa.String(length=64), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "subject ~ '^(unit:[0-9a-f]{16,64}:[0-9]{1,6}|sha256:[0-9a-f]{64})$'",
            name=op.f("ck_page_analysis_subject_format"),
        ),
        sa.CheckConstraint(
            "content_sha256 IS NULL OR content_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_page_analysis_content_sha256_format"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_page_analysis")),
        sa.UniqueConstraint(
            "subject",
            "analyzer_id",
            "analyzer_version",
            name=op.f("uq_page_analysis_subject_analyzer_id_analyzer_version"),
        ),
    )


def downgrade() -> None:
    # Derived data: dropping it loses nothing that cannot be recomputed.
    op.drop_table("page_analysis")
