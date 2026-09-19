"""M3 Visual Knowledge: technique facets for the Visual Knowledge functions.

Revision ID: 0016_vk_technique_facets
Revises: 0015_vk_external_resource
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_vk_technique_facets"
down_revision: str | None = "0015_vk_external_resource"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BEFORE = (
    "PAGE_COMPOSITION",
    "PANEL_DENSITY",
    "PAGE_TURN",
    "ACTION_READABILITY",
    "FACIAL_ACTING",
    "DIALOGUE_FRAMING",
    "NEGATIVE_SPACE",
    "IMPACT_LANGUAGE",
    "SCREENTONE",
    "BACKGROUND_TREATMENT",
    "COMEDY",
    "HORROR",
    "ROMANCE",
    "ATMOSPHERE",
    "ESTABLISHING_SHOT",
    "EXPERIMENTAL_LAYOUT",
    "LIGHTING",
    "NIGHT_RENDERING",
    "CINEMATOGRAPHY",
    "MOTION_LANGUAGE",
)
_ADDED = (
    "ANATOMY",
    "HANDS",
    "CLOTHING",
    "POSE",
    "PERSPECTIVE",
    "COMPOSITION",
    "QUIET_ACTING",
    "ARCHITECTURE",
    "MATERIALS",
    "MAGIC",
    "FX",
    "LINEART",
    "COLOR",
    "MANGA_GRAMMAR",
    "PROCESS",
)
_NAME = "ck_reference_technique_technique_facet"


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.drop_constraint(op.f(_NAME), "reference_technique", type_="check")
    op.create_check_constraint(
        op.f(_NAME), "reference_technique", _in("facet", (*_BEFORE, *_ADDED))
    )


def downgrade() -> None:
    bind = op.get_bind()
    tagged = bind.execute(
        sa.text("SELECT count(*) FROM reference_technique WHERE " + _in("facet", _ADDED))  # noqa: S608 - constant enum values
    ).scalar_one()
    if tagged:
        raise RuntimeError(
            f"{tagged} reference(s) are tagged with Visual Knowledge facets; downgrading "
            "would erase a person's tagging. Remove those tags deliberately first."
        )
    op.drop_constraint(op.f(_NAME), "reference_technique", type_="check")
    op.create_check_constraint(op.f(_NAME), "reference_technique", _in("facet", _BEFORE))
