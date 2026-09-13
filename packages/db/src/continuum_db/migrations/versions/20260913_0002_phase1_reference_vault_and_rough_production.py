"""Phase 1: reference vault (Tiers A-C) and rough-manga production (Tier D).

Revision ID: 0002_phase1
Revises: 0001_phase0
Create Date: 2026-09-13

Creates only Phase 1 tables; ``continuum_db.tiers`` declares each table's
tier and ``tests/invariants`` checks that foreign keys point only downward.
No Phase 0 table, column or constraint is altered here.

No column stores source bytes, and no column stores a Source Vault path as
identity: bytes are addressed by content hash and locations are observations.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0002_phase1'
down_revision: str | None = '0001_phase0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('character_profile',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=False),
    sa.Column('source_label', sa.String(length=200), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('scale_notes', sa.Text(), nullable=False),
    sa.Column('distinguishing_marks', sa.Text(), nullable=False),
    sa.Column('posture_notes', sa.Text(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('row_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_character_profile'))
    )
    op.create_table('generation_recipe',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('mode', sa.Enum('NEW_GENERATION', 'SOURCE_DERIVED_EDIT', 'COMPOSITE', 'LAYOUT_ONLY', name='rough_mode', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('recipe_schema_version', sa.Integer(), nullable=False),
    sa.Column('template_package_version', sa.String(length=40), nullable=False),
    sa.Column('intent', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('execution', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('intent_hash', sa.String(length=64), nullable=False),
    sa.Column('execution_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("execution_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_generation_recipe_execution_hash_is_sha256')),
    sa.CheckConstraint("intent_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_generation_recipe_intent_hash_is_sha256')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_generation_recipe'))
    )
    op.create_index('ix_generation_recipe_intent_hash', 'generation_recipe', ['intent_hash'], unique=False)
    op.create_table('library_asset',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('medium', sa.Enum('ARCHIVE', 'IMAGE', 'PDF', 'VIDEO', name='asset_medium', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('origin', sa.Enum('SOURCE_VAULT', 'USER_ADDED', 'GENERATED', name='asset_origin', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('byte_size', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_library_asset_content_hash_is_sha256')),
    sa.CheckConstraint('byte_size >= 0', name=op.f('ck_library_asset_byte_size_non_negative')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_library_asset')),
    sa.UniqueConstraint('content_hash', name=op.f('uq_library_asset_content_hash'))
    )
    op.create_table('rough_artifact',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_key', sa.String(length=80), nullable=False),
    sa.Column('episode', sa.String(length=40), nullable=False),
    sa.Column('chapter', sa.Integer(), nullable=True),
    sa.Column('page', sa.Integer(), nullable=False),
    sa.Column('panel', sa.Integer(), nullable=True),
    sa.Column('kind', sa.Enum('PANEL', 'PAGE', name='rough_artifact_kind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('panel_script_document', sa.String(length=80), nullable=True),
    sa.Column('panel_script_version', sa.String(length=20), nullable=True),
    sa.Column('brief', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(kind = 'PANEL') = (panel IS NOT NULL)", name=op.f('ck_rough_artifact_panel_kind_has_panel')),
    sa.CheckConstraint('chapter IS NULL OR chapter >= 1', name=op.f('ck_rough_artifact_chapter_positive')),
    sa.CheckConstraint('page >= 1 AND (panel IS NULL OR panel >= 1)', name=op.f('ck_rough_artifact_page_panel_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rough_artifact')),
    sa.UniqueConstraint('project_key', 'episode', 'page', 'panel', 'kind', name=op.f('uq_rough_artifact_project_key_episode_page_panel_kind'), postgresql_nulls_not_distinct=True)
    )
    op.create_index('ix_rough_artifact_project_key', 'rough_artifact', ['project_key'], unique=False)
    op.create_table('visual_mode',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('row_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_visual_mode'))
    )
    op.create_table('character_outfit',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('character_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.Enum('SOURCE_DEFAULT', 'SOURCE_ALTERNATE', 'PROJECT', 'OTHER', name='outfit_kind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('project_key', sa.String(length=80), nullable=True),
    sa.Column('era', sa.String(length=120), nullable=False),
    sa.Column('season_weather', sa.String(length=120), nullable=False),
    sa.Column('condition', sa.String(length=120), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('row_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(kind = 'PROJECT') = (project_key IS NOT NULL)", name=op.f('ck_character_outfit_project_outfit_names_project')),
    sa.ForeignKeyConstraint(['character_id'], ['character_profile.id'], name=op.f('fk_character_outfit_character_id_character_profile'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_character_outfit'))
    )
    op.create_index('ix_character_outfit_character_id', 'character_outfit', ['character_id'], unique=False)
    op.create_table('library_asset_location',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('asset_id', sa.Uuid(), nullable=False),
    sa.Column('root_key', sa.String(length=32), nullable=False),
    sa.Column('relative_path', sa.Text(), nullable=False),
    sa.Column('byte_size', sa.BigInteger(), nullable=False),
    sa.Column('mtime_ns', sa.BigInteger(), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("relative_path <> '' AND relative_path !~ '^/' AND relative_path !~ '^[A-Za-z]:' AND position(chr(92) in relative_path) = 0 AND relative_path !~ '(^|/)\\.\\.?(/|$)'", name=op.f('ck_library_asset_location_relative_path_is_relative')),
    sa.CheckConstraint("root_key IN ('source_vault', 'library', 'generated')", name=op.f('ck_library_asset_location_known_root_key')),
    sa.ForeignKeyConstraint(['asset_id'], ['library_asset.id'], name=op.f('fk_library_asset_location_asset_id_library_asset'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_library_asset_location')),
    sa.UniqueConstraint('root_key', 'relative_path', 'byte_size', 'mtime_ns', name=op.f('uq_library_asset_location_root_key_relative_path_byte_size_mtime_ns'))
    )
    op.create_index('ix_library_asset_location_asset_id', 'library_asset_location', ['asset_id'], unique=False)
    op.create_table('reference_item',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('asset_id', sa.Uuid(), nullable=False),
    sa.Column('locator', sa.Text(), nullable=False),
    sa.Column('unit_index', sa.Integer(), nullable=True),
    sa.Column('region_x', sa.Float(), nullable=True),
    sa.Column('region_y', sa.Float(), nullable=True),
    sa.Column('region_width', sa.Float(), nullable=True),
    sa.Column('region_height', sa.Float(), nullable=True),
    sa.Column('reference_class', sa.Enum('CANON', 'TECHNIQUE', 'CONTINUITY', 'MOOD', name='reference_class', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('origin', sa.Enum('SOURCE', 'OFFICIAL_ART', 'FAN_ART', 'USER_CREATED', 'GENERATED', 'PROJECT_APPROVED', name='reference_origin', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('label', sa.String(length=300), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('favorite', sa.Boolean(), nullable=False),
    sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('row_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('(region_x IS NULL AND region_y IS NULL AND region_width IS NULL AND region_height IS NULL) OR (region_x >= 0 AND region_y >= 0 AND region_width > 0 AND region_height > 0 AND region_x + region_width <= 1.000001 AND region_y + region_height <= 1.000001)', name=op.f('ck_reference_item_region_all_or_none_and_inside')),
    sa.CheckConstraint('unit_index IS NULL OR unit_index >= 0', name=op.f('ck_reference_item_unit_index_non_negative')),
    sa.ForeignKeyConstraint(['asset_id'], ['library_asset.id'], name=op.f('fk_reference_item_asset_id_library_asset'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reference_item'))
    )
    op.create_index('ix_reference_item_asset_id', 'reference_item', ['asset_id'], unique=False)
    op.create_index('ix_reference_item_locator', 'reference_item', ['locator'], unique=False)
    op.create_table('project_panel_source',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_key', sa.String(length=80), nullable=False),
    sa.Column('episode', sa.String(length=40), nullable=False),
    sa.Column('chapter', sa.Integer(), nullable=True),
    sa.Column('page', sa.Integer(), nullable=False),
    sa.Column('panel', sa.Integer(), nullable=True),
    sa.Column('reference_id', sa.Uuid(), nullable=False),
    sa.Column('role', sa.Enum('SOURCE_PLATE', 'COMPOSITION', 'ENVIRONMENT', 'CONTINUITY', 'COMPARISON', 'MOOD', name='panel_source_role', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('chapter IS NULL OR chapter >= 1', name=op.f('ck_project_panel_source_chapter_positive')),
    sa.CheckConstraint('page >= 1 AND (panel IS NULL OR panel >= 1)', name=op.f('ck_project_panel_source_page_panel_positive')),
    sa.ForeignKeyConstraint(['reference_id'], ['reference_item.id'], name=op.f('fk_project_panel_source_reference_id_reference_item'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_project_panel_source')),
    sa.UniqueConstraint('project_key', 'episode', 'page', 'panel', 'reference_id', 'role', name=op.f('uq_project_panel_source_project_key_episode_page_panel_reference_id_role'), postgresql_nulls_not_distinct=True)
    )
    op.create_index('ix_project_panel_source_target', 'project_panel_source', ['project_key', 'episode', 'page'], unique=False)
    op.create_table('project_reference_standing',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('project_key', sa.String(length=80), nullable=False),
    sa.Column('reference_id', sa.Uuid(), nullable=False),
    sa.Column('character_id', sa.Uuid(), nullable=True),
    sa.Column('standing', sa.Enum('USEFUL', 'CANONICAL_FOR_PROJECT', 'PREFERRED_FOR_CURRENT_LOOK', name='project_standing', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['character_id'], ['character_profile.id'], name=op.f('fk_project_reference_standing_character_id_character_profile'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reference_id'], ['reference_item.id'], name=op.f('fk_project_reference_standing_reference_id_reference_item'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_project_reference_standing')),
    sa.UniqueConstraint('project_key', 'reference_id', 'character_id', 'standing', name=op.f('uq_project_reference_standing_project_key_reference_id_character_id_standing'), postgresql_nulls_not_distinct=True)
    )
    op.create_index('ix_project_reference_standing_project_key', 'project_reference_standing', ['project_key'], unique=False)
    op.create_table('reference_character',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('reference_id', sa.Uuid(), nullable=False),
    sa.Column('character_id', sa.Uuid(), nullable=False),
    sa.Column('outfit_id', sa.Uuid(), nullable=True),
    sa.Column('aspect', sa.Enum('FACE', 'HAIR', 'FULL_BODY', 'PROPORTIONS', 'SCALE', 'DISTINGUISHING_MARK', 'POSTURE', 'OUTFIT', 'ACCESSORY', 'EXPRESSION', 'POSE', 'GESTURE', 'ACTION_POSE', 'QUIET_ACTING', 'COMEDIC_EXPRESSION', name='character_aspect', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('preferred', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['character_id'], ['character_profile.id'], name=op.f('fk_reference_character_character_id_character_profile'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['outfit_id'], ['character_outfit.id'], name=op.f('fk_reference_character_outfit_id_character_outfit'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reference_id'], ['reference_item.id'], name=op.f('fk_reference_character_reference_id_reference_item'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reference_character')),
    sa.UniqueConstraint('reference_id', 'character_id', 'aspect', 'outfit_id', name=op.f('uq_reference_character_reference_id_character_id_aspect_outfit_id'), postgresql_nulls_not_distinct=True)
    )
    op.create_index('ix_reference_character_character_id', 'reference_character', ['character_id'], unique=False)
    op.create_table('reference_descriptor',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('reference_id', sa.Uuid(), nullable=False),
    sa.Column('facet', sa.Enum('ERA', 'SEASON_WEATHER', 'CONDITION', 'EXPRESSION', 'POSE', 'SHOT_TYPE', 'CAMERA_ANGLE', 'SCENE_TYPE', 'ACTION_INTENSITY', 'DIALOGUE_DENSITY', 'BACKGROUND_COMPLEXITY', 'COMPOSITION', 'PAGE_TURN_FUNCTION', 'MOOD', 'PANEL_GEOMETRY', 'CHARACTER_COUNT', 'LOCATION', name='descriptor_facet', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('value', sa.String(length=200), nullable=False),
    sa.Column('origin', sa.Enum('USER', 'ANALYSIS', name='descriptor_origin', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('analyzer_ref', sa.String(length=120), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(origin = 'USER' AND confidence IS NULL AND analyzer_ref IS NULL) OR (origin = 'ANALYSIS' AND analyzer_ref IS NOT NULL AND (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)))", name=op.f('ck_reference_descriptor_origin_matches_evidence')),
    sa.ForeignKeyConstraint(['reference_id'], ['reference_item.id'], name=op.f('fk_reference_descriptor_reference_id_reference_item'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reference_descriptor')),
    sa.UniqueConstraint('reference_id', 'facet', 'value', 'origin', name=op.f('uq_reference_descriptor_reference_id_facet_value_origin'))
    )
    op.create_table('reference_technique',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('reference_id', sa.Uuid(), nullable=False),
    sa.Column('visual_mode_id', sa.Uuid(), nullable=True),
    sa.Column('facet', sa.Enum('PAGE_COMPOSITION', 'PANEL_DENSITY', 'PAGE_TURN', 'ACTION_READABILITY', 'FACIAL_ACTING', 'DIALOGUE_FRAMING', 'NEGATIVE_SPACE', 'IMPACT_LANGUAGE', 'SCREENTONE', 'BACKGROUND_TREATMENT', 'COMEDY', 'HORROR', 'ROMANCE', 'ATMOSPHERE', 'ESTABLISHING_SHOT', 'EXPERIMENTAL_LAYOUT', 'LIGHTING', 'NIGHT_RENDERING', 'CINEMATOGRAPHY', 'MOTION_LANGUAGE', name='technique_facet', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['reference_id'], ['reference_item.id'], name=op.f('fk_reference_technique_reference_id_reference_item'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['visual_mode_id'], ['visual_mode.id'], name=op.f('fk_reference_technique_visual_mode_id_visual_mode'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_reference_technique')),
    sa.UniqueConstraint('reference_id', 'visual_mode_id', 'facet', name=op.f('uq_reference_technique_reference_id_visual_mode_id_facet'), postgresql_nulls_not_distinct=True)
    )
    op.create_index('ix_reference_technique_visual_mode_id', 'reference_technique', ['visual_mode_id'], unique=False)
    op.create_table('rough_attempt',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('artifact_id', sa.Uuid(), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('recipe_id', sa.Uuid(), nullable=False),
    sa.Column('parent_attempt_id', sa.Uuid(), nullable=True),
    sa.Column('job_id', sa.Uuid(), nullable=True),
    sa.Column('state', sa.Enum('QUEUED', 'GENERATED', 'APPROVED', 'REJECTED', 'SUPERSEDED', name='attempt_state', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('mime', sa.String(length=40), nullable=True),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("(state = 'QUEUED') = (content_hash IS NULL)", name=op.f('ck_rough_attempt_output_iff_rendered')),
    sa.CheckConstraint("content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_rough_attempt_content_hash_is_sha256')),
    sa.CheckConstraint('attempt >= 1', name=op.f('ck_rough_attempt_attempt_positive')),
    sa.ForeignKeyConstraint(['artifact_id'], ['rough_artifact.id'], name=op.f('fk_rough_attempt_artifact_id_rough_artifact'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['job_id'], ['job.id'], name=op.f('fk_rough_attempt_job_id_job'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['parent_attempt_id'], ['rough_attempt.id'], name=op.f('fk_rough_attempt_parent_attempt_id_rough_attempt'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['recipe_id'], ['generation_recipe.id'], name=op.f('fk_rough_attempt_recipe_id_generation_recipe'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rough_attempt')),
    sa.UniqueConstraint('artifact_id', 'attempt', name=op.f('uq_rough_attempt_artifact_id_attempt'))
    )
    op.create_index('ix_rough_attempt_job_id', 'rough_attempt', ['job_id'], unique=False)
    op.create_table('attempt_derivative',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('attempt_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.Enum('OUTPUT', 'MASK', 'SOURCE_CROP', name='derivative_kind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('mime', sa.String(length=40), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_attempt_derivative_content_hash_is_sha256')),
    sa.ForeignKeyConstraint(['attempt_id'], ['rough_attempt.id'], name=op.f('fk_attempt_derivative_attempt_id_rough_attempt'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attempt_derivative')),
    sa.UniqueConstraint('attempt_id', 'kind', 'content_hash', name=op.f('uq_attempt_derivative_attempt_id_kind_content_hash'))
    )
    op.create_table('attempt_input',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('attempt_id', sa.Uuid(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('role', sa.Enum('CANON', 'TECHNIQUE', 'MOOD', 'SOURCE_PLATE', 'CONTINUITY', name='bundle_role', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('reference_id', sa.Uuid(), nullable=True),
    sa.Column('locator', sa.Text(), nullable=False),
    sa.Column('unit_index', sa.Integer(), nullable=True),
    sa.Column('region_x', sa.Float(), nullable=True),
    sa.Column('region_y', sa.Float(), nullable=True),
    sa.Column('region_width', sa.Float(), nullable=True),
    sa.Column('region_height', sa.Float(), nullable=True),
    sa.Column('character_id', sa.Uuid(), nullable=True),
    sa.Column('outfit_id', sa.Uuid(), nullable=True),
    sa.Column('aspect', sa.Enum('FACE', 'HAIR', 'FULL_BODY', 'PROPORTIONS', 'SCALE', 'DISTINGUISHING_MARK', 'POSTURE', 'OUTFIT', 'ACCESSORY', 'EXPRESSION', 'POSE', 'GESTURE', 'ACTION_POSE', 'QUIET_ACTING', 'COMEDIC_EXPRESSION', name='character_aspect', native_enum=False, create_constraint=True, length=32), nullable=True),
    sa.Column('label', sa.String(length=300), nullable=False),
    sa.CheckConstraint('(region_x IS NULL AND region_y IS NULL AND region_width IS NULL AND region_height IS NULL) OR (region_x >= 0 AND region_y >= 0 AND region_width > 0 AND region_height > 0 AND region_x + region_width <= 1.000001 AND region_y + region_height <= 1.000001)', name=op.f('ck_attempt_input_region_all_or_none_and_inside')),
    sa.ForeignKeyConstraint(['attempt_id'], ['rough_attempt.id'], name=op.f('fk_attempt_input_attempt_id_rough_attempt'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['character_id'], ['character_profile.id'], name=op.f('fk_attempt_input_character_id_character_profile'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['outfit_id'], ['character_outfit.id'], name=op.f('fk_attempt_input_outfit_id_character_outfit'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reference_id'], ['reference_item.id'], name=op.f('fk_attempt_input_reference_id_reference_item'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attempt_input')),
    sa.UniqueConstraint('attempt_id', 'position', name=op.f('uq_attempt_input_attempt_id_position'))
    )
    op.create_index('ix_attempt_input_locator', 'attempt_input', ['locator'], unique=False)
    op.create_index('ix_attempt_input_reference_id', 'attempt_input', ['reference_id'], unique=False)
    op.create_table('attempt_review',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('attempt_id', sa.Uuid(), nullable=False),
    sa.Column('decision', sa.Enum('APPROVE', 'REJECT', 'REGENERATE', name='review_decision', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['attempt_id'], ['rough_attempt.id'], name=op.f('fk_attempt_review_attempt_id_rough_attempt'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attempt_review'))
    )
    op.create_index('ix_attempt_review_attempt_id', 'attempt_review', ['attempt_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_attempt_review_attempt_id', table_name='attempt_review')
    op.drop_table('attempt_review')
    op.drop_index('ix_attempt_input_reference_id', table_name='attempt_input')
    op.drop_index('ix_attempt_input_locator', table_name='attempt_input')
    op.drop_table('attempt_input')
    op.drop_table('attempt_derivative')
    op.drop_index('ix_rough_attempt_job_id', table_name='rough_attempt')
    op.drop_table('rough_attempt')
    op.drop_index('ix_reference_technique_visual_mode_id', table_name='reference_technique')
    op.drop_table('reference_technique')
    op.drop_table('reference_descriptor')
    op.drop_index('ix_reference_character_character_id', table_name='reference_character')
    op.drop_table('reference_character')
    op.drop_index('ix_project_reference_standing_project_key', table_name='project_reference_standing')
    op.drop_table('project_reference_standing')
    op.drop_index('ix_project_panel_source_target', table_name='project_panel_source')
    op.drop_table('project_panel_source')
    op.drop_index('ix_reference_item_locator', table_name='reference_item')
    op.drop_index('ix_reference_item_asset_id', table_name='reference_item')
    op.drop_table('reference_item')
    op.drop_index('ix_library_asset_location_asset_id', table_name='library_asset_location')
    op.drop_table('library_asset_location')
    op.drop_index('ix_character_outfit_character_id', table_name='character_outfit')
    op.drop_table('character_outfit')
    op.drop_table('visual_mode')
    op.drop_index('ix_rough_artifact_project_key', table_name='rough_artifact')
    op.drop_table('rough_artifact')
    op.drop_table('library_asset')
    op.drop_index('ix_generation_recipe_intent_hash', table_name='generation_recipe')
    op.drop_table('generation_recipe')
    op.drop_table('character_profile')
