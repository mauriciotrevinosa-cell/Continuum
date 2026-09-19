"""M3 layered construction: a panel stage per artifact, and the upstream-stage input role.

Revision ID: 0017_layered_panel_stages
Revises: 0016_vk_technique_facets
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_layered_panel_stages"
down_revision: str | None = "0016_vk_technique_facets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STAGES = (
    "COMPOSITION",
    "DRAWING",
    "LINE",
    "VALUE_MATERIAL",
    "LIGHT_SHADOW",
    "FX",
    "ENVIRONMENT_INTEGRATION",
    "FINISH",
)
_ROLES_BEFORE = (
    "CANON",
    "STYLE",
    "TECHNIQUE",
    "MOOD",
    "SOURCE_PLATE",
    "CONTINUITY",
    "GRAMMAR",
    "ENVIRONMENT",
    "WARDROBE",
)
_ROLES_AFTER = (*_ROLES_BEFORE, "UPSTREAM_STAGE")
_UNIQUE_BEFORE = "uq_rough_artifact_project_key_purpose_production_run_id_b8b8"
_UNIQUE_AFTER = "uq_rough_artifact_project_key_purpose_production_run_id_1fe2"
_KEY = ("project_key", "purpose", "production_run_id", "episode", "page", "panel", "kind")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.add_column("rough_artifact", sa.Column("stage", sa.String(length=32), nullable=True))
    op.create_check_constraint(
        op.f("ck_rough_artifact_panel_stage"), "rough_artifact", _in("stage", _STAGES)
    )
    op.create_check_constraint(
        op.f("ck_rough_artifact_stage_is_a_panel_stage"),
        "rough_artifact",
        "stage IS NULL OR kind = 'PANEL'",
    )
    op.drop_constraint(op.f(_UNIQUE_BEFORE), "rough_artifact", type_="unique")
    op.create_unique_constraint(
        op.f(_UNIQUE_AFTER),
        "rough_artifact",
        [*_KEY, "stage"],
        postgresql_nulls_not_distinct=True,
    )
    op.drop_constraint(op.f("ck_attempt_input_bundle_role"), "attempt_input", type_="check")
    op.create_check_constraint(
        op.f("ck_attempt_input_bundle_role"), "attempt_input", _in("role", _ROLES_AFTER)
    )


def downgrade() -> None:
    bind = op.get_bind()
    staged = bind.execute(
        sa.text("SELECT count(*) FROM rough_artifact WHERE stage IS NOT NULL")
    ).scalar_one()
    if staged:
        raise RuntimeError(
            f"{staged} layered panel stage artifact(s) exist; downgrading would merge their "
            "attempts into one panel. Export or remove them deliberately first."
        )
    op.drop_constraint(op.f("ck_attempt_input_bundle_role"), "attempt_input", type_="check")
    op.create_check_constraint(
        op.f("ck_attempt_input_bundle_role"), "attempt_input", _in("role", _ROLES_BEFORE)
    )
    op.drop_constraint(op.f(_UNIQUE_AFTER), "rough_artifact", type_="unique")
    op.create_unique_constraint(
        op.f(_UNIQUE_BEFORE), "rough_artifact", list(_KEY), postgresql_nulls_not_distinct=True
    )
    op.drop_constraint(op.f("ck_rough_artifact_stage_is_a_panel_stage"), "rough_artifact")
    op.drop_constraint(op.f("ck_rough_artifact_panel_stage"), "rough_artifact")
    op.drop_column("rough_artifact", "stage")
