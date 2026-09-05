# Codex Phase 0 Final Falsification Audit

## Verdict

**REJECT — DO NOT TAG**

The exact candidate `b6295c4689716cb531fcf09623b07250906e10d1`
contains three deterministically reproduced stale-worker ownership defects. A
worker that has lost a job can finalize it, fail it, and overwrite its newer
owner through an unlocked transition. These are unresolved High Phase 0
defects in the durable coordination foundation.

## Audit identity and environment

- Audited branch: `audit/codex-phase-0-final-b6295c4`
- Audited candidate: `b6295c4689716cb531fcf09623b07250906e10d1`
- Workspace: `C:\Continuum-Codex-Audit` (outside synchronized storage)
- Platform: Windows, with Developer Mode enabled
- Data home: `C:/ContinuumData-Codex-Audit`
- Database: PostgreSQL at `127.0.0.1:5433/continuum_codex_audit`
- `docker compose ps`: command succeeded but listed no services for this
  worktree's Compose project. Direct application connectivity, migrations,
  and every PostgreSQL acceptance test succeeded against port 5433.
- Python: CPython 3.12.10 through `uv`
- Web dependencies were initially absent. `pnpm install --frozen-lockfile`
  installed the locked dependencies without changing the lockfile; all web
  gates then passed. This was an environment prerequisite, not a code defect.

Production code was not modified. No tag was created.

## Findings

### Critical

None.

### High

#### H-1: stale worker finalizes a job reclaimed by another worker (code defect)

**FAIL.** The last-unit sequence has an ownership-free interval after the
heartbeat context exits. The worker commits `JobStep.SUCCEEDED`, progress, and
any checkpoint at
`packages/jobs/src/continuum_jobs/execution.py:293-330`, then calls
`renew_lease()` without `worker_id` at line 333 and unconditionally transitions
the stale ORM job to `SUCCEEDED` at line 336.

`test_stale_worker_cannot_finalize_after_post_handler_reclaim` pauses exactly
at that post-unit renewal. PostgreSQL reaps A's expired lease and B claims the
job. B is observably `RUNNING` and owns the lease before A resumes. A then
returns `COMPLETED` rather than `OWNERSHIP_LOST`. H-3 independently proves the
resulting stale final transition clears B's lease and commits `SUCCEEDED`.

The optional ownership predicate in
`packages/jobs/src/continuum_jobs/lease.py:105-107` allows the omitted owner at
the execution call site to extend B's lease. Ignoring the boolean result at
execution lines 332-334 also prevents the caller from standing down.

#### H-2: handler exception after known ownership loss fails B's job (code defect)

**FAIL.** The exception path at
`packages/jobs/src/continuum_jobs/execution.py:272-291` never examines
`beat.ownership_lost`. It writes `STEP_FAILED`, error history, attempts, and a
job failure after the heartbeat has proved that A no longer owns the job.

`test_handler_exception_after_ownership_loss_cannot_fail_new_owner_job` uses an
event emitted by the actual refused PostgreSQL renewal, not a timing guess.
Only after the heartbeat observes B's ownership does the handler raise. A
returns `FAILED`, not `OWNERSHIP_LOST`, and executes the stale failure path.

#### H-3: transition validation and write are not protected by a row lock (code defect)

**FAIL.** `transition()` validates `job.status` from an in-memory ORM object at
`packages/jobs/src/continuum_jobs/queue.py:180-193`; `_apply_status()` mutates
and flushes that object at lines 210-229. It neither locks/reloads the row nor
performs a compare-and-set including current owner/status.

`test_transition_rejects_a_stale_unlocked_orm_snapshot` loads A's `RUNNING`
snapshot, lets another transaction reap and claim the job for B, then calls
`transition(... SUCCEEDED, worker_id=A)`. PostgreSQL persists `SUCCEEDED` and
clears B's lease. The same helper underlies finalization, failure, block,
pause, drain, and other worker transitions, so callers without an independently
held row lock share this defect class.

### Medium

None.

### Low

None.

## Historical remediation results

### C-1 lease/reaper race

**PASS for the historical stale-reaper race; FAIL for the newly tested wider
ownership lifecycle.** The reaper's `FOR UPDATE SKIP LOCKED` selection and
under-lock revalidation at `packages/jobs/src/continuum_jobs/lease.py:275-367`
prevent a stale pre-renewal observation from overwriting a fresh lease. The 13
shipped lease concurrency tests passed, covering genuine abandonment, live
renewal, renewal/reaper ordering, two reapers, ownership loss, resurrection,
and persistent heartbeat failure. Long-unit heartbeat coverage also passed in
the shipped suite. H-1 and H-2 show that protection ends too early in
`execute_job()` and does not cover exception unwinding.

