"""The paid-generation budget, recurring props and curated training manifests.

Three independent additions, all additive:

* ``spend_budget`` / ``spend_entry`` - the hard cap on paid generation and the
  reservations that enforce it;
* ``project_prop`` / ``project_prop_reference`` - recurring objects whose size
  must not drift between panels;
* ``training_dataset`` / ``training_dataset_item`` / ``training_run`` - exact,
  hashed training manifests and the runs over them.

Downgrade drops them. It refuses first if any of them holds rows, because a
settled charge, an approved prop lock or a locked training manifest is a
record of something that happened.

Revision ID: 0019_paid_budget_props_training
Revises: 0018_vk_page_analysis
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_paid_budget_props_training"
down_revision = "0018_vk_page_analysis"
branch_labels = None
depends_on = None

_TABLES = (
    "spend_entry",
    "spend_budget",
    "project_prop_reference",
    "project_prop",
    "training_run",
    "training_dataset_item",
    "training_dataset",
)


def upgrade() -> None:
    op.create_table(
        "spend_budget",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scope_key", sa.String(80), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("limit_micros", sa.BigInteger(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("scope_key", name="uq_spend_budget_scope_key"),
        sa.CheckConstraint("limit_micros >= 0", name="budget_limit_non_negative"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="budget_currency_code"),
    )
    op.create_table(
        "spend_entry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("budget_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(10), nullable=False, server_default="RESERVED"),
        sa.Column("provider_id", sa.String(80), nullable=False),
        sa.Column("model_ref", sa.String(200), nullable=False, server_default=""),
        sa.Column("purpose", sa.String(40), nullable=False, server_default=""),
        sa.Column("images", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("batch", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("estimated_micros", sa.BigInteger(), nullable=False),
        sa.Column("actual_micros", sa.BigInteger(), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subject", sa.String(160), nullable=False, server_default=""),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["budget_id"], ["spend_budget.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "state IN ('RESERVED', 'SETTLED', 'RELEASED')", name="spend_entry_state"
        ),
        sa.CheckConstraint("estimated_micros >= 0", name="spend_estimate_non_negative"),
        sa.CheckConstraint(
            "actual_micros IS NULL OR actual_micros >= 0", name="spend_actual_non_negative"
        ),
        sa.CheckConstraint("images > 0", name="spend_images_positive"),
        sa.CheckConstraint(
            "(state = 'SETTLED') = (actual_micros IS NOT NULL AND settled_at IS NOT NULL)",
            name="settled_entry_has_actual_cost",
        ),
    )
    op.create_index("ix_spend_entry_budget_state", "spend_entry", ["budget_id", "state"])
    op.create_index("ix_spend_entry_subject", "spend_entry", ["subject"])

    op.create_table(
        "project_prop",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_key", sa.String(80), nullable=False),
        sa.Column("prop_key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("character_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("size", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("body_scale", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("narrative_role", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(12), nullable=False, server_default="DRAFT"),
        sa.Column("approved_by", sa.String(200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["character_id"], ["character_profile.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("project_key", "prop_key", name="uq_project_prop_project_key_prop_key"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'RETIRED')", name="project_prop_status"
        ),
        sa.CheckConstraint(
            "prop_key ~ '^[a-z0-9][a-z0-9-]{0,79}$'", name="project_prop_key_format"
        ),
        sa.CheckConstraint("project_key ~ '^[a-z0-9][a-z0-9-]{0,79}$'", name="prop_project_key"),
        sa.CheckConstraint(
            "(status = 'APPROVED') = (approved_at IS NOT NULL AND approved_by IS NOT NULL)",
            name="approved_prop_has_human",
        ),
    )
    op.create_index("ix_project_prop_character", "project_prop", ["project_key", "character_id"])
    op.create_table(
        "project_prop_reference",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prop_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("view", sa.String(16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["prop_id"], ["project_prop.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reference_id"], ["reference_item.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "prop_id",
            "reference_id",
            "view",
            name="uq_project_prop_reference_prop_id_reference_id_view",
        ),
        sa.CheckConstraint(
            "view IN ('FRONT', 'PROFILE', 'DETAIL', 'IN_CONTEXT', 'SCALE')",
            name="prop_reference_view",
        ),
        sa.CheckConstraint("position >= 0", name="prop_reference_position"),
    )
    op.create_index(
        "ix_project_prop_reference_prop", "project_prop_reference", ["prop_id", "position"]
    )

    op.create_table(
        "training_dataset",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_key", sa.String(80), nullable=False),
        sa.Column("dataset_key", sa.String(80), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("state", sa.String(10), nullable=False, server_default="DRAFT"),
        sa.Column("recipe", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("split", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("purpose_tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("counts", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("manifest_hash", sa.String(64), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(200), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "project_key",
            "dataset_key",
            "version",
            name="uq_training_dataset_project_key_dataset_key_version",
        ),
        sa.CheckConstraint("version > 0", name="dataset_version_positive"),
        sa.CheckConstraint(
            "kind IN ('STYLE', 'STRUCTURE', 'SUBJECT')", name="training_dataset_kind"
        ),
        sa.CheckConstraint(
            "state IN ('DRAFT', 'LOCKED', 'RETIRED')", name="training_dataset_state"
        ),
        sa.CheckConstraint(
            "manifest_hash IS NULL OR manifest_hash ~ '^[0-9a-f]{64}$'", name="dataset_hash"
        ),
        sa.CheckConstraint(
            "(state = 'DRAFT') = (manifest_hash IS NULL AND locked_at IS NULL "
            "AND locked_by IS NULL)",
            name="locked_dataset_is_hashed_and_human",
        ),
    )
    op.create_index(
        "ix_training_dataset_project",
        "training_dataset",
        ["project_key", "dataset_key", "version"],
    )
    op.create_table(
        "training_dataset_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_kind", sa.String(20), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("locator", sa.String(500), nullable=False),
        sa.Column("crop", postgresql.JSONB(), nullable=True),
        sa.Column("item_key", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("caption", sa.Text(), nullable=False, server_default=""),
        sa.Column("purpose_tags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("split", sa.String(12), nullable=False, server_default="TRAIN"),
        sa.Column("rights_status", sa.String(24), nullable=False),
        sa.Column("training_eligibility", sa.String(24), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["training_dataset.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reference_id"], ["reference_item.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["external_resource_id"], ["external_resource.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "dataset_id", "item_key", name="uq_training_dataset_item_dataset_id_item_key"
        ),
        sa.CheckConstraint(
            "source_kind IN ('REFERENCE', 'EXTERNAL_RESOURCE')", name="dataset_item_source"
        ),
        sa.CheckConstraint("split IN ('TRAIN', 'VALIDATION')", name="dataset_item_split"),
        sa.CheckConstraint("item_key ~ '^[0-9a-f]{64}$'", name="dataset_item_key_is_sha256"),
        sa.CheckConstraint(
            "content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'", name="dataset_item_hash"
        ),
        sa.CheckConstraint(
            "(source_kind = 'REFERENCE') = (reference_id IS NOT NULL)",
            name="dataset_item_names_its_source",
        ),
    )
    op.create_index(
        "ix_training_dataset_item_dataset",
        "training_dataset_item",
        ["dataset_id", "split", "position"],
    )
    op.create_table(
        "training_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_key", sa.String(80), nullable=False),
        sa.Column("label", sa.String(200), nullable=False, server_default=""),
        sa.Column("base_model_ref", sa.String(200), nullable=False),
        sa.Column("adapter_kind", sa.String(20), nullable=False, server_default="LORA"),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("config_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(12), nullable=False, server_default="PLANNED"),
        sa.Column("output", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["training_dataset.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "state IN ('PLANNED', 'PREPARED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="training_run_state",
        ),
        sa.CheckConstraint("config_hash ~ '^[0-9a-f]{64}$'", name="training_config_hash"),
    )
    op.create_index("ix_training_run_dataset", "training_run", ["dataset_id", "created_at"])


def downgrade() -> None:
    connection = op.get_bind()
    held = [
        table
        for table in _TABLES
        if connection.exec_driver_sql(f"SELECT 1 FROM {table} LIMIT 1").first() is not None
    ]
    if held:
        raise RuntimeError(
            "Refusing to drop tables that hold records of what happened: "
            + ", ".join(sorted(held))
            + ". Export or delete those rows deliberately first."
        )
    op.drop_index("ix_training_run_dataset", table_name="training_run")
    op.drop_table("training_run")
    op.drop_index("ix_training_dataset_item_dataset", table_name="training_dataset_item")
    op.drop_table("training_dataset_item")
    op.drop_index("ix_training_dataset_project", table_name="training_dataset")
    op.drop_table("training_dataset")
    op.drop_index("ix_project_prop_reference_prop", table_name="project_prop_reference")
    op.drop_table("project_prop_reference")
    op.drop_index("ix_project_prop_character", table_name="project_prop")
    op.drop_table("project_prop")
    op.drop_index("ix_spend_entry_subject", table_name="spend_entry")
    op.drop_index("ix_spend_entry_budget_state", table_name="spend_entry")
    op.drop_table("spend_entry")
    op.drop_table("spend_budget")
