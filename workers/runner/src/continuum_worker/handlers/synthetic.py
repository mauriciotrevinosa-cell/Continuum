"""The two Phase 0 synthetic handlers (ADR-0006 section 4).

Neither touches real media. They exist to make the durability invariants
testable *before* anything valuable depends on them -- which is the whole
reason the job system is built first. Fault injection against a user's real
library would be unconscionable; against a synthetic job it is routine.
"""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from typing import ClassVar

from continuum_core import (
    BlockedReason,
    ContinuumError,
    ErrorCategory,
    content_hash_bytes,
)
from continuum_jobs import JobContext, UnitOutcome, UnitSpec
from continuum_observability import get_logger
from continuum_providers import Capability, DataClass

__all__ = ["BlockedCapabilityHandler", "CountedWorkHandler", "SyntheticBlockedError"]

log = get_logger("continuum.worker.synthetic")


class SyntheticRetryableError(ContinuumError):
    """Injected retryable failure."""

    code = "synthetic.injected_failure"
    category = ErrorCategory.RETRYABLE_TRANSIENT


class SyntheticPermanentError(ContinuumError):
    """Injected permanent failure."""

    code = "synthetic.injected_permanent_failure"
    category = ErrorCategory.PERMANENT_INPUT


class SyntheticBlockedError(ContinuumError):
    """Raised when no permitted provider can serve the requested capability."""

    code = "synthetic.capability_unavailable"
    category = ErrorCategory.PERMANENT_CONFIG


class CountedWorkHandler:
    """N deterministic units, each landing a content-addressed marker.

    Proves durable progress, effect idempotency, checkpoint/resume,
    pause/drain, retry and crash recovery (acceptance 110.6-110.11).

    **Why the effect is content-addressed:** the marker's destination is the
    SHA-256 of its own bytes, so re-running a completed unit rewrites the
    identical path with identical content and the store reports
    ``already_present``. That is what makes at-least-once execution behave as
    effectively-once (ADR-0002 section 2) -- not the checkpoint frequency.
    """

    job_type: ClassVar[str] = "synthetic.counted_work"

    #: Where markers land. /cache is disposable by definition (section 108).
    ROOT_KEY: ClassVar[str] = "cache"

    def plan(self, ctx: JobContext) -> Sequence[UnitSpec]:
        total = int(ctx.payload.get("units", 5))
        if total < 1:
            raise SyntheticPermanentError(
                "A counted-work job needs at least one unit.",
                technical_detail=f"units={total}",
            )
        # Deterministic keys: re-planning after a crash must produce exactly
        # the same set, or resume cannot recognise completed work.
        return [UnitSpec(unit_key=f"unit-{i:05d}", ordinal=i) for i in range(total)]

    def execute_unit(self, ctx: JobContext, unit: UnitSpec) -> UnitOutcome:
        payload = ctx.payload
        index = unit.ordinal if unit.ordinal is not None else 0

        # -- fault injection, all opt-in via job payload -------------------
        fail_at = payload.get("fail_at_unit")
        fail_permanently_at = payload.get("fail_permanently_at_unit")
        die_at = payload.get("die_at_unit")

        if fail_permanently_at is not None and index == int(fail_permanently_at):
            raise SyntheticPermanentError(
                f"Injected permanent failure at {unit.unit_key}.",
                technical_detail=f"unit_index={index}",
                remediation="This job cannot succeed as configured.",
            )

        if fail_at is not None and index == int(fail_at):
            attempts_before_success = int(payload.get("fail_times", 1))
            step_attempt = self._attempt_for(ctx, unit)
            if step_attempt <= attempts_before_success:
                raise SyntheticRetryableError(
                    f"Injected retryable failure at {unit.unit_key}.",
                    technical_detail=f"attempt={step_attempt}",
                    remediation="It will be retried automatically with backoff.",
                )

        delay_ms = int(payload.get("unit_delay_ms", 0))
        if delay_ms:
            time.sleep(delay_ms / 1000.0)

        # -- the effect: a content-addressed write -------------------------
        body = self._marker_bytes(ctx, unit)
        digest = content_hash_bytes(body)

        already_present = False
        if ctx.derived is not None:
            stored = ctx.derived.put_bytes(self.ROOT_KEY, body)
            already_present = stored.already_present
            digest = stored.content_hash

        if die_at is not None and index == int(die_at) and not already_present:
            # Die after the durable effect lands but before the completion
            # row/checkpoint transaction. On recovery the same write reports
            # already_present, proving that this at-least-once window is safe.
            log.warning("synthetic hard death after effect", extra={"unit": unit.unit_key})
            os._exit(137)

        return UnitOutcome(
            result={
                "content_hash": digest,
                "already_present": already_present,
                "unit_index": index,
            },
            checkpoint={"last_unit_key": unit.unit_key, "last_unit_index": index},
        )

    def _marker_bytes(self, ctx: JobContext, unit: UnitSpec) -> bytes:
        """Deterministic content: identical input yields identical bytes.

        Deliberately contains no timestamp, no random value and no attempt
        counter. If it did, a re-run would produce a different hash, land a
        second file, and the idempotency property would be a lie.
        """
        marker = ctx.payload.get("marker", "default")
        return (
            "continuum-synthetic-unit\n"
            f"job_type={self.job_type}\n"
            f"marker={marker}\n"
            f"unit={unit.unit_key}\n"
        ).encode()

    @staticmethod
    def _attempt_for(ctx: JobContext, unit: UnitSpec) -> int:
        from continuum_db.models import JobStep
        from sqlalchemy import select

        return int(
            ctx.session.execute(
                select(JobStep.attempt).where(
                    JobStep.job_id == ctx.job_id, JobStep.unit_key == unit.unit_key
                )
            ).scalar_one_or_none()
            or 1
        )


class BlockedCapabilityHandler:
    """Requests a capability nothing satisfies, to prove the BLOCKED path.

    Acceptance 110.12: it must park with an actionable remediation rather
    than failing opaquely, and it must never silently reach for cloud or
    paid work (Master Plan section 103).
    """

    job_type: ClassVar[str] = "synthetic.blocked_capability"

    #: Nothing in the Phase 0 registry provides this.
    CAPABILITY: ClassVar[Capability] = Capability.VIDEO_GENERATE

    def plan(self, ctx: JobContext) -> Sequence[UnitSpec]:
        return [UnitSpec(unit_key="probe-capability", ordinal=0)]

    def execute_unit(self, ctx: JobContext, unit: UnitSpec) -> UnitOutcome:
        if ctx.providers is None:
            raise SyntheticBlockedError(
                "No provider registry is available to this worker.",
                technical_detail="ctx.providers is None",
            )

        decision = ctx.providers.evaluate(self.CAPABILITY, DataClass.SYNTHETIC)
        if decision.permitted:
            # A provider appeared. Phase 0 should have none for this.
            return UnitOutcome(result={"provider_id": decision.provider_id})

        reason = decision.blocked_reason or BlockedReason.MISSING_PROVIDER
        remediation = dict(decision.remediation or {})
        raise SyntheticBlockedError(
            str(remediation.get("message", "No permitted provider.")),
            technical_detail=f"capability={self.CAPABILITY.value}",
            remediation=str(remediation.get("action", "")),
            blocked_reason=reason.value,
        )
