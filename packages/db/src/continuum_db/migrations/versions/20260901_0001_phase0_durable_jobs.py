"""Phase 0 foundation: pgvector extension and the six durable job tables.

Revision ID: 0001_phase0
Revises:
Create Date: 2026-09-01

The pgvector extension is created here only to prove the database
environment is the one Continuum expects (ADR-0006 section 3). **No column
in Phase 0 uses a vector type.** Embeddings arrive in Phase 3, as
model-versioned rows in their own table (F-47), never as a column on a
segment.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase0"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JOB_STATUSES = (
    "QUEUED",
    "BLOCKED",
    "RUNNING",
    "PAUSING",
    "PAUSED",
    "CANCELLING",
    "CANCELLED",
    "SUCCEEDED",
    "FAILED_RETRYABLE",
    "FAILED_FINAL",
)
BLOCKED_REASONS = (
    "DEPENDENCY",
    "MISSING_PROVIDER",
    "MISSING_MODEL",
    "MISSING_SOURCE_ASSET",
    "AWAITING_APPROVAL",
    "RESOURCE_UNAVAILABLE",
)
STEP_STATUSES = ("PENDING", "RUNNING", "SUCCEEDED", "FAILED")
JOB_EVENT_TYPES = (
    "CREATED",
    "TRANSITION",
    "LEASE_ACQUIRED",
    "LEASE_RENEWED",
    "LEASE_EXPIRED",
    "CHECKPOINT",
    "STEP_STARTED",
    "STEP_COMPLETED",
    "STEP_FAILED",
    "ERROR",
    "PAUSE_REQUESTED",
    "CANCEL_REQUESTED",
    "BLOCKED",
    "PROGRESS",
)

TERMINAL = "'SUCCEEDED','FAILED_FINAL','CANCELLED'"


def _enum(values: Sequence[str], name: str) -> sa.Enum:
    """VARCHAR + CHECK, not a native PostgreSQL ENUM.

    Adding a value to a native enum needs a migration that cannot run inside
    a transaction on older servers, and later phases will certainly add
    blocked reasons and event types.
    """
    return sa.Enum(*values, name=name, native_enum=False, length=32, create_constraint=True)


def upgrade() -> None:
    # Proves the database image is pgvector-enabled. No vector column exists
    # in Phase 0.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "worker",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column("resource_classes", sa.String(length=255), nullable=False),
        sa.Column("hardware_signature", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("drain_requested", sa.Boolean(), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker")),
    )

    op.create_table(
        "job",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(length=128), nullable=False),
        sa.Column("status", _enum(JOB_STATUSES, "job_status"), nullable=False),
        sa.Column("blocked_reason", _enum(BLOCKED_REASONS, "blocked_reason"), nullable=True),
        sa.Column("remediation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("resource_class", sa.String(length=32), nullable=False),
        sa.Column("dedupe_key", sa.String(length=128), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("recipe_version", sa.String(length=64), nullable=True),
        sa.Column("provider_ref", sa.String(length=128), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("units_done", sa.Integer(), nullable=False),
        sa.Column("units_total", sa.Integer(), nullable=True),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("total_steps", sa.Integer(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("pause_requested", sa.Boolean(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("lease_owner", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elapsed_active_ms", sa.BigInteger(), nullable=False),
        sa.Column("hardware_signature", sa.String(length=128), nullable=True),
        sa.Column("last_error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_history", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("units_done >= 0", name=op.f("ck_job_units_done_non_negative")),
        sa.CheckConstraint(
            "units_total IS NULL OR units_total >= 0",
            name=op.f("ck_job_units_total_non_negative"),
        ),
        sa.CheckConstraint("attempt >= 0", name=op.f("ck_job_attempt_non_negative")),
        sa.CheckConstraint("max_attempts >= 1", name=op.f("ck_job_max_attempts_positive")),
        sa.CheckConstraint(
            "(status = 'BLOCKED') = (blocked_reason IS NOT NULL)",
            name=op.f("ck_job_blocked_reason_iff_blocked"),
        ),
        sa.ForeignKeyConstraint(
            ["lease_owner"],
            ["worker.id"],
            name=op.f("fk_job_lease_owner_worker"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job")),
    )
    # Partial unique index: only ONE non-terminal job per dedupe key (F-26).
    op.create_index(
        "uq_job_dedupe_key_active",
        "job",
        ["dedupe_key"],
        unique=True,
        postgresql_where=sa.text(f"status NOT IN ({TERMINAL})"),
    )
    op.create_index("ix_job_claim", "job", ["status", "run_after", "priority", "created_at"])
    op.create_index("ix_job_lease_expiry", "job", ["status", "lease_expires_at"])

    op.create_table(
        "job_step",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("unit_key", sa.String(length=255), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=True),
        sa.Column("status", _enum(STEP_STATUSES, "step_status"), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"], ["job.id"], name=op.f("fk_job_step_job_id_job"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_step")),
        # The idempotency boundary: one row per (job, unit).
        sa.UniqueConstraint("job_id", "unit_key", name=op.f("uq_job_step_job_id_unit_key")),
    )
    op.create_index("ix_job_step_job_id", "job_step", ["job_id"])
    op.create_index("ix_job_step_job_status", "job_step", ["job_id", "status"])

    op.create_table(
        "job_checkpoint",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("locator", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"], ["job.id"], name=op.f("fk_job_checkpoint_job_id_job"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_checkpoint")),
        sa.UniqueConstraint("job_id", "seq", name=op.f("uq_job_checkpoint_job_id_seq")),
    )
    op.create_index("ix_job_checkpoint_job_id", "job_checkpoint", ["job_id"])
    op.create_index("ix_job_checkpoint_latest", "job_checkpoint", ["job_id", "seq"])

    op.create_table(
        "job_dependency",
        sa.Column("job_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("depends_on_job_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "job_id <> depends_on_job_id", name=op.f("ck_job_dependency_no_self_dependency")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["job.id"], name=op.f("fk_job_dependency_job_id_job"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["depends_on_job_id"],
            ["job.id"],
            name=op.f("fk_job_dependency_depends_on_job_id_job"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("job_id", "depends_on_job_id", name=op.f("pk_job_dependency")),
    )

    op.create_table(
        "job_event",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("event_type", _enum(JOB_EVENT_TYPES, "job_event_type"), nullable=False),
        sa.Column("from_status", _enum(JOB_STATUSES, "job_status_from"), nullable=True),
        sa.Column("to_status", _enum(JOB_STATUSES, "job_status_to"), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("worker_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"], ["job.id"], name=op.f("fk_job_event_job_id_job"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_event")),
    )
    op.create_index("ix_job_event_job_id", "job_event", ["job_id"])
    op.create_index("ix_job_event_job_created", "job_event", ["job_id", "created_at"])


def downgrade() -> None:
    """Best-effort only; not a data-preservation guarantee (ADR-0003 s.15).

    The supported recovery path is restore-from-backup. Dropping these tables
    destroys all job history, which is why the policy is stated plainly
    rather than implying a reversibility the migration does not have.
    """
    op.drop_table("job_event")
    op.drop_table("job_dependency")
    op.drop_table("job_checkpoint")
    op.drop_table("job_step")
    op.drop_index("ix_job_lease_expiry", table_name="job")
    op.drop_index("ix_job_claim", table_name="job")
    op.drop_index("uq_job_dedupe_key_active", table_name="job")
    op.drop_table("job")
    op.drop_table("worker")
    # The extension is deliberately NOT dropped: another database user or
    # future phase may rely on it, and dropping it is not this migration's
    # to decide.
