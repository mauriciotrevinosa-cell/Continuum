# Final Cold Phase 0 Audit: 4474ee5

## Verdict

**REJECT — DO NOT TAG**

Candidate `4474ee54268499b37debd664f5bf04f46fde8184` closes the previously
reported H-1 through H-7b cases, but two new deterministic PostgreSQL
reproductions expose unresolved ownership lifecycle defects. H-8 permits stale
step-start state to commit after actual lease expiry. H-9 lets a handler query
autoflush `STEP_STARTED` and hold a foreign-key-related lock that makes the
real reaper skip the expired job indefinitely while the handler transaction
remains open.

No production code or permanent test was modified. No merge or tag was made.

## Identity and independence

- Required workspace: `C:\Continuum-Claude-FinalAudit`
- Branch: `audit/claude-final-phase-0-4474ee5`
- Exact audited SHA: `4474ee54268499b37debd664f5bf04f46fde8184`
- Database: `continuum_claude_final_audit` on PostgreSQL at `127.0.0.1:5433`
- Data root: `C:/ContinuumData-Claude-FinalAudit`
- Platform: Windows, Python 3.12.10

Independence is reduced because the same model family participated in prior
fix implementation and this audit. All implementation claims were nevertheless
treated as untrusted; the new results come from separately constructed audit
artifacts and real PostgreSQL serialization.

The named audit worktree and database did not initially exist. The worktree
was created from the pinned remote audit branch, and only the named isolated
database was created. These were environment prerequisites, not candidate
code changes.

## Findings

### Critical

None.

### High

#### H-8: stale transaction timestamp authorizes expired step start

**DEFECT — code defect.**

`_stop_requested()` locks the job row at
`packages/jobs/src/continuum_jobs/execution.py:697-739` and then calls
`_lease_is_alive()`. That helper compares the deadline with `func.now()` at
lines 597-610. `_authorize_effect()` renews and verifies with the same
transaction-scoped `now()` at lines 614-668.

The audit transaction established `transaction_timestamp()` while A's
one-second lease was live and then blocked on another transaction's job-row
lock. After 1.5 seconds of actual database wall time, the blocker released.
The production pre-unit sequence observed:

```text
_stop_requested -> None
_authorize_effect -> True
```

It committed `JobStep.RUNNING` and `attempt = 1` although
`lease_expires_at < clock_timestamp()` immediately after commit. The separate
fresh `_owns_live_lease()` session correctly returned false, so the effect was
prevented, but it does not roll back the already committed stale step-start
mutation.

The root fix should obtain a fresh post-lock clock value, using
`clock_timestamp()` or beginning a new transaction after lock acquisition,
and use that same fresh authority for the lease check and renewal. Merely
adding another pre-effect probe does not repair durable step state already
committed.

#### H-9: handler-session autoflush prevents expired-lease recovery

**DEFECT — code defect.**

After the step-start commit, `record_event(STEP_STARTED)` is staged at
`packages/jobs/src/continuum_jobs/execution.py:307-310`. The handler receives
that same session. A harmless handler query triggers SQLAlchemy autoflush,
inserting the pending `JobEvent`. Its foreign key check acquires a lock related
to the job row and leaves the handler transaction open across the effect.

The deterministic artifact then made every heartbeat renewal fail until the
real `LeaseHeartbeat` declared ownership lost. After actual database time
passed the lease deadline, `reap_expired_leases()` returned `[]`; its
`FOR UPDATE SKIP LOCKED` query skipped the job locked by the handler
transaction. Once the handler was released, A stood down, but recovery had
been unavailable for the entire arbitrary handler wait.

This is not merely an idle read transaction or an `xmin` maintenance concern:
it changes reaper behavior for the target job. `STEP_STARTED` should be
committed atomically with the authorized step-start transaction, before the
handler receives the session. More generally, a handler must not inherit
pending coordination writes whose autoflush can lock the job for the duration
of an effect.

### Medium

None.

### Low

None.

## Prior hypotheses

