"""M3 W8: add WARDROBE to the attempt-input bundle roles.

Revision ID: 0012_m3_wardrobe_bundle_role
Revises: 0011_m3_wardrobe_condition
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_m3_wardrobe_bundle_role"
down_revision: str | None = "0011_m3_wardrobe_condition"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLES_BEFORE = (
    "CANON",
    "STYLE",
    "TECHNIQUE",
    "MOOD",
    "SOURCE_PLATE",
    "CONTINUITY",
    "GRAMMAR",
    "ENVIRONMENT",
)
_ROLES_AFTER = (*_ROLES_BEFORE, "WARDROBE")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.drop_constraint(op.f("ck_attempt_input_bundle_role"), "attempt_input", type_="check")
    op.create_check_constraint(
        op.f("ck_attempt_input_bundle_role"), "attempt_input", _in("role", _ROLES_AFTER)
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_attempt_input_bundle_role"), "attempt_input", type_="check")
    op.create_check_constraint(
        op.f("ck_attempt_input_bundle_role"), "attempt_input", _in("role", _ROLES_BEFORE)
    )