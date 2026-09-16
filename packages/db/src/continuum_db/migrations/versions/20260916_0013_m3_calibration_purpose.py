"""M3 calibration: add CALIBRATION to the rough-purpose enum checks.

Revision ID: 0013_m3_calibration_purpose
Revises: 0012_m3_wardrobe_bundle_role
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013_m3_calibration_purpose"
down_revision: str | None = "0012_m3_wardrobe_bundle_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PURPOSES_BEFORE = ("PRODUCTION", "WORKFLOW_TEST", "NON_CANON_SAMPLE")
_PURPOSES_AFTER = (*_PURPOSES_BEFORE, "CALIBRATION")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    # The enum-generated check (native_enum=False, create_constraint=True) and
    # the explicit run_purpose check both constrain the same column; update both.
    op.drop_constraint(op.f("ck_rough_artifact_rough_purpose"), "rough_artifact", type_="check")
    op.create_check_constraint(
        op.f("ck_rough_artifact_rough_purpose"), "rough_artifact", _in("purpose", _PURPOSES_AFTER)
    )
    op.drop_constraint(op.f("ck_production_run_rough_purpose"), "production_run", type_="check")
    op.create_check_constraint(
        op.f("ck_production_run_rough_purpose"),
        "production_run",
        _in("purpose", _PURPOSES_AFTER),
    )
    op.drop_constraint(op.f("ck_production_run_run_purpose"), "production_run", type_="check")
    op.create_check_constraint(
        op.f("ck_production_run_run_purpose"), "production_run", _in("purpose", _PURPOSES_AFTER)
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_production_run_run_purpose"), "production_run", type_="check")
    op.create_check_constraint(
        op.f("ck_production_run_run_purpose"), "production_run", _in("purpose", _PURPOSES_BEFORE)
    )
    op.drop_constraint(op.f("ck_production_run_rough_purpose"), "production_run", type_="check")
    op.create_check_constraint(
        op.f("ck_production_run_rough_purpose"),
        "production_run",
        _in("purpose", _PURPOSES_BEFORE),
    )
    op.drop_constraint(op.f("ck_rough_artifact_rough_purpose"), "rough_artifact", type_="check")
    op.create_check_constraint(
        op.f("ck_rough_artifact_rough_purpose"), "rough_artifact", _in("purpose", _PURPOSES_BEFORE)
    )