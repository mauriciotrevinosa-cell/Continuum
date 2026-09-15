"""M3 W6: timeline-aware wardrobe (outfit review + owner/wearer separation).

Revision ID: 0010_m3_wardrobe
Revises: 0009_m3_model_builder
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_m3_wardrobe"
down_revision: str | None = "0009_m3_model_builder"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "character_outfit",
        sa.Column("review_status", sa.String(12), nullable=True),
    )
    op.add_column(
        "character_outfit",
        sa.Column("reviewed_by", sa.String(200), nullable=True),
    )
    op.add_column(
        "character_outfit",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "character_outfit",
        sa.Column("model_sheet_reference_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_character_outfit_model_sheet_reference_id_reference_item",
        "character_outfit",
        "reference_item",
        ["model_sheet_reference_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "only_project_outfits_are_reviewed",
        "character_outfit",
        "(kind = 'PROJECT') OR (review_status IS NULL)",
    )
    op.create_check_constraint(
        "outfit_review_status",
        "character_outfit",
        "review_status IS NULL OR review_status IN ('DRAFT', 'REVIEW', 'APPROVED', 'REJECTED')",
    )
    op.create_check_constraint(
        "approved_outfit_has_human",
        "character_outfit",
        "review_status <> 'APPROVED' OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)",
    )

    op.create_table(
        "outfit_wear",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("outfit_id", sa.Uuid(), nullable=False),
        sa.Column("wearer_character_id", sa.Uuid(), nullable=False),
        sa.Column("project_key", sa.String(80), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("context", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["outfit_id"], ["character_outfit.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["wearer_character_id"], ["character_profile.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("outfit_id", "project_key", "stage"),
        sa.CheckConstraint("stage <> ''", name=op.f("ck_outfit_wear_outfit_wear_stage_non_empty")),
    )
    op.create_index(
        "ix_outfit_wear_wearer_stage",
        "outfit_wear",
        ["wearer_character_id", "project_key", "stage"],
    )


def downgrade() -> None:
    op.drop_index("ix_outfit_wear_wearer_stage", table_name="outfit_wear")
    op.drop_table("outfit_wear")
    op.drop_constraint("approved_outfit_has_human", "character_outfit", type_="check")
    op.drop_constraint("outfit_review_status", "character_outfit", type_="check")
    op.drop_constraint("only_project_outfits_are_reviewed", "character_outfit", type_="check")
    op.drop_constraint(
        "fk_character_outfit_model_sheet_reference_id_reference_item",
        "character_outfit",
        type_="foreignkey",
    )
    op.drop_column("character_outfit", "model_sheet_reference_id")
    op.drop_column("character_outfit", "reviewed_at")
    op.drop_column("character_outfit", "reviewed_by")
    op.drop_column("character_outfit", "review_status")