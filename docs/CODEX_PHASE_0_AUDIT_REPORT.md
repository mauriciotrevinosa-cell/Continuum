# Codex Independent Phase 0 Audit Report

**Audited candidate:** `02764288bd206c11f3a69b215e5eea33e7188779`  
**Fixed code candidate:** `441654b0d6b72f19d5acf4de5afcfdef8c815365`  
**Candidate branch:** `phase-0/claude-implementation`  
**Audit branch:** `audit/codex-phase-0-0276428`  
**Audit date:** 2026-09-01  
**Verdict:** `FAIL`  
**Recommendation:** `REJECT` pending correction and execution of every database-backed gate.  

No `continuum-phase-0` tag was created. No Phase 1 feature was added.

## Environment

- Windows 11 (`win32`), repository at `C:\Users\mauri\OneDrive\Desktop\Continnum`
- `uv 0.11.27`, Python `3.12.10`, Node `v24.15.0`
- pnpm `9.15.4` available through Corepack, but not directly on `PATH`
- Docker/PostgreSQL unavailable (`docker` command not found)
- The checkout is under OneDrive and therefore fails OQ-2/D-19 independently of code quality

## Executive Findings

| Status | Severity | Classification | Finding |
|---|---:|---|---|
| **FAIL (fixed on audit branch)** | Critical | Code defect + test defect | Retryable jobs were never automatically claimable. `fail_job()` left them in `FAILED_RETRYABLE`, while `claim_next_job()` selected only `QUEUED`; the acceptance test checked recorded backoff but never proved a due retry could run. |
| **FAIL (fixed on audit branch)** | High | Code defect | Retry scheduling and lease-reaper rescheduling used the worker's local UTC clock, contrary to D-09/F-25. They now obtain `now()` from PostgreSQL. |
| **FAIL (fixed on audit branch)** | Critical | Test defect + code defect | `die_at_unit` called `os._exit(137)` before the content-addressed effect. It did not exercise the promised effect-landed/completion-not-committed crash window. It now dies after landing the effect and only on the first landing. |
| **FAIL (fixed on audit branch)** | High | Code defect masked by skipped test | `execute_job()` converted `SyntheticBlockedError` into `FAILED_FINAL`, making the worker's `BLOCKED(MISSING_PROVIDER)` branch unreachable. The exception now propagates to the worker-owned blocked transition. |
| **FAIL (unfixed)** | Critical | Code defect + missing test | No heartbeat runs during a unit. The worker heartbeats before claim and renews the lease only after a unit finishes. A unit longer than its lease can be reaped and executed concurrently by another worker. `worker_heartbeat_seconds` is configured but unused. |
| **FAIL (unfixed)** | High | Code defect | API request helpers write job status directly (`request_pause` and `request_cancel`), contrary to the approved rule that the API sets request flags and only worker/reaper paths write status. |
| **FAIL (unfixed)** | Medium | Code/test defect | Dependency cycle prevention is not implemented beyond the database self-edge check. ADR-0002 requires a cycle check at insert; there is no transitive-cycle test. |
| **NOT RUN** | Blocker | Environment prerequisite | Acceptance 110.1 and 110.6-110.11, the migration round trip, concurrent enqueue, lease recovery, retry execution, checkpoint durability, drain/resume, and the repaired post-effect crash path require PostgreSQL and did not execute. |
| **BLOCKED** | Blocker | Environment prerequisite | The active repository is under OneDrive. Foundation Approval OQ-2/D-19 prohibits declaring Phase 0 accepted from this location. |

## Acceptance Matrix

| Requirement | Result | Evidence |
|---|---|---|
| 110.1 clean install/migrate/boot | **NOT RUN** | Docker/PostgreSQL unavailable. Offline Alembic head check passed. |
| 110.2 API health/web contract | **PASS_ON_THIS_RUNNER** | Non-DB API tests passed; Next.js lint, typecheck, and production build passed. |
| 110.3 path normalization | **PASS_ON_THIS_RUNNER** | Available path tests passed. |
| 110.4 traversal/symlink/junction | **BLOCKED/PARTIAL** | Available Windows cases passed; privilege-dependent cases skipped. Skips are not PASS. |
| 110.5 vault immutability | **PASS_ON_THIS_RUNNER** | Structural/read-only tests passed; no audit write probe was performed. |
| 110.6 durable processing | **NOT RUN** | PostgreSQL fixture skipped. |
| 110.7 durable progress | **NOT RUN** | PostgreSQL fixture skipped. |
| 110.8 API/UI independence | **NOT RUN** | Process-backed acceptance case skipped; static topology inspection passed. |
| 110.9 graceful stop/resume | **NOT RUN** | PostgreSQL fixture skipped. |
| 110.10 unfinished-only resume and repeat-safe effect | **NOT RUN** | PostgreSQL fixture skipped. Candidate's hard-kill injection was defective and was repaired, but not executed. |
| 110.11 error/retry/reaper | **NOT RUN** | PostgreSQL fixture skipped. Static audit found retry and clock defects; repaired paths remain unverified. |
| 110.12 provider/privacy | **PASS_ON_THIS_RUNNER** | Fake-provider suite passed with no AI SDK; end-to-end BLOCKED job case remained skipped. |
| 110.13 secret logging | **PASS_ON_THIS_RUNNER** | Redaction tests passed. |
| 110.14 migration strategy/round trip | **PARTIAL** | One Alembic head; database upgrade/downgrade/upgrade not run. |
| 110.15 required documents | **PASS** | Required Phase 0 documents exist. This audit corrects overclaims rather than treating prose as runtime evidence. |

