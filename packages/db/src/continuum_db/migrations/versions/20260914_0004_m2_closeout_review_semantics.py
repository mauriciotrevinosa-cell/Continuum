"""M2 closeout: technical passes are not creative approvals; references keep provenance.

Revision ID: 0004_m2_closeout
Revises: 0003_phase15
Create Date: 2026-09-14

Rough production (Tier D):

* ``rough_artifact.purpose`` - PRODUCTION, WORKFLOW_TEST or NON_CANON_SAMPLE.
  The artifact's unique key gains the purpose, so a workflow test of a page
  never occupies that page's production slot.
* ``rough_attempt.output_class`` - TEST_RENDER or ARTWORK_CANDIDATE, set by the
  renderer. A database check forbids creative or final approval of anything
  but an artwork candidate.
* The single ``APPROVED`` state and ``APPROVE`` decision are split into
  TECHNICAL_PASS, CREATIVE_APPROVED / CREATIVE_APPROVE and FINAL_APPROVED /
  FINAL_APPROVE.
* ``attempt_review.reclassified_from`` records a decision's original value
  when this upgrade changes what it means.
* ``attempt_input.provenance`` snapshots each chosen reference's provenance.

Existing M2 data is reclassified, never deleted. Before this revision the
only renderer that could draw a rough was the deterministic sketch provider,
so every rendered attempt is a TEST_RENDER; every ``APPROVED`` attempt becomes
TECHNICAL_PASS, every ``APPROVE`` review becomes TECHNICAL_PASS with
``reclassified_from = 'APPROVE'``, and every artifact whose attempts are all
test renders becomes a WORKFLOW_TEST. Attempts, bytes, recipes, bundles,
seeds, hashes, ancestry and notes are untouched.

Reference Vault (Tier C): ``character_profile`` gains ``origin``
(SOURCE_WORK or PROJECT_ORIGINAL), ``project_key`` and ``design_documents``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0004_m2_closeout'
down_revision: str | None = '0003_phase15'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATES_BEFORE = ('QUEUED', 'GENERATED', 'APPROVED', 'REJECTED', 'SUPERSEDED')
_STATES_AFTER = (
    'QUEUED', 'GENERATED', 'TECHNICAL_PASS', 'CREATIVE_APPROVED', 'FINAL_APPROVED', 'REJECTED',
    'SUPERSEDED',
)
_DECISIONS_BEFORE = ('APPROVE', 'REJECT', 'REGENERATE')
_DECISIONS_AFTER = ('TECHNICAL_PASS', 'CREATIVE_APPROVE', 'FINAL_APPROVE', 'REJECT', 'REGENERATE')
_PURPOSES = ('PRODUCTION', 'WORKFLOW_TEST', 'NON_CANON_SAMPLE')
_OUTPUTS = ('TEST_RENDER', 'ARTWORK_CANDIDATE')
_ORIGINS = ('SOURCE_WORK', 'PROJECT_ORIGINAL')
_OLD_UNIQUE = 'uq_rough_artifact_project_key_episode_page_panel_kind'
_NEW_UNIQUE = 'uq_rough_artifact_project_key_purpose_episode_page_panel_kind'


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    # -- rough artifacts: purpose ------------------------------------------------
    op.add_column(
        'rough_artifact',
        sa.Column('purpose', sa.String(length=32), server_default='PRODUCTION', nullable=False),
    )
    op.create_check_constraint(
        op.f('ck_rough_artifact_rough_purpose'), 'rough_artifact', _in('purpose', _PURPOSES)
    )
    op.drop_constraint(op.f(_OLD_UNIQUE), 'rough_artifact', type_='unique')
    op.create_unique_constraint(
        op.f(_NEW_UNIQUE),
        'rough_artifact',
        ['project_key', 'purpose', 'episode', 'page', 'panel', 'kind'],
        postgresql_nulls_not_distinct=True,
    )

    # -- attempts: what the image is evidence of ---------------------------------
    op.add_column('rough_attempt', sa.Column('output_class', sa.String(length=32), nullable=True))
    op.create_check_constraint(
        op.f('ck_rough_attempt_render_output'),
        'rough_attempt',
        f"output_class IS NULL OR {_in('output_class', _OUTPUTS)}",
    )
    op.execute("UPDATE rough_attempt SET output_class = 'TEST_RENDER' WHERE state <> 'QUEUED'")
    op.create_check_constraint(
        op.f('ck_rough_attempt_output_class_iff_rendered'),
        'rough_attempt',
        "(state = 'QUEUED') = (output_class IS NULL)",
    )

    # -- the approval vocabulary, split ------------------------------------------
    op.drop_constraint(op.f('ck_rough_attempt_attempt_state'), 'rough_attempt', type_='check')
    op.execute("UPDATE rough_attempt SET state = 'TECHNICAL_PASS' WHERE state = 'APPROVED'")
    op.create_check_constraint(
        op.f('ck_rough_attempt_attempt_state'), 'rough_attempt', _in('state', _STATES_AFTER)
    )
    op.create_check_constraint(
        op.f('ck_rough_attempt_creative_approval_needs_artwork'),
        'rough_attempt',
        "state NOT IN ('CREATIVE_APPROVED', 'FINAL_APPROVED') OR output_class = 'ARTWORK_CANDIDATE'",
    )

    op.add_column(
        'attempt_review', sa.Column('reclassified_from', sa.String(length=32), nullable=True)
    )
    op.drop_constraint(op.f('ck_attempt_review_review_decision'), 'attempt_review', type_='check')
    op.execute(
        "UPDATE attempt_review SET reclassified_from = 'APPROVE', decision = 'TECHNICAL_PASS'"
        " WHERE decision = 'APPROVE'"
    )
    op.create_check_constraint(
        op.f('ck_attempt_review_review_decision'),
        'attempt_review',
        _in('decision', _DECISIONS_AFTER),
    )

    op.execute(
        "UPDATE rough_artifact AS a SET purpose = 'WORKFLOW_TEST'"
        " WHERE EXISTS (SELECT 1 FROM rough_attempt t WHERE t.artifact_id = a.id"
        "               AND t.output_class IS NOT NULL)"
        " AND NOT EXISTS (SELECT 1 FROM rough_attempt t WHERE t.artifact_id = a.id"
        "                 AND t.output_class = 'ARTWORK_CANDIDATE')"
    )

    # -- bundle provenance snapshot ---------------------------------------------
    op.add_column(
        'attempt_input',
        sa.Column(
            'provenance',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='{}',
            nullable=False,
        ),
    )

    # -- characters: original or from a source work ------------------------------
    op.add_column(
        'character_profile',
        sa.Column('origin', sa.String(length=32), server_default='SOURCE_WORK', nullable=False),
    )
    op.add_column('character_profile', sa.Column('project_key', sa.String(length=80), nullable=True))
    op.add_column(
        'character_profile',
        sa.Column(
            'design_documents',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default='[]',
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f('ck_character_profile_character_origin'), 'character_profile', _in('origin', _ORIGINS)
    )
    op.create_check_constraint(
        op.f('ck_character_profile_original_character_has_project'),
        'character_profile',
        "origin <> 'PROJECT_ORIGINAL' OR project_key IS NOT NULL",
    )


def downgrade() -> None:
    bind = op.get_bind()
    blocking = bind.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM rough_attempt"
            "        WHERE state IN ('CREATIVE_APPROVED', 'FINAL_APPROVED')"
            "        OR output_class = 'ARTWORK_CANDIDATE')"
            " + (SELECT count(*) FROM rough_artifact WHERE purpose = 'NON_CANON_SAMPLE')"
            " + (SELECT count(*) FROM character_profile WHERE origin = 'PROJECT_ORIGINAL')"
            " + (SELECT count(*) FROM (SELECT 1 FROM rough_artifact"
            "        GROUP BY project_key, episode, page, panel, kind HAVING count(*) > 1) d)"
        )
    ).scalar_one()
    if blocking:
        raise RuntimeError(
            f"{blocking} rows use creative/final approval, artwork, samples, original "
            "characters or a test beside a production page, which revision 0003 cannot represent."
        )
    op.drop_constraint(
        op.f('ck_character_profile_original_character_has_project'), 'character_profile', type_='check'
    )
    op.drop_constraint(op.f('ck_character_profile_character_origin'), 'character_profile', type_='check')
    op.drop_column('character_profile', 'design_documents')
    op.drop_column('character_profile', 'project_key')
    op.drop_column('character_profile', 'origin')
    op.drop_column('attempt_input', 'provenance')

    op.drop_constraint(op.f('ck_attempt_review_review_decision'), 'attempt_review', type_='check')
    op.execute("UPDATE attempt_review SET decision = 'APPROVE' WHERE decision = 'TECHNICAL_PASS'")
    op.create_check_constraint(
        op.f('ck_attempt_review_review_decision'),
        'attempt_review',
        _in('decision', _DECISIONS_BEFORE),
    )
    op.drop_column('attempt_review', 'reclassified_from')

    op.drop_constraint(
        op.f('ck_rough_attempt_creative_approval_needs_artwork'), 'rough_attempt', type_='check'
    )
    op.drop_constraint(op.f('ck_rough_attempt_attempt_state'), 'rough_attempt', type_='check')
    op.execute("UPDATE rough_attempt SET state = 'APPROVED' WHERE state = 'TECHNICAL_PASS'")
    op.create_check_constraint(
        op.f('ck_rough_attempt_attempt_state'), 'rough_attempt', _in('state', _STATES_BEFORE)
    )
    op.drop_constraint(op.f('ck_rough_attempt_output_class_iff_rendered'), 'rough_attempt', type_='check')
    op.drop_constraint(op.f('ck_rough_attempt_render_output'), 'rough_attempt', type_='check')
    op.drop_column('rough_attempt', 'output_class')

    op.drop_constraint(op.f(_NEW_UNIQUE), 'rough_artifact', type_='unique')
    op.create_unique_constraint(
        op.f(_OLD_UNIQUE),
        'rough_artifact',
        ['project_key', 'episode', 'page', 'panel', 'kind'],
        postgresql_nulls_not_distinct=True,
    )
    op.drop_constraint(op.f('ck_rough_artifact_rough_purpose'), 'rough_artifact', type_='check')
    op.drop_column('rough_artifact', 'purpose')
