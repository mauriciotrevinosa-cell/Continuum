"""Phase 1.5: full-Vault catalog (Tiers A-B), progress and project inputs (Tier C).

Revision ID: 0003_phase15
Revises: 0002_phase1
Create Date: 2026-09-14

Creates the catalog (``catalog_scan``, ``catalog_entry``, ``catalog_member``,
``catalog_unit``), reading and watching progress (``media_progress``) and the
project production inputs (``reference_manifest``, ``chapter_package``,
``music_reference``). ``continuum_db.tiers`` declares each table's tier.

Alters two Phase 1 tables, additively:

* references and inbox candidates gain ``collection``, ``source_posted_at``,
  ``rights_status`` (default ``UNKNOWN``) and ``training_eligibility``
  (default ``MANUAL_REVIEW``) - existing rows receive those defaults, so
  nothing becomes approved for training by migrating;
* the reference class vocabulary gains ``UNSORTED`` for imported material
  whose purpose no person has decided yet.

No column stores source bytes or a path as identity.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0003_phase15'
down_revision: str | None = '0002_phase1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CLASSES_BEFORE = ('CANON', 'TECHNIQUE', 'CONTINUITY', 'MOOD')
_CLASSES_AFTER = (*_CLASSES_BEFORE, 'UNSORTED')
_RIGHTS = ('UNKNOWN', 'OWNED', 'LICENSED', 'PERMITTED', 'RESTRICTED')
_TRAINING = ('MANUAL_REVIEW', 'APPROVED', 'EXCLUDED')


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table('chapter_package',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_key', sa.String(length=80), nullable=False),
    sa.Column('package_key', sa.String(length=120), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('schema_version', sa.String(length=40), nullable=False),
    sa.Column('approval_state', sa.Enum('DRAFT', 'IN_REVIEW', 'APPROVED', 'SUPERSEDED', name='approval_state', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('body', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('body_hash', sa.String(length=64), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('row_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("body_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_chapter_package_body_hash_is_sha256')),
    sa.CheckConstraint("package_key ~ '^[a-z0-9][a-z0-9-]{0,119}$'", name=op.f('ck_chapter_package_package_key_format')),
    sa.CheckConstraint("project_key ~ '^[a-z0-9][a-z0-9-]{0,79}$'", name=op.f('ck_chapter_package_project_key_format')),
    sa.CheckConstraint('version >= 1', name=op.f('ck_chapter_package_version_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_chapter_package')),
    sa.UniqueConstraint('project_key', 'package_key', 'version', name=op.f('uq_chapter_package_project_key_package_key_version'))
    )
    op.create_table('media_progress',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('profile_key', sa.String(length=40), nullable=False),
    sa.Column('project_key', sa.String(length=80), nullable=False),
    sa.Column('unit_key', sa.String(length=64), nullable=False),
    sa.Column('medium', sa.Enum('READING', 'WATCHING', name='progress_medium', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('series_key', sa.String(length=120), nullable=True),
    sa.Column('root_key', sa.String(length=48), nullable=False),
    sa.Column('relative_path', sa.Text(), nullable=False),
    sa.Column('member_name', sa.Text(), nullable=True),
    sa.Column('page_index', sa.Integer(), nullable=True),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('position_ms', sa.BigInteger(), nullable=True),
    sa.Column('duration_ms', sa.BigInteger(), nullable=True),
    sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("relative_path <> '' AND relative_path !~ '^/' AND relative_path !~ '^[A-Za-z]:' AND position(chr(92) in relative_path) = 0 AND relative_path !~ '(^|/)\\.\\.?(/|$)'", name=op.f('ck_media_progress_relative_path_is_relative')),
    sa.CheckConstraint("root_key ~ '^(source_vault|intake:[a-z0-9][a-z0-9-]{0,39})$'", name=op.f('ck_media_progress_root_key_is_catalog_root')),
    sa.CheckConstraint('page_index IS NULL OR page_index >= 0', name=op.f('ck_media_progress_page_non_negative')),
    sa.CheckConstraint('position_ms IS NULL OR position_ms >= 0', name=op.f('ck_media_progress_position_non_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_media_progress')),
    sa.UniqueConstraint('profile_key', 'project_key', 'unit_key', name=op.f('uq_media_progress_profile_key_project_key_unit_key'))
    )
    op.create_index('ix_media_progress_recent', 'media_progress', ['profile_key', 'project_key', 'opened_at'], unique=False)
    op.create_index('ix_media_progress_series', 'media_progress', ['profile_key', 'series_key'], unique=False)
    op.create_table('music_reference',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_key', sa.String(length=80), nullable=False),
    sa.Column('track', sa.String(length=300), nullable=False),
    sa.Column('artist', sa.String(length=300), nullable=False),
    sa.Column('reference', sa.Text(), nullable=False),
    sa.Column('episode', sa.String(length=40), nullable=False),
    sa.Column('scene', sa.String(length=200), nullable=False),
    sa.Column('mood', sa.String(length=200), nullable=False),
    sa.Column('intended_use', sa.String(length=200), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('row_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("project_key ~ '^[a-z0-9][a-z0-9-]{0,79}$'", name=op.f('ck_music_reference_project_key_format')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_music_reference'))
    )
    op.create_index('ix_music_reference_project_key', 'music_reference', ['project_key'], unique=False)
    op.create_table('reference_manifest',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_key', sa.String(length=80), nullable=False),
    sa.Column('label', sa.String(length=200), nullable=False),
    sa.Column('request', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('manifest', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('manifest_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("manifest_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_reference_manifest_manifest_hash_is_sha256')),
    sa.CheckConstraint("project_key ~ '^[a-z0-9][a-z0-9-]{0,79}$'", name=op.f('ck_reference_manifest_project_key_format')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reference_manifest')),
    sa.UniqueConstraint('project_key', 'manifest_hash', name=op.f('uq_reference_manifest_project_key_manifest_hash'))
    )
    op.create_table('catalog_scan',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('root_key', sa.String(length=48), nullable=False),
    sa.Column('job_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.Enum('RUNNING', 'COMPLETED', name='scan_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('scanner_version', sa.Integer(), nullable=False),
    sa.Column('survey', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('counts', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("root_key ~ '^(source_vault|intake:[a-z0-9][a-z0-9-]{0,39})$'", name=op.f('ck_catalog_scan_root_key_is_catalog_root')),
    sa.ForeignKeyConstraint(['job_id'], ['job.id'], name=op.f('fk_catalog_scan_job_id_job'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_catalog_scan'))
    )
    op.create_index('ix_catalog_scan_root_key_started_at', 'catalog_scan', ['root_key', 'started_at'], unique=False)
    op.create_table('catalog_entry',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('root_key', sa.String(length=48), nullable=False),
    sa.Column('relative_path', sa.Text(), nullable=False),
    sa.Column('file_name', sa.Text(), nullable=False),
    sa.Column('extension', sa.String(length=24), nullable=False),
    sa.Column('byte_size', sa.BigInteger(), nullable=False),
    sa.Column('mtime_ns', sa.BigInteger(), nullable=False),
    sa.Column('detected_kind', sa.Enum('ARCHIVE', 'VIDEO', 'IMAGE', 'DOCUMENT', 'SOFTWARE', 'EMPTY', 'OTHER', name='detected_kind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('detected_format', sa.String(length=32), nullable=False),
    sa.Column('status', sa.Enum('CATALOGUED', 'UNSUPPORTED', 'FAILED', 'MISSING', name='entry_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('status_reason', sa.Text(), nullable=False),
    sa.Column('material_class', sa.Enum('MANGA', 'MANHWA', 'MANHUA', 'COMIC', 'ANIME', 'FAN_ART', 'REFERENCE', 'DOCUMENT', 'SOFTWARE', 'UNKNOWN', name='material_class', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('collection', sa.String(length=120), nullable=False),
    sa.Column('series_key', sa.String(length=120), nullable=True),
    sa.Column('series_title', sa.Text(), nullable=True),
    sa.Column('facts', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('archive_view', sa.String(length=16), nullable=True),
    sa.Column('member_count', sa.Integer(), nullable=False),
    sa.Column('image_count', sa.Integer(), nullable=False),
    sa.Column('video_count', sa.Integer(), nullable=False),
    sa.Column('other_count', sa.Integer(), nullable=False),
    sa.Column('quick_fingerprint', sa.String(length=64), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('hash_source', sa.Enum('ENGINE_INDEX', 'COMPUTED', name='hash_source', native_enum=False, create_constraint=True, length=32), nullable=True),
    sa.Column('hashed_size', sa.BigInteger(), nullable=True),
    sa.Column('hashed_mtime_ns', sa.BigInteger(), nullable=True),
    sa.Column('duplicate_of_id', sa.Uuid(), nullable=True),
    sa.Column('scanner_version', sa.Integer(), nullable=False),
    sa.Column('last_seen_scan_id', sa.Uuid(), nullable=True),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('missing_since', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_catalog_entry_hash_is_sha256')),
    sa.CheckConstraint("relative_path <> '' AND relative_path !~ '^/' AND relative_path !~ '^[A-Za-z]:' AND position(chr(92) in relative_path) = 0 AND relative_path !~ '(^|/)\\.\\.?(/|$)'", name=op.f('ck_catalog_entry_relative_path_is_relative')),
    sa.CheckConstraint("root_key ~ '^(source_vault|intake:[a-z0-9][a-z0-9-]{0,39})$'", name=op.f('ck_catalog_entry_root_key_is_catalog_root')),
    sa.CheckConstraint('byte_size >= 0', name=op.f('ck_catalog_entry_byte_size_non_negative')),
    sa.CheckConstraint('content_hash IS NULL OR (hashed_size IS NOT NULL AND hashed_mtime_ns IS NOT NULL AND hash_source IS NOT NULL)', name=op.f('ck_catalog_entry_hash_records_its_observation')),
    sa.ForeignKeyConstraint(['duplicate_of_id'], ['catalog_entry.id'], name=op.f('fk_catalog_entry_duplicate_of_id_catalog_entry'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['last_seen_scan_id'], ['catalog_scan.id'], name=op.f('fk_catalog_entry_last_seen_scan_id_catalog_scan'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_catalog_entry')),
    sa.UniqueConstraint('root_key', 'relative_path', name=op.f('uq_catalog_entry_root_key_relative_path'))
    )
    op.create_index('ix_catalog_entry_content_hash', 'catalog_entry', ['content_hash'], unique=False)
    op.create_index('ix_catalog_entry_series_key', 'catalog_entry', ['series_key'], unique=False)
    op.create_index('ix_catalog_entry_status', 'catalog_entry', ['status'], unique=False)
    op.create_table('catalog_member',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('entry_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Enum('VIDEO', 'PAGE_GROUP', name='member_kind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('byte_size', sa.BigInteger(), nullable=False),
    sa.Column('compressed_size', sa.BigInteger(), nullable=False),
    sa.Column('crc32', sa.BigInteger(), nullable=True),
    sa.Column('compress_type', sa.Integer(), nullable=True),
    sa.Column('encrypted', sa.Boolean(), nullable=False),
    sa.Column('first_page_index', sa.Integer(), nullable=True),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('cached_sha256', sa.String(length=64), nullable=True),
    sa.Column('cached_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("cached_sha256 IS NULL OR cached_sha256 ~ '^[0-9a-f]{64}$'", name=op.f('ck_catalog_member_cached_hash_is_sha256')),
    sa.ForeignKeyConstraint(['entry_id'], ['catalog_entry.id'], name=op.f('fk_catalog_member_entry_id_catalog_entry'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_catalog_member')),
    sa.UniqueConstraint('entry_id', 'kind', 'name', name=op.f('uq_catalog_member_entry_id_kind_name'))
    )
    op.create_index('ix_catalog_member_entry_id', 'catalog_member', ['entry_id'], unique=False)
    op.create_table('catalog_unit',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('unit_key', sa.String(length=64), nullable=False),
    sa.Column('entry_id', sa.Uuid(), nullable=False),
    sa.Column('member_id', sa.Uuid(), nullable=True),
    sa.Column('kind', sa.Enum('MANGA_CHAPTER', 'ARCHIVE_PAGES', 'EPISODE', 'VIDEO', 'IMAGE', 'DOCUMENT', name='unit_kind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('material_class', sa.Enum('MANGA', 'MANHWA', 'MANHUA', 'COMIC', 'ANIME', 'FAN_ART', 'REFERENCE', 'DOCUMENT', 'SOFTWARE', 'UNKNOWN', name='material_class', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('collection', sa.String(length=120), nullable=False),
    sa.Column('series_key', sa.String(length=120), nullable=True),
    sa.Column('series_title', sa.Text(), nullable=True),
    sa.Column('program_title', sa.Text(), nullable=True),
    sa.Column('season', sa.Integer(), nullable=True),
    sa.Column('episode', sa.Integer(), nullable=True),
    sa.Column('episode_kind', sa.Enum('REGULAR', 'SPECIAL', 'OVA', 'MOVIE', 'RECAP', 'UNKNOWN', name='episode_kind', native_enum=False, create_constraint=True, length=32), nullable=True),
    sa.Column('chapter_number', sa.Numeric(precision=10, scale=3), nullable=True),
    sa.Column('volume', sa.Integer(), nullable=True),
    sa.Column('label', sa.Text(), nullable=False),
    sa.Column('sort_key', sa.String(length=400), nullable=False),
    sa.Column('first_page_index', sa.Integer(), nullable=True),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('confidence', sa.Enum('HIGH', 'MEDIUM', 'LOW', name='confidence', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('flags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('search_text', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('episode IS NULL OR episode >= 0', name=op.f('ck_catalog_unit_episode_non_negative')),
    sa.CheckConstraint('first_page_index IS NULL OR first_page_index >= 0', name=op.f('ck_catalog_unit_first_page_non_negative')),
    sa.CheckConstraint('season IS NULL OR season >= 0', name=op.f('ck_catalog_unit_season_non_negative')),
    sa.ForeignKeyConstraint(['entry_id'], ['catalog_entry.id'], name=op.f('fk_catalog_unit_entry_id_catalog_entry'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['member_id'], ['catalog_member.id'], name=op.f('fk_catalog_unit_member_id_catalog_member'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_catalog_unit')),
    sa.UniqueConstraint('unit_key', name=op.f('uq_catalog_unit_unit_key'))
    )
    op.create_index('ix_catalog_unit_entry_id', 'catalog_unit', ['entry_id'], unique=False)
    op.create_index('ix_catalog_unit_series', 'catalog_unit', ['series_key', 'kind', 'sort_key'], unique=False)

    for table in ('reference_item', 'reference_candidate'):
        op.add_column(table, sa.Column('collection', sa.String(length=120), server_default='', nullable=False))
        op.add_column(table, sa.Column('source_posted_at', sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column('rights_status', sa.String(length=32), server_default='UNKNOWN', nullable=False))
        op.add_column(
            table,
            sa.Column('training_eligibility', sa.String(length=32), server_default='MANUAL_REVIEW', nullable=False),
        )
        op.create_check_constraint(op.f(f'ck_{table}_rights_status'), table, _in('rights_status', _RIGHTS))
        op.create_check_constraint(
            op.f(f'ck_{table}_training_eligibility'), table, _in('training_eligibility', _TRAINING)
        )

    op.drop_constraint(op.f('ck_reference_item_reference_class'), 'reference_item', type_='check')
    op.create_check_constraint(
        op.f('ck_reference_item_reference_class'), 'reference_item', _in('reference_class', _CLASSES_AFTER)
    )
    op.drop_constraint(op.f('ck_reference_candidate_reference_class'), 'reference_candidate', type_='check')
    op.create_check_constraint(
        op.f('ck_reference_candidate_reference_class'),
        'reference_candidate',
        _in('suggested_class', _CLASSES_AFTER),
    )


def downgrade() -> None:
    # An UNSORTED reference cannot be represented before this revision, and
    # re-classifying a person's references on their behalf is not an option.
    unsorted = op.get_bind().execute(
        sa.text("SELECT count(*) FROM reference_item WHERE reference_class = 'UNSORTED'")
    ).scalar_one()
    if unsorted:
        raise RuntimeError(
            f"{unsorted} references are UNSORTED, which revision 0002 cannot represent. "
            "Sort them (or remove them) before downgrading; nothing was changed."
        )
    # A candidate's class is only a suggestion; dropping an unrepresentable one loses no decision.
    op.execute("UPDATE reference_candidate SET suggested_class = NULL WHERE suggested_class = 'UNSORTED'")
    op.drop_constraint(op.f('ck_reference_candidate_reference_class'), 'reference_candidate', type_='check')
    op.create_check_constraint(
        op.f('ck_reference_candidate_reference_class'),
        'reference_candidate',
        _in('suggested_class', _CLASSES_BEFORE),
    )
    op.drop_constraint(op.f('ck_reference_item_reference_class'), 'reference_item', type_='check')
    op.create_check_constraint(
        op.f('ck_reference_item_reference_class'), 'reference_item', _in('reference_class', _CLASSES_BEFORE)
    )
    for table in ('reference_candidate', 'reference_item'):
        op.drop_constraint(op.f(f'ck_{table}_training_eligibility'), table, type_='check')
        op.drop_constraint(op.f(f'ck_{table}_rights_status'), table, type_='check')
        op.drop_column(table, 'training_eligibility')
        op.drop_column(table, 'rights_status')
        op.drop_column(table, 'source_posted_at')
        op.drop_column(table, 'collection')

    op.drop_index('ix_catalog_unit_series', table_name='catalog_unit')
    op.drop_index('ix_catalog_unit_entry_id', table_name='catalog_unit')
    op.drop_table('catalog_unit')
    op.drop_index('ix_catalog_member_entry_id', table_name='catalog_member')
    op.drop_table('catalog_member')
    op.drop_index('ix_catalog_entry_status', table_name='catalog_entry')
    op.drop_index('ix_catalog_entry_series_key', table_name='catalog_entry')
    op.drop_index('ix_catalog_entry_content_hash', table_name='catalog_entry')
    op.drop_table('catalog_entry')
    op.drop_index('ix_catalog_scan_root_key_started_at', table_name='catalog_scan')
    op.drop_table('catalog_scan')
    op.drop_table('reference_manifest')
    op.drop_index('ix_music_reference_project_key', table_name='music_reference')
    op.drop_table('music_reference')
    op.drop_index('ix_media_progress_series', table_name='media_progress')
    op.drop_index('ix_media_progress_recent', table_name='media_progress')
    op.drop_table('media_progress')
    op.drop_table('chapter_package')
