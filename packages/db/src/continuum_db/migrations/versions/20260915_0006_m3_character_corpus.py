"""M3: the character reference corpus.

Revision ID: 0006_m3_corpus
Revises: 0005_m3_manga
Create Date: 2026-09-15

Creates ``character_observation`` (Tier B): observations of a character -
curated references, source manga pages, labelled fan art, approved project
pages - with what each teaches, its authority, whether a person confirmed it,
and how it was found. Additive; no existing row changes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0006_m3_corpus'
down_revision: str | None = '0005_m3_manga'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = sa.Uuid()
_JSON = postgresql.JSONB(astext_type=sa.Text())


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)


def upgrade() -> None:
    op.create_table(
        'character_observation',
        sa.Column('id', _UUID, nullable=False),
        sa.Column('character_id', _UUID, nullable=False),
        sa.Column('locator', sa.String(length=200), nullable=False),
        sa.Column('source_kind', sa.String(length=20), nullable=False),
        sa.Column('reference_id', _UUID, nullable=True),
        sa.Column('unit_key', sa.String(length=64), nullable=True),
        sa.Column('page_offset', sa.Integer(), nullable=True),
        sa.Column('series_key', sa.String(length=120), nullable=True),
        sa.Column('source_label', sa.String(length=300), nullable=False),
        sa.Column('authority', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('role', sa.String(length=12), nullable=False),
        sa.Column('anchor', sa.Boolean(), nullable=False),
        sa.Column('atypical', sa.Boolean(), nullable=False),
        sa.Column('facets', _JSON, nullable=False),
        sa.Column('angle', sa.String(length=24), nullable=True),
        sa.Column('framing', sa.String(length=12), nullable=True),
        sa.Column('expression', sa.String(length=80), nullable=False),
        sa.Column('pose', sa.String(length=80), nullable=False),
        sa.Column('evidence', _JSON, nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        _now('created_at'),
        _now('updated_at'),
        sa.CheckConstraint(
            "source_kind IN ('CURATED', 'SOURCE_PAGE', 'FAN_ART', 'APPROVED_OUTPUT')",
            name=op.f('ck_character_observation_observation_source'),
        ),
        sa.CheckConstraint(
            "authority IN ('PRIMARY_SOURCE', 'CREATOR_PRIMARY', 'OFFICIAL', 'PROJECT_CREATED',"
            " 'SUPPLEMENTAL', 'UNSORTED')",
            name=op.f('ck_character_observation_observation_authority'),
        ),
        sa.CheckConstraint(
            "status IN ('CANDIDATE', 'CONFIRMED', 'REJECTED')",
            name=op.f('ck_character_observation_observation_status'),
        ),
        sa.CheckConstraint(
            "role IN ('GROUNDING', 'STYLIZATION', 'EVIDENCE')",
            name=op.f('ck_character_observation_observation_role'),
        ),
        sa.CheckConstraint(
            "angle IS NULL OR angle IN ('FRONT', 'THREE_QUARTER_LEFT', 'THREE_QUARTER_RIGHT',"
            " 'PROFILE', 'BACK', 'LOOKING_UP', 'LOOKING_DOWN')",
            name=op.f('ck_character_observation_observation_angle'),
        ),
        sa.CheckConstraint(
            "framing IS NULL OR framing IN ('CLOSE_UP', 'UPPER_BODY', 'FULL_BODY', 'WIDE')",
            name=op.f('ck_character_observation_observation_framing'),
        ),
        sa.CheckConstraint(
            "(source_kind = 'SOURCE_PAGE') = (unit_key IS NOT NULL AND page_offset IS NOT NULL)",
            name=op.f('ck_character_observation_source_page_has_unit'),
        ),
        sa.CheckConstraint(
            "source_kind = 'SOURCE_PAGE' OR reference_id IS NOT NULL",
            name=op.f('ck_character_observation_reference_observation_has_reference'),
        ),
        sa.CheckConstraint(
            "status <> 'CANDIDATE' OR NOT anchor",
            name=op.f('ck_character_observation_candidates_are_never_anchors'),
        ),
        sa.ForeignKeyConstraint(
            ['character_id'], ['character_profile.id'],
            name=op.f('fk_character_observation_character_id_character_profile'), ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['reference_id'], ['reference_item.id'],
            name=op.f('fk_character_observation_reference_id_reference_item'), ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_character_observation')),
        sa.UniqueConstraint(
            'character_id', 'locator', name=op.f('uq_character_observation_character_id_locator')
        ),
    )
    op.create_index('ix_character_observation_locator', 'character_observation', ['locator'])


def downgrade() -> None:
    op.drop_index('ix_character_observation_locator', table_name='character_observation')
    op.drop_table('character_observation')
