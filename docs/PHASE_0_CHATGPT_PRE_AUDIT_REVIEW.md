# Phase 0 ChatGPT Pre-Audit Review

**Purpose:** record a static pre-audit review of the integrated Phase 0 candidate before the final independent/falsification run.  
**Production integration merge reviewed:** `5e99d42fa1bc202005c80d2beeb84081ffdc9821`  
**Scope:** durable job ownership/finalization and dependency-graph concurrency only.  
**Status:** hypotheses for adversarial verification; this document does **not** declare a production defect without a deterministic reproduction.

## Reviewed authority and code

- `docs/FOUNDATION_APPROVAL.md`
- `docs/ADR/0002-durable-jobs-and-worker-boundary.md`
- `packages/jobs/src/continuum_jobs/execution.py`
- `packages/jobs/src/continuum_jobs/lease.py`
- `packages/jobs/src/continuum_jobs/queue.py`
- `workers/runner/src/continuum_worker/main.py`
- `tests/acceptance/test_110_06_11_lease_concurrency.py`
- `tests/acceptance/test_110_11_dependency_concurrency.py`

The already-shipped suites and the user's integrated Windows/PostgreSQL run are green. The purpose here is to look for interleavings that those suites may not cover.

## H-1 — ownership loss after a unit but before final job completion

`execute_job()` runs `LeaseHeartbeat` only around `handler.execute_unit()`. On a successful handler return it snapshots `beat.ownership_lost`, exits the heartbeat context, writes/commits the step completion and checkpoint/progress, then performs a post-unit lease renewal. After the final unit it transitions the job directly to `SUCCEEDED`.

Two details require adversarial verification together:

1. the post-unit call is currently equivalent to `renew_lease(session, job.id, lease_seconds)` without `worker_id`, so `renew_lease()` checks `RUNNING` but does not check `lease_owner` for that call;
2. after the final unit there is no `_stop_requested()` ownership check before `transition(..., SUCCEEDED)`.

Hypothesis to falsify: if worker A loses ownership after the unit's heartbeat stops but before/around post-unit finalization, a reaper may requeue the job and worker B may claim it, after which stale worker A could extend B's lease and/or mark B's job `SUCCEEDED`.

A useful deterministic reproduction should coordinate real PostgreSQL sessions/row locks rather than rely on sleeps. It should prove whether worker A can mutate lease/status/progress after B has become the committed owner.

**Required result:** either prove this impossible under the actual transaction/locking semantics, or produce a deterministic reproduction.

## H-2 — handler exception after ownership has been lost

The success path checks `lost_ownership` after `handler.execute_unit()` returns. The exception path catches the handler exception and immediately writes `STEP_FAILED` / `fail_job(...)`; it does not appear to consult the heartbeat's ownership-loss state first.

Hypothesis to falsify: worker A loses ownership while a long unit is still executing, the heartbeat observes/refuses renewal, then the handler raises. The stale worker may write failure state for a job now owned by worker B or returned to the queue.

Audit with a deterministic handler/barrier if possible. A correct result must preserve the rule that a worker which no longer owns the job does not write status/progress for it.

## H-3 — transition locking/ownership contract

ADR-0002 section 4 states that worker/reaper status transitions go through a single transition function **holding the row lock**. The current `transition()` function validates the in-memory status and flushes the ORM object, but the function itself does not acquire `FOR UPDATE` and does not condition the write on `lease_owner`.

This may still be safe if every production caller that can race already holds the required row lock/ownership guarantee; do not label it a defect solely from static inspection.

Audit call sites and attempt a stale-ORM transition after another transaction has committed a newer status/owner. Determine whether the implementation actually enforces the accepted invariant or merely relies on caller discipline.

## C-2 static review — dependency graph advisory lock

The integrated C-2 fix acquires a PostgreSQL transaction-scoped advisory lock before `_creates_cycle()` and keeps it through `session.flush()`; because it is an `xact` lock, release occurs only at transaction commit/rollback. At static review this is a coherent root fix for concurrent graph mutations, including an initially empty graph.

The final audit should still attempt:

- opposing two-edge race;
- synchronized 3-, 4-, and deeper-node cycles;
- concurrent valid DAG additions;
- exception/rollback while another writer waits;
- repeated `add_dependency()` calls in one transaction (advisory-lock reentrancy);
- graph usability and lock release after rejection;
- any lock-order deadlock involving dependency insertion and job-row/FK locks.

## Pre-audit disposition

No production change is made by this review. C-1 and C-2 remediations remain integrated and all currently shipped gates are green, but Phase 0 should **not** be tagged until H-1/H-2/H-3 are either cleared with reasoning + adversarial evidence or fixed and re-audited.