### C-2 concurrent dependency cycles

**PASS.** The transaction advisory lock at
`packages/jobs/src/continuum_jobs/queue.py:417-438` serializes reachability and
insert/flush until commit or rollback. All seven shipped dependency tests and
all three additional audit tests passed. Added tests exercised concurrent
four- and eight-edge cycles, five concurrent valid DAG mutations, rejection
rollback, lock release, graph usability, and deadlock timeouts. Persisted
graphs remained acyclic. The lock is transaction-scoped and reentrant within a
transaction; exception paths require the normal caller rollback, after which a
waiting/fresh transaction acquires it successfully.

## Audit artifacts

- `audit_artifacts/test_final_audit_worker_ownership.py`: **0 passed, 3
  failed**, intentionally asserting the required ownership invariant. All
  failures are deterministic PostgreSQL reproductions of H-1, H-2, and H-3.
- `audit_artifacts/test_final_audit_dependency_lock.py`: **3 passed, 0
  failed**.
- Combined audit-artifact result: **3 passed, 3 failed**.

The synchronization hooks only pause production boundaries or observe an
actual production renewal result. Reaping, claiming, transitions, commits,
advisory locks, and graph persistence all use real PostgreSQL transactions.

## Phase 0 acceptance §110

| Item | Result | Evidence |
|---|---|---|
| 110.1 clean setup/migrations/boot | PASS | PostgreSQL reachable; Alembic current/head and downgrade-base/upgrade-head succeeded. |
| 110.2 web/API health | PASS | Shipped health/API tests and web gates passed. |
| 110.3 vault path normalization | PASS | Required storage selection passed. |
| 110.4 traversal/symlink/junction | PASS on Windows; NOT RUN on POSIX | 66 passed, one explicitly POSIX-only test skipped. Windows symlink/junction cases executed. |
| 110.5 vault immutability | PASS | Shipped structural/behavioral tests passed; no write probe was added. |
| 110.6 durable queue/process | FAIL | H-1 proves stale A can finalize B's claimed job. |
| 110.7 progress independent of UI | PASS | PostgreSQL-backed shipped coverage passed. |
| 110.8 API restart does not cancel worker | PASS | Standalone process/boundary coverage passed. |
| 110.9 graceful pause/drain/resume | FAIL | Shared transition primitive does not hold the ADR-required lock; H-3 proves stale overwrite. |
| 110.10 unfinished-only resume/idempotent effect | PASS | Forced completed-unit rerun and post-effect crash coverage passed. This does not cure stale coordination writes. |
| 110.11 failure/retry/lease recovery | FAIL | H-1, H-2, and H-3 violate ownership; historical reaper race itself passed. |
| 110.12 providers/no credentials | PASS | Full suite passed under `FREE_LOCAL` without cloud credentials. |
| 110.13 secret leakage | PASS | Redaction/config coverage passed. |
| 110.14 migration strategy | PASS | One head; downgrade/upgrade round trip passed. |
| 110.15 required docs/final review | FAIL | Final falsification audit rejects the candidate. |

## Gate results

- `uv run pytest -q`: **215 passed, 1 skipped, 0 failed**. Skip:
  `test_110_04_traversal.py:135`, POSIX-only filesystem semantics.
- Lease/dependency targeted selection: **20 passed, 0 skipped, 0 failed**.
- Path/traversal/vault targeted selection: **66 passed, 1 skipped, 0 failed**.
- `uv run ruff check .`: PASS.
- `uv run ruff format --check .`: PASS, 102 files formatted.
- `uv run mypy packages apps workers`: PASS, 49 source files.
- `uv run lint-imports`: PASS, four contracts kept.
- `corepack pnpm --filter @continuum/web lint`: PASS, no warnings/errors.
- `corepack pnpm --filter @continuum/web typecheck`: PASS.
- `corepack pnpm --filter @continuum/web build`: PASS.
- Alembic `current`, `heads`, `downgrade base`, `upgrade head`: PASS; one
  head (`0001_phase0`).

The green shipped suite alongside failing audit artifacts is a **test defect**:
permanent acceptance coverage is missing for the post-handler ownership gap,
exception-after-loss path, and atomic transition ownership. The underlying
failures are **code defects**. The Phase 0 report's existing PASS claims for
110.6, 110.9, and 110.11 are now disproved, making those claims a
**documentation defect** until remediation and re-audit. The absent initial
web install and empty worktree-local Compose listing are **environment
observations**, not candidate defects.

## Required disposition

Do not finalize Phase 0 and do not create `continuum-phase-0`. Remediation must
make ownership/status validation atomic with every worker mutation, cover the
post-heartbeat finalization interval and exception path, add permanent
PostgreSQL regressions, and undergo a fresh independent audit.
