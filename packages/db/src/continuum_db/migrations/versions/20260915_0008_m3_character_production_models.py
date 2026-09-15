"""M3 W1: versioned character production models.

Revision ID: 0008_m3_models
Revises: 0007_m3_preview
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_m3_models"
down_revision: str | None = "0007_m3_preview"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "character_production_model",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_key", sa.String(80), nullable=False),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("identity_rules", postgresql.JSONB(), nullable=False),
        sa.Column("restrictions", postgresql.JSONB(), nullable=False),
        sa.Column("active_outfit_id", sa.Uuid(), nullable=True),
        sa.Column("head_sheet_reference_id", sa.Uuid(), nullable=True),
        sa.Column("body_sheet_reference_id", sa.Uuid(), nullable=True),
        sa.Column("created_from", postgresql.JSONB(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(200), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["character_id"], ["character_profile.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["active_outfit_id"], ["character_outfit.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["head_sheet_reference_id"], ["reference_item.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["body_sheet_reference_id"], ["reference_item.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_key", "character_id", "version"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'REVIEW', 'APPROVED', 'SUPERSEDED')",
            name=op.f("ck_character_production_model_production_model_status"),
        ),
        sa.CheckConstraint(
            "version > 0",
            name=op.f("ck_character_production_model_production_model_version_positive"),
        ),
        sa.CheckConstraint(
            "(status = 'APPROVED') = (approved_at IS NOT NULL AND approved_by IS NOT NULL)",
            name=op.f("ck_character_production_model_approved_model_has_human"),
        ),
    )
    op.create_index(
        "ix_character_production_model_active",
        "character_production_model",
        ["project_key", "character_id", "status"],
    )
    op.create_index(
        "uq_character_production_model_approved",
        "character_production_model",
        ["project_key", "character_id"],
        unique=True,
        postgresql_where=sa.text("status = 'APPROVED'"),
    )
    op.create_table(
        "character_production_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("preferred", sa.Boolean(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["character_production_model.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"], ["character_observation.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_id", "observation_id", "role"),
        sa.CheckConstraint(
            "role IN ('IDENTITY', 'BODY', 'WARDROBE', 'EXPRESSION', 'POSE', 'ACCESSORY', 'SCALE')",
            name=op.f("ck_character_production_evidence_production_evidence_role"),
        ),
        sa.CheckConstraint(
            "position >= 0",
            name=op.f("ck_character_production_evidence_production_evidence_position_non_negative"),
        ),
    )
    op.create_index(
        "ix_character_production_evidence_model",
        "character_production_evidence",
        ["model_id", "position"],
    )


def downgrade() -> None:
    op.drop_table("character_production_evidence")
    op.drop_table("character_production_model")