| Hypothesis | Result | Evidence |
|---|---|---|
| H-1 stale finalization | CLEARED | Permanent ownership tests pass; completion and final transition re-lock and require owner. |
| H-2 exception after loss | CLEARED | Ownership dominates exceptions; stale failure state is withheld. |
| H-3 stale ORM transition | CLEARED | Transition locks/reloads and enforces owner for worker RUNNING transitions. |
| H-4 pre-unit step mutation | CLEARED for ordinary interleavings | Ownership lock spans normal authorization and step-start commit. H-8 identifies the transaction-time exception. |
| H-5 slow planning | CLEARED | Planning heartbeat and post-plan locked ownership proof pass. |
| H-5b planning loss/exception | CLEARED | Worker stands down without corrupting state or terminating continuation. |
| H-6 effect-start gap | CLEARED for expired-at-entry and normal reclaim | Permanent tests prevent an expired owner reaching the effect. The two historical artifacts that require that obsolete setup no longer reach their gate. H-8 remains a distinct lock-wait timestamp defect. |
| H-7 exception/BLOCKED after loss | CLEARED | Permanent real-worker paths pass. |
| H-7b unknown job type after loss | CLEARED | Permanent worker continuation and stale BLOCKED coverage pass. |
| C-1 renewal/reaper serialization | CLEARED | Lease concurrency tests pass, including two reapers and stale renewal behavior. |
| C-2 dependency mutation serialization | CLEARED | Advisory-lock concurrency tests pass and persisted graphs remain acyclic. |
| F-A deterministic ownership handover | CLEARED | Included in three repeated targeted runs with no intermittent failure. |

Normal worker continuation after ownership stand-down and legitimate
pause/cancel/drain paths passed in the permanent ownership coverage.

## Lease-model boundary

Phase 0 may accept the residual instruction boundary between the final fresh
lease probe and the first handler instruction. An arbitrarily suspended process
can always cross a lease deadline between two instructions. ADR-0002 explicitly
uses at-least-once execution plus content-addressed or deterministic-idempotent
effects to tolerate that residual. True fencing tokens are not required merely
to make this theoretical interval zero-width.

That accepted boundary does not excuse H-8 or H-9. H-8 commits stale durable
coordination state based on an old database timestamp. H-9 actively prevents
the reaper from performing the recovery promised by the lease model.

## Audit artifacts

### Restored cold artifact from `8975e4dd`

`audit_artifacts/test_cold_lifecycle_audit.py` was restored byte-for-byte and
not silently edited: **16 passed, 2 failed**.

The two failures are structurally obsolete H-6 setups. They deliberately move
the lease to expired before `_stop_requested()` and then expect execution to
reach the effect-heartbeat boundary. Candidate `4474ee5` stands down before
that boundary, so their synchronization event is correctly never reached.
Their invariant was reconstructed by permanent effect-start tests and the new
H-8 test; an expired worker does not execute the effect, but H-8 proves it can
still mutate durable step-start state after a lock wait.

### New H-8/H-9 artifact

`audit_artifacts/test_final_cold_h8_h9.py`: **0 passed, 2 failed**. Both tests
assert the required safety property and fail on deterministic real-PostgreSQL
observations. Synchronization controls only interleaving; ownership, row locks,
lease clocks, autoflush, heartbeat failure handling, and reaping are production
operations.

## Verification

- `uv run pytest -q`: **250 passed, 1 skipped, 0 failed**. The skip is the
  explicitly POSIX-only traversal case on Windows.
- Ownership/effect-start/planning/lease/dependency selection: **55 passed** per
  run, repeated three times with identical results.
- Historical cold artifact: **16 passed, 2 structurally obsolete failures**.
- New final-cold artifact: **0 passed, 2 genuine invariant failures**.
- `uv run ruff check .`: PASS after formatting the new audit-only artifact.
- `uv run ruff format --check .`: PASS, 105 files formatted.
- `uv run mypy packages apps workers`: PASS, 49 source files.
- `uv run lint-imports`: PASS, four contracts kept.
- Web lint: PASS, no warnings or errors.
- Web typecheck: PASS.
- Web production build: PASS.
- Alembic `current`: `0001_phase0 (head)`.
- Alembic `heads`: one head, `0001_phase0`.
- Alembic downgrade to base and upgrade to head: PASS.

## Classification and disposition

- H-8: High production code defect; permanent test coverage missing.
- H-9: High production code defect; permanent test coverage missing.
- Two restored H-6 artifact failures: obsolete test setup, not candidate
  regression and not hidden as PASS.
- Missing initial worktree/database and Node installation: environment setup;
  resolved without production changes.
- Existing Phase 0 PASS documentation is now inaccurate for durable lease
  recovery until H-8/H-9 are remediated and re-audited.

Phase 0 may not be technically finalized. Do not create `continuum-phase-0`.
