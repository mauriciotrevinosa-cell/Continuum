"""Production sheet kinds beyond head and body, and one approval per variant.

A character has one face and one body, but several outfits and several props,
and the manga translation of the character is its own question. The sheet kind
list grows and every attempt gains a ``variant_key`` naming which outfit or
prop it is about, so "one approved sheet" means one per variant rather than
one per character.

Downgrade narrows the list again and refuses if any row uses a new kind or a
variant, because dropping those would silently lose approved work.

Revision ID: 0020_production_sheet_variants
Revises: 0019_paid_budget_props_training
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_production_sheet_variants"
down_revision = "0019_paid_budget_props_training"
branch_labels = None
depends_on = None

_TABLE = "character_model_sheet_attempt"
_OLD_KINDS = ("HEAD", "FULL_BODY")
_NEW_UNIQUE = "uq_character_model_sheet_attempt_variant_attempt"
_NEW_KINDS = ("HEAD", "FULL_BODY", "MANGA_TRANSLATION", "OUTFIT", "ACCESSORY_SCALE")


def _kind_check(kinds: tuple[str, ...]) -> str:
    return "sheet_kind IN (" + ", ".join(f"'{kind}'" for kind in kinds) + ")"


def upgrade() -> None:
    op.alter_column(_TABLE, "sheet_kind", type_=sa.String(20), existing_nullable=False)
    op.add_column(
        _TABLE,
        sa.Column("variant_key", sa.String(80), nullable=False, server_default=""),
    )
    op.drop_constraint(
        "model_sheet_kind", _TABLE, type_="check"
    )
    op.create_check_constraint("model_sheet_kind", _TABLE, _kind_check(_NEW_KINDS))
    op.drop_constraint(
        f"uq_{_TABLE}_model_id_sheet_kind_attempt", _TABLE, type_="unique"
    )
    op.create_unique_constraint(
        _NEW_UNIQUE,
        _TABLE,
        ["model_id", "sheet_kind", "variant_key", "attempt"],
    )
    op.drop_index("uq_character_model_sheet_approved", table_name=_TABLE)
    op.create_index(
        "uq_character_model_sheet_approved",
        _TABLE,
        ["project_key", "character_id", "sheet_kind", "variant_key"],
        unique=True,
        postgresql_where=sa.text("status = 'APPROVED'"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    kept = connection.exec_driver_sql(
        f"SELECT 1 FROM {_TABLE} WHERE sheet_kind NOT IN "  # noqa: S608 - fixed table name
        "('HEAD', 'FULL_BODY') OR variant_key <> '' LIMIT 1"
    ).first()
    if kept is not None:
        raise RuntimeError(
            "Refusing to narrow the sheet kinds: approved or attempted sheets use a kind "
            "or a variant this revision cannot represent. Remove them deliberately first."
        )
    op.drop_index("uq_character_model_sheet_approved", table_name=_TABLE)
    op.create_index(
        "uq_character_model_sheet_approved",
        _TABLE,
        ["project_key", "character_id", "sheet_kind"],
        unique=True,
        postgresql_where=sa.text("status = 'APPROVED'"),
    )
    op.drop_constraint(
        _NEW_UNIQUE, _TABLE, type_="unique"
    )
    op.create_unique_constraint(
        f"uq_{_TABLE}_model_id_sheet_kind_attempt",
        _TABLE,
        ["model_id", "sheet_kind", "attempt"],
    )
    op.drop_constraint("model_sheet_kind", _TABLE, type_="check")
    op.create_check_constraint("model_sheet_kind", _TABLE, _kind_check(_OLD_KINDS))
    op.drop_column(_TABLE, "variant_key")
    op.alter_column(_TABLE, "sheet_kind", type_=sa.String(16), existing_nullable=False)