## Detailed Evidence

### Durable retries

At the candidate, `packages/jobs/src/continuum_jobs/queue.py` selected only
`QUEUED` rows, while `fail_job()` transitioned retryable failures to
`FAILED_RETRYABLE`. No worker path promoted due failures. The existing test
stopped after asserting `run_after` was populated. The audit fix lets the
locked claim query select due `FAILED_RETRYABLE` rows, transitions them through
`QUEUED`, and adds an assertion that normal claiming returns the same job.

### Crash-window idempotency

At the candidate, `workers/runner/src/continuum_worker/handlers/synthetic.py`
terminated before `DerivedStore.put_bytes()`. This contradicted its own comment
and did not prove F-22. The audit fix places termination after the durable
content-addressed write and before `UnitOutcome` can be committed. Recovery
does not terminate again because the identical artifact reports
`already_present=True`.

### Lease safety

`workers/runner/src/continuum_worker/main.py` calls `heartbeat()` before a
claim. `packages/jobs/src/continuum_jobs/execution.py` renews the job lease only
after `execute_unit()` returns. There is no periodic renewal during a long
unit, despite the configured `worker_heartbeat_seconds`. This permits the
reaper to reclaim live work and violates the active-work lease contract. A fix
needs a database-backed two-worker regression test and was not guessed in an
environment where that test cannot run.

### State ownership

`packages/jobs/src/continuum_jobs/queue.py` transitions queued/running jobs in
`request_pause()` and `request_cancel()`. Those helpers are invoked by API
routes. This conflicts with Foundation Approval invariant 8 and ADR-0002 section
4: API calls set flags; worker/reaper code owns guarded status transitions.

### Storage and vault

`SourceVaultReader` exposes read operations only. `DerivedStore` accepts only
keys from `WRITABLE_ROOT_KEYS`, which excludes `source_vault`, and derived paths
are hash-generated. The filesystem/import AST guards executed and passed. The
audit never wrote to the Source Vault. Windows privilege-dependent symlink
coverage remains incomplete, and no universal PASS is claimed.

### Scope, providers, security, and schema

No Phase 1 domain implementation or real AI SDK was found. The API surface is
limited to health/jobs/workers, loopback validation is present, CORS is
restricted, provider data classification is required, privacy filtering occurs
before cost filtering, and `FREE_LOCAL` rejects remote/paid-only capability.
ORM/migration inspection shows the six Phase 0 application tables plus Alembic
bookkeeping and pgvector extension setup, with no domain/vector tables.

## Fixes Made

Fix commit: `441654b0d6b72f19d5acf4de5afcfdef8c815365`

1. Automatic claim/promotion of due `FAILED_RETRYABLE` jobs plus a regression assertion.
2. PostgreSQL-clock scheduling for automatic/manual retry and lease recovery.
3. Post-effect/pre-checkpoint hard-death injection that is safe on recovery.
4. Propagation of actionable blocked-capability errors to the worker's BLOCKED transition.

These fixes are reviewable Phase 0 changes only. Their PostgreSQL-dependent
tests are still `NOT RUN`; code inspection is not substituted for execution.

## Commands Executed

```text
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
uv run mypy packages apps workers
uv run lint-imports
uv run alembic heads
corepack pnpm --filter @continuum/web lint
corepack pnpm --filter @continuum/web typecheck
corepack pnpm --filter @continuum/web build
docker version
```

Observed non-database result: Python suite completed with 24 explicit skips and
no failures; ruff, formatting, mypy strict, four import contracts, one Alembic
head, web lint, web typecheck, and production build passed. `docker version`
could not run because Docker is not installed.

## Required Before Re-audit

1. Move/clone the repository and all configured data roots outside OneDrive.
2. Install/start Docker Desktop and the PostgreSQL/pgvector service.
3. Fix and test lease renewal during long-running units with two workers.
4. Resolve API status ownership to match the approved request-flag design.
5. Implement and test transitive dependency-cycle rejection.
6. Run clean migration and upgrade/downgrade/upgrade round trip.
7. Run all 110.6-110.11 cases, including real hard-kill recovery after effect landing, concurrent dedupe, automatic retry, drain/resume, and no duplicate effects.
8. Execute every required Windows path-security case; report privilege-related skips explicitly until resolved.

## Final Recommendation

**REJECT** candidate `02764288bd206c11f3a69b215e5eea33e7188779` for Phase 0 acceptance. The
candidate contains verified critical durability defects, and its load-bearing
PostgreSQL acceptance claims remain `NOT RUN`. The audit branch improves four
defects but is not acceptable for tagging until the remaining code defects are
fixed and the full database-backed suite executes successfully.
