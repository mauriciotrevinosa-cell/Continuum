"""Job and worker domain enumerations (ADR-0002 sections 3-6).

These live in ``continuum_core`` rather than ``continuum_db`` because they are
domain primitives, not persistence concerns: the provider policy needs
``BlockedReason`` to explain why work cannot proceed, and it must not depend
on the database package to say so. ``continuum_db`` maps them to columns.

Stored as VARCHAR with a CHECK constraint rather than a native PostgreSQL
ENUM type: adding a value to a native enum requires a migration that cannot
run inside a transaction on older servers, and Phase 9+ will certainly add
blocked reasons. The CHECK constraint gives the same integrity with an
ordinary ALTER.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "TERMINAL_STATUSES",
    "BlockedReason",
    "JobEventType",
    "JobStatus",
    "StepStatus",
]


class JobStatus(StrEnum):
    """The durable job lifecycle.

    ``CANCELLING`` is present because cancelling a running step is
    asynchronous exactly as pausing is (F-23). Without it the UI would
    either lie about cancellation or the implementation would hard-kill the
    worker mid-unit.
    """

    QUEUED = "QUEUED"
    BLOCKED = "BLOCKED"
    RUNNING = "RUNNING"
    PAUSING = "PAUSING"
    PAUSED = "PAUSED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"


#: Statuses from which no further transition is possible.
TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.FAILED_FINAL, JobStatus.CANCELLED}
)


class BlockedReason(StrEnum):
    """Why a job is blocked (F-24).

    ``BLOCKED`` alone is useless to the user: the remediation for a missing
    model is completely different from the remediation for an unmet
    dependency. ``AWAITING_APPROVAL`` is reserved now for the Phase 6+
    approval gates of Master Plan section 103, so adding them needs no
    migration.
    """

    DEPENDENCY = "DEPENDENCY"
    MISSING_PROVIDER = "MISSING_PROVIDER"
    MISSING_MODEL = "MISSING_MODEL"
    MISSING_SOURCE_ASSET = "MISSING_SOURCE_ASSET"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"


class StepStatus(StrEnum):
    """State of one durable unit of work."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class JobEventType(StrEnum):
    """Append-only audit event kinds (ADR-0002 section 11)."""

    CREATED = "CREATED"
    TRANSITION = "TRANSITION"
    LEASE_ACQUIRED = "LEASE_ACQUIRED"
    LEASE_RENEWED = "LEASE_RENEWED"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    CHECKPOINT = "CHECKPOINT"
    STEP_STARTED = "STEP_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    STEP_FAILED = "STEP_FAILED"
    ERROR = "ERROR"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    BLOCKED = "BLOCKED"
    PROGRESS = "PROGRESS"
