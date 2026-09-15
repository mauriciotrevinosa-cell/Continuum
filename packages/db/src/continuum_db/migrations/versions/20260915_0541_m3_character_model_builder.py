"""M3 W4: provider-backed character model-sheet attempts.

Revision ID: 0009_m3_model_builder
Revises: 0008_m3_models
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_m3_model_builder"
down_revision: str | None = "0008_m3_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE character_production_evidence "
        "RENAME CONSTRAINT ck_character_production_evidence_production_evidence_po_5084 "
        "TO ck_character_production_evidence_evidence_position_non_negative"
    )
    op.create_table(
        "character_model_sheet_attempt",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("project_key", sa.String(80), nullable=False),
        sa.Column("sheet_kind", sa.String(16), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("parent_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("views", postgresql.JSONB(), nullable=False),
        sa.Column("reference_pack", postgresql.JSONB(), nullable=False),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("mime", sa.String(40), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.String(200), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["model_id"], ["character_production_model.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["character_id"], ["character_profile.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["parent_attempt_id"], ["character_model_sheet_attempt.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reference_id"], ["reference_item.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "sheet_kind", "attempt"),
        sa.CheckConstraint(
            "sheet_kind IN ('HEAD', 'FULL_BODY')",
            name=op.f("ck_character_model_sheet_attempt_model_sheet_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'GENERATED', 'APPROVED', 'REJECTED', 'SUPERSEDED')",
            name=op.f("ck_character_model_sheet_attempt_model_sheet_status"),
        ),
        sa.CheckConstraint(
            "attempt > 0",
            name=op.f("ck_character_model_sheet_attempt_model_sheet_attempt_positive"),
        ),
        sa.CheckConstraint(
            "content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_character_model_sheet_attempt_model_sheet_hash"),
        ),
        sa.CheckConstraint(
            "(status = 'QUEUED') = (content_hash IS NULL)",
            name=op.f("ck_character_model_sheet_attempt_sheet_output_iff_rendered"),
        ),
        sa.CheckConstraint(
            "(status IN ('APPROVED', 'REJECTED', 'SUPERSEDED')) = "
            "(reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)",
            name=op.f("ck_character_model_sheet_attempt_sheet_terminal_has_human"),
        ),
    )
    op.create_index(
        "ix_character_model_sheet_model",
        "character_model_sheet_attempt",
        ["model_id", "sheet_kind", "attempt"],
    )
    op.create_index(
        "uq_character_model_sheet_approved",
        "character_model_sheet_attempt",
        ["project_key", "character_id", "sheet_kind"],
        unique=True,
        postgresql_where=sa.text("status = 'APPROVED'"),
    )


def downgrade() -> None:
    op.drop_table("character_model_sheet_attempt")
    op.execute(
        "ALTER TABLE character_production_evidence "
        "RENAME CONSTRAINT ck_character_production_evidence_evidence_position_non_negative "
        "TO ck_character_production_evidence_production_evidence_po_5084"
    )
