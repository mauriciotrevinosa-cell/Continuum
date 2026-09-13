"""The guarded job transition table (ADR-0002 sections 3-4).

Only the worker and the lease reaper write ``status``, and only through
:func:`assert_transition`. Illegal transitions **raise**; they never silently
no-op, because a silent no-op is how a job ends up in a state nobody can
explain three hours into a render.

Pause and cancel are *requests* (flags on the row), never status writes. That
removes the entire class of race the audit checklist looks for: the UI
writing ``PAUSED`` while the worker concurrently writes ``SUCCEEDED``.

This module is pure logic with no database dependency, so the table itself is
testable without PostgreSQL.
"""

from __future__ import annotations

from continuum_core import IllegalTransitionError
from continuum_db.enums import TERMINAL_STATUSES, JobStatus

__all__ = [
    "ALLOWED_TRANSITIONS",
    "assert_transition",
    "can_transition",
    "is_terminal",
    "next_backoff_seconds",
]

S = JobStatus

#: from -> allowed destinations.
ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    S.QUEUED: frozenset({S.RUNNING, S.BLOCKED, S.CANCELLED, S.PAUSED, S.FAILED_FINAL}),
    # BLOCKED returns to QUEUED once the dependency, provider, model or
    # approval that blocked it becomes available.
    S.BLOCKED: frozenset({S.QUEUED, S.CANCELLED, S.FAILED_FINAL}),
    S.RUNNING: frozenset(
        {
            S.SUCCEEDED,
            S.FAILED_RETRYABLE,
            S.FAILED_FINAL,
            S.PAUSING,
            S.CANCELLING,
            S.BLOCKED,
            # Lease expiry: the reaper returns a job whose worker died to the
            # queue. Without this edge a hard-killed worker strands the job in
            # RUNNING forever (F-27).
            S.QUEUED,
        }
    ),
    # PAUSING and CANCELLING are the asynchronous halves of a cooperative
    # stop: the worker observes the flag between units, finishes the current
    # unit durably, and only then lands the terminal state.
    S.PAUSING: frozenset({S.PAUSED, S.SUCCEEDED, S.FAILED_RETRYABLE, S.FAILED_FINAL, S.CANCELLING}),
    S.PAUSED: frozenset({S.QUEUED, S.RUNNING, S.CANCELLED, S.FAILED_FINAL}),
    S.CANCELLING: frozenset({S.CANCELLED, S.SUCCEEDED, S.FAILED_FINAL}),
    # FAILED_RETRYABLE is not terminal: run_after schedules the next attempt.
    S.FAILED_RETRYABLE: frozenset({S.QUEUED, S.FAILED_FINAL, S.CANCELLED}),
    # Terminal.
    S.SUCCEEDED: frozenset(),
    S.FAILED_FINAL: frozenset(),
    S.CANCELLED: frozenset(),
}


def is_terminal(status: JobStatus) -> bool:
    return status in TERMINAL_STATUSES


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition(current: JobStatus, target: JobStatus, *, job_id: object = None) -> None:
    """Raise unless ``current -> target`` is permitted."""
    if can_transition(current, target):
        return
    allowed = sorted(s.value for s in ALLOWED_TRANSITIONS.get(current, frozenset()))
    raise IllegalTransitionError(
        f"Cannot move a job from {current.value} to {target.value}.",
        technical_detail=(
            f"job_id={job_id} current={current.value} target={target.value} allowed={allowed}"
        ),
        remediation=(
            "Terminal states are final; corrections are new jobs."
            if is_terminal(current)
            else f"Permitted transitions from {current.value}: {', '.join(allowed) or 'none'}"
        ),
    )


def next_backoff_seconds(attempt: int, *, base: float = 2.0, cap: float = 300.0) -> float:
    """Exponential backoff with full jitter (F-25).

    Full jitter rather than fixed exponential: several workers retrying the
    same failing dependency at the same instant would otherwise synchronise
    into a thundering herd.
    """
    import random

    if attempt <= 0:
        return 0.0
    exponential = min(cap, base**attempt)
    return random.uniform(0.0, exponential)  # noqa: S311 - jitter, not cryptography
