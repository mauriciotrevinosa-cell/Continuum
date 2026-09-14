"""M3: page-by-page manga production.

Revision ID: 0005_m3_manga
Revises: 0004_m2_closeout
Create Date: 2026-09-14

Creates ``materialized_chapter`` and ``production_profile`` (Tier C), and
``production_run``, ``production_page``, ``continuity_state`` and
``page_dependency`` (Tier D).

Extends the M2 rough tables additively:

* ``rough_artifact.production_run_id``, added to its unique key;
* ``rough_attempt`` gains ``production_page_id``, ``continuity_state_id``,
  ``profile_id`` and ``artwork_provenance``, plus the check
  ``artwork_is_reproducible``: an artwork candidate must record its backend,
  model, workflow and settings;
* derivative kinds gain COMPOSITION_MASTER, BW_FINISH and COLOR_FINISH;
* bundle roles gain GRAMMAR and ENVIRONMENT.

Existing M2 rows are untouched (their new columns are NULL or empty).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0005_m3_manga'
down_revision: str | None = '0004_m2_closeout'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DERIVATIVES_BEFORE = ('OUTPUT', 'MASK', 'SOURCE_CROP')
_DERIVATIVES_AFTER = (*_DERIVATIVES_BEFORE, 'COMPOSITION_MASTER', 'BW_FINISH', 'COLOR_FINISH')
_ROLES_BEFORE = ('CANON', 'STYLE', 'TECHNIQUE', 'MOOD', 'SOURCE_PLATE', 'CONTINUITY')
_ROLES_AFTER = (*_ROLES_BEFORE, 'GRAMMAR', 'ENVIRONMENT')
_OLD_UNIQUE = 'uq_rough_artifact_project_key_purpose_episode_page_panel_kind'
_NEW_UNIQUE = 'uq_rough_artifact_project_key_purpose_production_run_id_episode_page_panel_kind'
_UUID = sa.Uuid()
_JSON = postgresql.JSONB(astext_type=sa.Text())


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _created() -> sa.Column:
    return sa.Column(
        'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        'materialized_chapter',
        sa.Column('id', _UUID, nullable=False),
        sa.Column('project_key', sa.String(length=80), nullable=False),
        sa.Column('episode', sa.String(length=40), nullable=False),
        sa.Column('chapter', sa.Integer(), nullable=False),
        sa.Column('materializer_version', sa.String(length=60), nullable=False),
        sa.Column('body', _JSON, nullable=False),
        sa.Column('body_hash', sa.String(length=64), nullable=False),
        _created(),
        sa.CheckConstraint("body_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_materialized_chapter_body_hash_is_sha256')),
        sa.CheckConstraint('chapter >= 1', name=op.f('ck_materialized_chapter_chapter_positive')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_materialized_chapter')),
        sa.UniqueConstraint(
            'project_key', 'episode', 'chapter', 'body_hash',
            name=op.f('uq_materialized_chapter_project_key_episode_chapter_body_hash'),
        ),
    )
    op.create_table(
        'production_profile',
        sa.Column('id', _UUID, nullable=False),
        sa.Column('project_key', sa.String(length=80), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('body', _JSON, nullable=False),
        sa.Column('body_hash', sa.String(length=64), nullable=False),
        sa.Column('promoted_from_run', _UUID, nullable=True),
        sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=False),
        _created(),
        sa.CheckConstraint("status IN ('DRAFT', 'PROMOTED', 'RETIRED')", name=op.f('ck_production_profile_profile_status')),
        sa.CheckConstraint('version >= 1', name=op.f('ck_production_profile_version_positive')),
        sa.CheckConstraint("(status = 'PROMOTED') = (promoted_at IS NOT NULL)", name=op.f('ck_production_profile_promoted_iff_dated')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_production_profile')),
        sa.UniqueConstraint('project_key', 'name', 'version', name=op.f('uq_production_profile_project_key_name_version')),
    )
    op.create_table(
        'production_run',
        sa.Column('id', _UUID, nullable=False),
        sa.Column('project_key', sa.String(length=80), nullable=False),
        sa.Column('episode', sa.String(length=40), nullable=False),
        sa.Column('chapter', sa.Integer(), nullable=True),
        sa.Column('purpose', sa.String(length=32), nullable=False),
        sa.Column('profile_id', _UUID, nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('decision_notes', sa.Text(), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        _created(),
        sa.CheckConstraint(
            _in('purpose', ('PRODUCTION', 'WORKFLOW_TEST', 'NON_CANON_SAMPLE')),
            name=op.f('ck_production_run_rough_purpose'),
        ),
        sa.CheckConstraint("purpose IN ('PRODUCTION', 'NON_CANON_SAMPLE')", name=op.f('ck_production_run_run_purpose')),
        sa.CheckConstraint(
            "status IN ('OPEN', 'SAMPLE_PASSED', 'SAMPLE_FAILED', 'CLOSED')", name=op.f('ck_production_run_run_status')
        ),
        sa.CheckConstraint(
            "status NOT IN ('SAMPLE_PASSED', 'SAMPLE_FAILED') OR purpose = 'NON_CANON_SAMPLE'",
            name=op.f('ck_production_run_only_samples_pass_or_fail'),
        ),
        sa.ForeignKeyConstraint(['profile_id'], ['production_profile.id'], name=op.f('fk_production_run_profile_id_production_profile'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_production_run')),
    )
    op.create_index('ix_production_run_project_key', 'production_run', ['project_key'])
    op.create_table(
        'continuity_state',
        sa.Column('id', _UUID, nullable=False),
        sa.Column('run_id', _UUID, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('body', _JSON, nullable=False),
        sa.Column('body_hash', sa.String(length=64), nullable=False),
        sa.Column('reason', sa.String(length=300), nullable=False),
        _created(),
        sa.CheckConstraint('version >= 1', name=op.f('ck_continuity_state_version_positive')),
        sa.ForeignKeyConstraint(['run_id'], ['production_run.id'], name=op.f('fk_continuity_state_run_id_production_run'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_continuity_state')),
        sa.UniqueConstraint('run_id', 'version', name=op.f('uq_continuity_state_run_id_version')),
    )

    # -- the M2 rough tables join production -------------------------------------
    op.add_column('rough_artifact', sa.Column('production_run_id', _UUID, nullable=True))
    op.create_foreign_key(
        op.f('fk_rough_artifact_production_run_id_production_run'), 'rough_artifact',
        'production_run', ['production_run_id'], ['id'], ondelete='RESTRICT',
    )
    op.drop_constraint(op.f(_OLD_UNIQUE), 'rough_artifact', type_='unique')
    op.create_unique_constraint(
        op.f(_NEW_UNIQUE), 'rough_artifact',
        ['project_key', 'purpose', 'production_run_id', 'episode', 'page', 'panel', 'kind'],
        postgresql_nulls_not_distinct=True,
    )

    op.create_table(
        'production_page',
        sa.Column('id', _UUID, nullable=False),
        sa.Column('run_id', _UUID, nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('materialized_chapter_id', _UUID, nullable=False),
        sa.Column('page_key', sa.String(length=80), nullable=False),
        sa.Column('page_hash', sa.String(length=64), nullable=False),
        sa.Column('artifact_id', _UUID, nullable=False),
        sa.Column('state', sa.String(length=20), nullable=False),
        sa.Column('reasons', _JSON, nullable=False),
        sa.Column('approved_attempt_id', _UUID, nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('sequence >= 1', name=op.f('ck_production_page_sequence_positive')),
        sa.CheckConstraint(
            "state IN ('WAITING', 'BLOCKED', 'READY', 'IN_REVIEW', 'APPROVED', 'STALE')",
            name=op.f('ck_production_page_page_state'),
        ),
        sa.CheckConstraint(
            "state <> 'APPROVED' OR approved_attempt_id IS NOT NULL",
            name=op.f('ck_production_page_approved_has_attempt'),
        ),
        sa.ForeignKeyConstraint(['run_id'], ['production_run.id'], name=op.f('fk_production_page_run_id_production_run'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['materialized_chapter_id'], ['materialized_chapter.id'], name=op.f('fk_production_page_materialized_chapter_id_materialized_chapter'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['artifact_id'], ['rough_artifact.id'], name=op.f('fk_production_page_artifact_id_rough_artifact'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['approved_attempt_id'], ['rough_attempt.id'], name=op.f('fk_production_page_approved_attempt_id_rough_attempt'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_production_page')),
        sa.UniqueConstraint('run_id', 'sequence', name=op.f('uq_production_page_run_id_sequence')),
        sa.UniqueConstraint('artifact_id', name=op.f('uq_production_page_artifact_id')),
    )
    op.create_table(
        'page_dependency',
        sa.Column('id', _UUID, nullable=False),
        sa.Column('page_id', _UUID, nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('key', sa.String(length=200), nullable=False),
        sa.Column('version_hash', sa.String(length=64), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['page_id'], ['production_page.id'], name=op.f('fk_page_dependency_page_id_production_page'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_page_dependency')),
        sa.UniqueConstraint('page_id', 'kind', 'key', name=op.f('uq_page_dependency_page_id_kind_key')),
    )

    op.add_column('rough_attempt', sa.Column('production_page_id', _UUID, nullable=True))
    op.add_column('rough_attempt', sa.Column('continuity_state_id', _UUID, nullable=True))
    op.add_column('rough_attempt', sa.Column('profile_id', _UUID, nullable=True))
    op.add_column('rough_attempt', sa.Column('artwork_provenance', _JSON, server_default='{}', nullable=False))
    op.create_foreign_key(
        op.f('fk_rough_attempt_production_page_id_production_page'), 'rough_attempt',
        'production_page', ['production_page_id'], ['id'], ondelete='RESTRICT',
    )
    op.create_foreign_key(
        op.f('fk_rough_attempt_continuity_state_id_continuity_state'), 'rough_attempt',
        'continuity_state', ['continuity_state_id'], ['id'], ondelete='RESTRICT',
    )
    op.create_foreign_key(
        op.f('fk_rough_attempt_profile_id_production_profile'), 'rough_attempt',
        'production_profile', ['profile_id'], ['id'], ondelete='RESTRICT',
    )
    op.create_check_constraint(
        op.f('ck_rough_attempt_artwork_is_reproducible'), 'rough_attempt',
        "output_class IS DISTINCT FROM 'ARTWORK_CANDIDATE' OR (artwork_provenance ? 'model'"
        " AND artwork_provenance ? 'workflow' AND artwork_provenance ? 'settings'"
        " AND artwork_provenance ? 'backend')",
    )

    op.drop_constraint(op.f('ck_attempt_derivative_derivative_kind'), 'attempt_derivative', type_='check')
    op.create_check_constraint(
        op.f('ck_attempt_derivative_derivative_kind'), 'attempt_derivative', _in('kind', _DERIVATIVES_AFTER)
    )
    op.drop_constraint(op.f('ck_attempt_input_bundle_role'), 'attempt_input', type_='check')
    op.create_check_constraint(op.f('ck_attempt_input_bundle_role'), 'attempt_input', _in('role', _ROLES_AFTER))


def downgrade() -> None:
    bind = op.get_bind()
    used = bind.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM production_run)"
            " + (SELECT count(*) FROM attempt_derivative WHERE kind IN"
            "    ('COMPOSITION_MASTER', 'BW_FINISH', 'COLOR_FINISH'))"
            " + (SELECT count(*) FROM attempt_input WHERE role IN ('GRAMMAR', 'ENVIRONMENT'))"
        )
    ).scalar_one()
    if used:
        raise RuntimeError(f"{used} M3 production rows exist, which revision 0004 cannot represent.")
    op.drop_constraint(op.f('ck_attempt_input_bundle_role'), 'attempt_input', type_='check')
    op.create_check_constraint(op.f('ck_attempt_input_bundle_role'), 'attempt_input', _in('role', _ROLES_BEFORE))
    op.drop_constraint(op.f('ck_attempt_derivative_derivative_kind'), 'attempt_derivative', type_='check')
    op.create_check_constraint(
        op.f('ck_attempt_derivative_derivative_kind'), 'attempt_derivative', _in('kind', _DERIVATIVES_BEFORE)
    )
    op.drop_constraint(op.f('ck_rough_attempt_artwork_is_reproducible'), 'rough_attempt', type_='check')
    for name in (
        'fk_rough_attempt_profile_id_production_profile',
        'fk_rough_attempt_continuity_state_id_continuity_state',
        'fk_rough_attempt_production_page_id_production_page',
    ):
        op.drop_constraint(op.f(name), 'rough_attempt', type_='foreignkey')
    for column in ('artwork_provenance', 'profile_id', 'continuity_state_id', 'production_page_id'):
        op.drop_column('rough_attempt', column)
    op.drop_table('page_dependency')
    op.drop_table('production_page')
    op.drop_constraint(op.f(_NEW_UNIQUE), 'rough_artifact', type_='unique')
    op.create_unique_constraint(
        op.f(_OLD_UNIQUE), 'rough_artifact',
        ['project_key', 'purpose', 'episode', 'page', 'panel', 'kind'],
        postgresql_nulls_not_distinct=True,
    )
    op.drop_constraint(op.f('fk_rough_artifact_production_run_id_production_run'), 'rough_artifact', type_='foreignkey')
    op.drop_column('rough_artifact', 'production_run_id')
    op.drop_table('continuity_state')
    op.drop_index('ix_production_run_project_key', table_name='production_run')
    op.drop_table('production_run')
    op.drop_table('production_profile')
    op.drop_table('materialized_chapter')
