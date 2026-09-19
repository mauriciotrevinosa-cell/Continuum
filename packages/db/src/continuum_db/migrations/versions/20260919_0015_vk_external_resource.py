"""M3 Visual Knowledge: the external-resource registry.

Revision ID: 0015_vk_external_resource
Revises: 0014_continue_controls
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_vk_external_resource"
down_revision: str | None = "0014_continue_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KINDS = ("DATASET", "ANNOTATIONS", "MODEL", "TOOL", "RESEARCH", "UNVERIFIED")
_ACCESS = ("OPEN", "NOT_REQUESTED", "REQUESTED", "GRANTED", "DENIED", "UNKNOWN")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.create_table(
        "external_resource",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("urls", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("license_summary", sa.Text(), nullable=False),
        sa.Column("access_state", sa.String(length=20), nullable=False),
        sa.Column("license_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("license_acceptance_note", sa.Text(), nullable=False),
        sa.Column("proposed_uses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("allowed_uses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("intake_root_key", sa.String(length=64), nullable=True),
        sa.Column("registry_entry", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("registry_hash", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "key ~ '^[a-z0-9][a-z0-9._-]{1,79}$'", name=op.f("ck_external_resource_key_format")
        ),
        sa.CheckConstraint(_in("kind", _KINDS), name=op.f("ck_external_resource_kind_known")),
        sa.CheckConstraint(
            _in("access_state", _ACCESS), name=op.f("ck_external_resource_access_known")
        ),
        sa.CheckConstraint(
            "intake_root_key IS NULL OR intake_root_key ~ '^intake:[a-z0-9-]{1,57}$'",
            name=op.f("ck_external_resource_intake_root_is_a_key"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(allowed_uses) = 'array' AND jsonb_typeof(proposed_uses) = 'array'",
            name=op.f("ck_external_resource_uses_are_lists"),
        ),
        sa.CheckConstraint(
            "NOT (proposed_uses ? 'TRAINING_APPROVED')",
            name=op.f("ck_external_resource_registry_never_approves_training"),
        ),
        sa.CheckConstraint(
            "NOT (allowed_uses ? 'TRAINING_APPROVED') OR (license_accepted_at IS NOT NULL"
            " AND access_state IN ('OPEN', 'GRANTED'))",
            name=op.f("ck_external_resource_training_needs_accepted_license"),
        ),
        sa.CheckConstraint(
            "registry_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_external_resource_registry_hash_is_sha256"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_resource")),
        sa.UniqueConstraint("key", name=op.f("uq_external_resource_key")),
    )


def downgrade() -> None:
    op.drop_table("external_resource")
