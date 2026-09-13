"""The six Phase 0 tables (ADR-0006 section 3).

``job``, ``job_step``, ``job_checkpoint``, ``job_dependency``, ``job_event``
and ``worker``. Nothing else. No franchise, asset, character, canon,
project, branch, artifact, visual or provider table exists in Phase 0, and
``tests/invariants/test_phase0_schema.py`` asserts that.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import uuid7
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SaEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from continuum_db.enums import BlockedReason, JobEventType, JobStatus, StepStatus
from continuum_db.models.base import Base, TimestampTz, UuidV7

__all__ = ["Job", "JobCheckpoint", "JobDependency", "JobEvent", "JobStep", "Worker"]


def _enum(python_enum: type, name: str) -> SaEnum:
    """VARCHAR + CHECK rather than a native PostgreSQL ENUM (see enums.py)."""
    return SaEnum(python_enum, name=name, native_enum=False, length=32, validate_strings=True)


class Job(Base):
    """One durable unit of long-running work."""

    __tablename__ = "job"
    __table_args__ = (
        # Only ONE active job may exist per dedupe key (F-26). Double-clicking
        # "Scan" must yield one job, not a race between two scanners.
        Index(
            "uq_job_dedupe_key_active",
            "dedupe_key",
            unique=True,
            postgresql_where="status NOT IN ('SUCCEEDED','FAILED_FINAL','CANCELLED')",
        ),
        # The claim query's access path: status + run_after + priority.
        Index("ix_job_claim", "status", "run_after", "priority", "created_at"),
        Index("ix_job_lease_expiry", "status", "lease_expires_at"),
        CheckConstraint("units_done >= 0", name="units_done_non_negative"),
        CheckConstraint("units_total IS NULL OR units_total >= 0", name="units_total_non_negative"),
        CheckConstraint("attempt >= 0", name="attempt_non_negative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        # A blocked job must say why, and a non-blocked job must not pretend to.
        CheckConstraint(
            "(status = 'BLOCKED') = (blocked_reason IS NOT NULL)",
            name="blocked_reason_iff_blocked",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    job_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"), nullable=False, default=JobStatus.QUEUED
    )
    blocked_reason: Mapped[BlockedReason | None] = mapped_column(
        _enum(BlockedReason, "blocked_reason"), nullable=True
    )
    remediation: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Which pool of concurrency this job consumes (F-30). The field exists in
    #: Phase 0 even though the limiter is naive, because "one GPU job at a
    #: time, eight hashing jobs" is inevitable and adding it later is a
    #: schema change plus a scheduler rewrite.
    resource_class: Mapped[str] = mapped_column(String(32), nullable=False, default="cpu")

    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recipe_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    #: Propagated request -> job -> step -> provider call (F-71). Stored on
    #: the row because a ContextVar cannot cross a process boundary.
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    units_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    units_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)

    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    #: Without this, FAILED_RETRYABLE has no scheduling semantics and a
    #: permanently-failing job spins at full speed against a dead provider (F-25).
    run_after: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )

    #: Requests are FLAGS, never direct status writes (F-28). This removes the
    #: race where the UI writes PAUSED while the worker writes SUCCEEDED.
    pause_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    #: Lease + heartbeat, so a hard-killed worker's job is recoverable rather
    #: than stuck in RUNNING forever (F-27).
    lease_owner: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("worker.id", ondelete="SET NULL"), nullable=True
    )
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    elapsed_active_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: A plain string, deliberately NOT a HardwareExecutionProfile entity
    #: (F-60): telemetry can be partitioned later without a migration.
    hardware_signature: Mapped[str | None] = mapped_column(String(128), nullable=True)

    last_error: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)

    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    steps: Mapped[list[JobStep]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )
    checkpoints: Mapped[list[JobCheckpoint]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="noload"
    )

    @property
    def is_terminal(self) -> bool:
        from continuum_db.enums import TERMINAL_STATUSES

        return self.status in TERMINAL_STATUSES


class JobStep(Base):
    """One durable, idempotent unit of a job (F-29).

    A single mechanism covers both checkpoint patterns: unordered sets use
    ``unit_key`` alone, ordered streams additionally set ``ordinal`` and
    resume from the highest completed one. Implementing two mechanisms is
    what this design avoids.
    """

    __tablename__ = "job_step"
    __table_args__ = (
        UniqueConstraint("job_id", "unit_key", name="job_id_unit_key"),
        Index("ix_job_step_job_status", "job_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("job.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_key: Mapped[str] = mapped_column(String(255), nullable=False)
    ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[StepStatus] = mapped_column(
        _enum(StepStatus, "step_status"), nullable=False, default=StepStatus.PENDING
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    last_error: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    completed_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    job: Mapped[Job] = relationship(back_populates="steps")


class JobCheckpoint(Base):
    """Handler-specific resume state. Latest wins; a short history is kept."""

    __tablename__ = "job_checkpoint"
    __table_args__ = (
        UniqueConstraint("job_id", "seq", name="job_id_seq"),
        Index("ix_job_checkpoint_latest", "job_id", "seq"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("job.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    locator: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="checkpoints")


class JobDependency(Base):
    """DAG edge. A failed dependency BLOCKS dependents; it never cancels them.

    Automatic cascade cancellation would silently destroy queued work the
    user may still want, so the decision stays with the user (ADR-0002 s.9).
    """

    __tablename__ = "job_dependency"
    __table_args__ = (CheckConstraint("job_id <> depends_on_job_id", name="no_self_dependency"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("job.id", ondelete="CASCADE"), primary_key=True
    )
    depends_on_job_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("job.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="completion")


class JobEvent(Base):
    """Append-only audit of everything that happened to a job.

    This is what makes "incomplete error state / retry recording" checkable
    rather than a judgement call, and it is the only practical way to debug a
    failed six-hour job after the fact.
    """

    __tablename__ = "job_event"
    __table_args__ = (Index("ix_job_event_job_created", "job_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("job.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[JobEventType] = mapped_column(
        _enum(JobEventType, "job_event_type"), nullable=False
    )
    from_status: Mapped[JobStatus | None] = mapped_column(
        _enum(JobStatus, "job_status_from"), nullable=True
    )
    to_status: Mapped[JobStatus | None] = mapped_column(
        _enum(JobStatus, "job_status_to"), nullable=True
    )
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    worker_id: Mapped[uuid.UUID | None] = mapped_column(UuidV7(), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )


class Worker(Base):
    """A running worker process.

    Exists for two reasons beyond observability: it gives the lease reaper an
    auditable owner, and ``drain_requested`` is the portable graceful-stop
    channel (F-31). Windows has no real SIGTERM, so a signal-only design
    would be untested on the platform this project actually runs on.
    """

    __tablename__ = "worker"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    resource_classes: Mapped[str] = mapped_column(String(255), nullable=False, default="cpu")
    hardware_signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    last_heartbeat_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    drain_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    stopped_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    @property
    def is_alive(self) -> bool:
        return self.stopped_at is None
