"""M3: chapter technical previews, cast overrides, visual origin.

Revision ID: 0007_m3_preview
Revises: 0006_m3_corpus
Create Date: 2026-09-15

* ``production_run.purpose`` also allows WORKFLOW_TEST: a chapter technical
  preview that renders test pages without approval, continuity or canon;
* ``production_page.cast_override``: a person's correction of the cast derived
  from the script;
* ``reference_item.visual_origin``: who made the image, judged by a person,
  kept apart from where it was acquired.

Additive; no existing row changes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0007_m3_preview'
down_revision: str | None = '0006_m3_corpus'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VISUAL = "('PRIMARY_MANGA', 'OFFICIAL_ANIME', 'OFFICIAL_ART', 'PROJECT_CREATED', 'FAN_ART', 'UNKNOWN')"


def upgrade() -> None:
    op.drop_constraint(op.f('ck_production_run_run_purpose'), 'production_run', type_='check')
    op.create_check_constraint(
        op.f('ck_production_run_run_purpose'), 'production_run',
        "purpose IN ('PRODUCTION', 'NON_CANON_SAMPLE', 'WORKFLOW_TEST')",
    )
    op.add_column(
        'production_page',
        sa.Column(
            'cast_override', postgresql.JSONB(astext_type=sa.Text()),
            server_default='{}', nullable=False,
        ),
    )
    op.add_column('reference_item', sa.Column('visual_origin', sa.String(length=20), nullable=True))
    op.create_check_constraint(
        op.f('ck_reference_item_visual_origin_known'), 'reference_item',
        f"visual_origin IS NULL OR visual_origin IN {_VISUAL}",
    )


def downgrade() -> None:
    bind = op.get_bind()
    used = bind.execute(
        sa.text("SELECT count(*) FROM production_run WHERE purpose = 'WORKFLOW_TEST'")
    ).scalar_one()
    if used:
        raise RuntimeError(f"{used} chapter preview runs exist, which revision 0006 cannot represent.")
    op.drop_constraint(op.f('ck_reference_item_visual_origin_known'), 'reference_item', type_='check')
    op.drop_column('reference_item', 'visual_origin')
    op.drop_column('production_page', 'cast_override')
    op.drop_constraint(op.f('ck_production_run_run_purpose'), 'production_run', type_='check')
    op.create_check_constraint(
        op.f('ck_production_run_run_purpose'), 'production_run',
        "purpose IN ('PRODUCTION', 'NON_CANON_SAMPLE')",
    )
