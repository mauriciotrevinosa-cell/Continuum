"""Invariant - the guarded job transition table (F-28, F-23).

Pure logic, no database. These run everywhere, including the audit
environment, and they are what stops a future change from quietly making an
illegal transition legal.
"""

from __future__ import annotations

import itertools

import pytest
from continuum_core import IllegalTransitionError
from continuum_db.enums import TERMINAL_STATUSES, JobStatus
from continuum_jobs import ALLOWED_TRANSITIONS, assert_transition, can_transition, is_terminal
from continuum_jobs.states import next_backoff_seconds


class TestTableShape:
    def test_every_status_has_an_entry(self) -> None:
        assert set(ALLOWED_TRANSITIONS) == set(JobStatus)

    def test_cancelling_exists(self) -> None:
        """F-23: cancelling a running step is asynchronous exactly as pausing
        is. Without this state the UI lies or the worker is hard-killed."""
        assert JobStatus.CANCELLING in JobStatus
        assert can_transition(JobStatus.RUNNING, JobStatus.CANCELLING)
        assert can_transition(JobStatus.CANCELLING, JobStatus.CANCELLED)

    def test_terminal_statuses_have_no_outgoing_edges(self) -> None:
        for status in TERMINAL_STATUSES:
            assert ALLOWED_TRANSITIONS[status] == frozenset(), (
                f"{status.value} is terminal but has outgoing transitions"
            )
            assert is_terminal(status)

    def test_failed_retryable_is_not_terminal(self) -> None:
        """It is a scheduling state: run_after governs the next attempt."""
        assert JobStatus.FAILED_RETRYABLE not in TERMINAL_STATUSES
        assert can_transition(JobStatus.FAILED_RETRYABLE, JobStatus.QUEUED)

    def test_running_can_return_to_queued_for_lease_expiry(self) -> None:
        """F-27: without this edge, a hard-killed worker strands the job in
        RUNNING forever and the reaper has nowhere to put it."""
        assert can_transition(JobStatus.RUNNING, JobStatus.QUEUED)

    def test_no_status_transitions_to_itself(self) -> None:
        for status, targets in ALLOWED_TRANSITIONS.items():
            assert status not in targets, f"{status.value} -> itself is not a transition"


class TestIllegalTransitionsRaise:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (JobStatus.SUCCEEDED, JobStatus.RUNNING),
            (JobStatus.SUCCEEDED, JobStatus.PAUSED),
            (JobStatus.CANCELLED, JobStatus.QUEUED),
            (JobStatus.FAILED_FINAL, JobStatus.QUEUED),
            (JobStatus.QUEUED, JobStatus.SUCCEEDED),
            (JobStatus.PAUSED, JobStatus.SUCCEEDED),
            (JobStatus.BLOCKED, JobStatus.RUNNING),
        ],
    )
    def test_raises_rather_than_silently_no_op(self, current: JobStatus, target: JobStatus) -> None:
        """A silent no-op is how a job ends up in a state nobody can explain."""
        assert not can_transition(current, target)
        with pytest.raises(IllegalTransitionError):
            assert_transition(current, target)

    def test_error_names_the_permitted_transitions(self) -> None:
        with pytest.raises(IllegalTransitionError) as excinfo:
            assert_transition(JobStatus.QUEUED, JobStatus.SUCCEEDED)
        message = excinfo.value.remediation or ""
        assert "RUNNING" in message

    def test_terminal_error_explains_finality(self) -> None:
        with pytest.raises(IllegalTransitionError) as excinfo:
            assert_transition(JobStatus.SUCCEEDED, JobStatus.QUEUED)
        assert "Terminal" in (excinfo.value.remediation or "")


class TestLegalPaths:
    @pytest.mark.parametrize(
        "path",
        [
            [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCEEDED],
            [
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.PAUSING,
                JobStatus.PAUSED,
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.SUCCEEDED,
            ],
            [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.CANCELLING, JobStatus.CANCELLED],
            [
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.FAILED_RETRYABLE,
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.FAILED_FINAL,
            ],
            [
                JobStatus.QUEUED,
                JobStatus.BLOCKED,
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.SUCCEEDED,
            ],
            # Lease expiry mid-run, then a clean retry.
            [
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.SUCCEEDED,
            ],
        ],
    )
    def test_realistic_lifecycle_is_permitted(self, path: list[JobStatus]) -> None:
        for current, target in itertools.pairwise(path):
            assert_transition(current, target)


class TestBackoff:
    def test_no_delay_before_the_first_attempt(self) -> None:
        assert next_backoff_seconds(0) == 0.0

    def test_delay_is_bounded_and_jittered(self) -> None:
        """Full jitter, not fixed exponential: several workers retrying the
        same dead dependency must not synchronise into a thundering herd."""
        samples = [next_backoff_seconds(4) for _ in range(200)]
        assert all(0.0 <= s <= 16.0 for s in samples)
        assert len(set(samples)) > 1, "backoff is not jittered"

    def test_delay_is_capped(self) -> None:
        assert all(next_backoff_seconds(50) <= 300.0 for _ in range(50))
