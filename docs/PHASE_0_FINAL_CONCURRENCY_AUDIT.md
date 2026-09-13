# Phase 0 Final Concurrency Closure Audit — H-1 / H-2 / H-3

**Scope:** the three open ownership/finalization questions from `PHASE_0_CHATGPT_PRE_AUDIT_REVIEW.md` and §7 of `PHASE_0_FINAL_AUDIT_HANDOFF.md`, against the code of the PR #7 closure candidate.
**Candidate before this audit:** `bc7836f357f075858251145e4e7ea17c860b4865` (no production change since the concurrency merge `5e99d42`).
**Production fix + regression tests:** `81aa80d4520b88dfb58418e8311a487cc1ce9369`.
**This document:** a documentation-only descendant of `81aa80d`. The branch head that carries it is the exact candidate for review.
**Audit date:** 2026-09-13.
**Who:** Claude Code implemented the fix and ran this audit. It is not an independent audit; ChatGPT reviews it before any merge or tag.

## 1. Result

| Hypothesis | Result | Severity | Status |
|---|---|---|---|
| H-1 — ownership lost after a unit, before finalization | **DEFECT, reproduced deterministically** | Critical | Fixed in `81aa80d` |
| H-2 — handler exception after ownership loss | **DEFECT, reproduced deterministically** | High | Fixed in `81aa80d` |
| H-3 — transitions validated stale in-memory state | **DEFECT, reproduced deterministically** (worker, API and worker-BLOCKED paths) | High | Fixed in `81aa80d` |

The green CI on `bc7836f` did not cover these interleavings. All three reproduced against unmodified production code on live PostgreSQL. None depended on timing.

## 2. Environment actually observed

- Windows 11 `10.0.26200`; repository `C:\Continuum`.
- Docker Desktop engine `29.7.2`. It failed to start at first because stale Windows AF_UNIX socket files from an earlier session could not be removed. Moving the two stale socket directories aside (`%LOCALAPPDATA%\Docker\run`, `%LOCALAPPDATA%\docker-secrets-engine`) let it start. No data or volume was touched.
- `continuum-db`: `pgvector/pgvector:pg16`, healthy, `127.0.0.1:5433->5432`. Alembic `0001_phase0 (head)`.
- Python 3.12 via `uv`; pnpm 9.15.4.

## 3. How the reproductions were made deterministic

Test file: `tests/acceptance/test_110_06_11_ownership_finalization.py`. Every test uses real PostgreSQL, and there are no sleeps. The "takeover" is ordinary production code on a second session, committed: expire the lease, `reap_expired_leases()`, then `claim_next_job()` for worker B. It is triggered at an exact point in worker A's execution:

- **after A's heartbeat has stopped:** a `LeaseHeartbeat` subclass, swapped into `continuum_jobs.execution`, runs the takeover in `__exit__` after the heartbeat thread has been joined;
- **after a specific commit of A's session:** a SQLAlchemy `after_commit` listener;
- **inside the handler:** waiting on the heartbeat's own ownership-lost `threading.Event`, not on elapsed time.

When A's heartbeat is not under test, it is configured with a first beat minutes away. Ordering never depends on that: every takeover is triggered by a hook. Sessions use `expire_on_commit=False`, exactly like production. A worker's in-memory row therefore survives its own commits, and that is what makes H-3 reachable.

The assertion helper `_assert_untouched_since()` compares, field by field, against a snapshot committed by B's takeover: status, owner, lease deadline, attempt, units done, current step, elapsed time, last error, error history, every step's status/attempt/error, the checkpoint count, and every event. The only thing the stale worker may add is its own stand-down event.

## 4. Findings

### H-1 — ownership lost after the unit returns

**Violated invariant:** *no worker-owned mutation after ownership has been lost* (ADR-0002 §4–5; FOUNDATION_APPROVAL invariant 8: one writer of `status`).

**Root cause (`bc7836f`):**
1. After `execute_unit()` returned, `execute_job()` snapshotted `beat.ownership_lost` and exited the heartbeat. It then wrote step SUCCEEDED, `units_done`, `current_step`, `elapsed_active_ms`, the checkpoint and events, and committed, all with no ownership check.
2. It then called `renew_lease(session, job.id, lease_seconds)` **without `worker_id`**, so the `UPDATE` matched any RUNNING job.
3. After the last unit it called `transition(SUCCEEDED)` directly. `transition()` validated only the in-memory `job.status` (still RUNNING in A's session) and wrote `status`, `lease_owner = NULL` and `completed_at`.

**Deterministic reproduction on `bc7836f`:**

| Test | Interleaving | Observed on `bc7836f` |
|---|---|---|
| `test_no_progress_or_checkpoint_after_losing_the_job_before_the_completion_commit` | takeover after A's heartbeat stops, before the completion commit | `stale worker moved B's job to SUCCEEDED` |
| `test_final_success_is_not_written_after_losing_the_job` | takeover after A's unit commit, before the final transition | `stale worker moved B's job to SUCCEEDED` |
| `test_a_stale_worker_cannot_extend_the_new_owners_lease` | 2 units; takeover after A's first unit commit | `stale worker moved B's lease` |
| `test_reaped_work_is_completed_by_the_new_owner` | takeover before A's completion; B then runs the job | B executed only `unit-1`: A had falsely recorded `unit-0` as done on B's job |

**Consequence:** a job another worker is executing reaches terminal `SUCCEEDED` with its lease cleared. Recovery is defeated, and the new owner's progress is corrupted.

### H-2 — handler exception after ownership loss

**Root cause:** the exception branch wrote `STEP_FAILED` and called `fail_job()` immediately. `fail_job()` increments `attempt`, rewrites `last_error`/`error_history` and transitions to `FAILED_RETRYABLE`/`FAILED_FINAL`. Nothing consulted the heartbeat or the database first.

| Test | Interleaving | Observed on `bc7836f` |
|---|---|---|
| `test_failure_after_the_heartbeat_saw_the_loss_writes_nothing` | B takes over during the unit; the handler waits for the heartbeat's ownership-lost event, then raises | `stale worker moved B's job to FAILED_RETRYABLE` |
| `test_failure_after_an_unnoticed_loss_writes_nothing` | B takes over during the unit; the handler raises before any beat | `stale worker moved B's job to FAILED_RETRYABLE` |

### H-3 — transition locking and stale ORM state

**Root cause:** `transition()` ran `assert_transition(job.status, …)` on the caller's object and flushed it. It took no row lock and made no comparison with the committed row. Because sessions keep objects across commits, stale beliefs are the normal state, not an edge case.

| Test | Interleaving | Observed on `bc7836f` |
|---|---|---|
| `test_stale_worker_transition_cannot_overwrite_a_newer_owner` | A loads its RUNNING job and commits; B takes over; A transitions from its object | `DID NOT RAISE` — B's job overwritten |
| `test_stale_resume_cannot_reopen_a_cancelled_job` | API loads PAUSED; a worker cancels (→ CANCELLED, terminal); API `resume_job()` from its view | `DID NOT RAISE` — a terminal CANCELLED job became QUEUED |
| `test_worker_block_path_cannot_overwrite_a_newer_owner` | `Worker.run_once()`: B takes over, then the handler reports a missing capability | `stale worker moved B's job to BLOCKED` |

## 5. Root fix (`81aa80d`)

One database-enforced rule: **prove ownership under the row lock, in the same transaction as the write it permits.**

- **`queue.lock_job(session, job)`:** `SELECT status, lease_owner … FOR NO KEY UPDATE`, with autoflush suspended so no pending change reaches the row before the check. `NO KEY UPDATE` excludes every writer of the row (worker, reaper/claim `FOR UPDATE SKIP LOCKED`, lease renewal) but not inserts that merely reference the job (events, steps), so it adds no lock-order hazard with dependency inserts or audit events.
- **`transition()`:** now the single database-guarded status writer. It locks the row, then refuses before writing:
  - `owner=` given and the row's `lease_owner` differs → `JobOwnershipLostError`;
  - the session's loaded `(status, lease_owner)` differs from the committed row → `StaleJobStateError`. Pending in-memory edits are ignored by design; for example, the reaper clears `lease_owner` before transitioning.

  The transition table is then applied to the row's **actual** status.
- **`fail_job(owner=)`** proves ownership under the lock **before** touching `attempt`, `last_error` or `error_history`. **`block_job(owner=)`** does the same through `transition()`.
- **`renew_lease(…, *, worker_id)`:** `worker_id` is mandatory; there is no unowned renewal.
- **`execute_job()`:** each of these transactions begins with `_hold()` (lock + "RUNNING and `lease_owner == worker_id`"), held until commit:
  - plan;
  - stop check and step start (pause/cancel/drain landing included);
  - unit completion, together with the lease renewal (renewal moved into the same transaction);
  - unit or plan failure;
  - the final `SUCCEEDED`.

  A refusal rolls back and records only a `LEASE_EXPIRED` stand-down event. That append-only insert neither changes nor locks anything the owner uses. No lock is held while a handler runs, and the heartbeat still renews during long units.
- **Standalone worker:** both BLOCKED paths (unknown job type, blocked capability) go through `_park()`, which calls `block_job(owner=…)` and stands down on refusal.
- **`apply_pending_requests()` and `unblock_ready_dependents()`** lock rows as they select them (`FOR UPDATE SKIP LOCKED`), like claim and the reaper. A decision is made on the row as committed, and concurrent passes cannot trip the freshness check.
- **Removed `touch_progress()`:** it had no callers, was not exported, and was an unguarded job-row write.

### H-3 call-site audit (every production status writer after the fix)

| Call site | Actor | Protection |
|---|---|---|
| `execution.execute_job` final `SUCCEEDED` | executing worker | `_hold()` + `transition(owner=worker)` |
| `execution._land_stop` (CANCELLING, CANCELLED, PAUSING, PAUSED, drain PAUSED→QUEUED) | executing worker | runs inside the `_hold()` transaction; every transition `owner=worker` |
| `execution._record_failure` → `fail_job` (FAILED_RETRYABLE / FAILED_FINAL) | executing worker | `_hold()` + `fail_job(owner=)` (proof before bookkeeping) + `transition(owner=)` |
| `worker.main.Worker._park` → `block_job` (BLOCKED) | executing worker | `block_job(owner=worker)`; stands down on refusal |
| `lease.reap_expired_leases` (QUEUED, FAILED_FINAL) | reaper | `FOR UPDATE SKIP LOCKED` + re-verification under lock (C-1) + `transition()` lock/freshness |
| `queue.claim_next_job` (FAILED_RETRYABLE→QUEUED, QUEUED→RUNNING) | claiming worker | `FOR UPDATE SKIP LOCKED` + `transition()` lock/freshness |
| `queue.apply_pending_requests` (CANCELLED, PAUSED) | worker pass | **now** `FOR UPDATE SKIP LOCKED` + `transition()` |
| `queue.unblock_ready_dependents` (QUEUED) | worker pass | **now** `FOR UPDATE SKIP LOCKED` + `transition()` |
| `queue.resume_job`, `queue.retry_job` (→QUEUED) | API | `transition()` lock/freshness; a stale view raises `StaleJobStateError`, surfaced as HTTP 409 by the existing `ContinuumError` handler |
| `queue.enqueue` with `depends_on` (`_apply_status` → BLOCKED) | API | the row is created in the same uncommitted transaction, so no other writer can see it |

Non-status job writes: lease renewal (owner in the `WHERE`), progress/checkpoint/step writes (inside `_hold()`), and the API's `request_pause`/`request_cancel` (request flags only; the worker reads them under its lock).

A static invariant (`tests/invariants/test_worker_ownership_contract.py`) keeps this true: every `transition`/`fail_job`/`block_job` call in `execution.py` and the worker passes `owner=`; `renew_lease` has no default `worker_id` and no call omits it; and the execution loop contains no raw `update()`. It runs in the offline job, without a database.

## 6. Permanent regression tests and proof they exercise the old failure

The production changes of `81aa80d` were temporarily stashed (patch SHA-256 `be04e6b42b69d86aa46f43db62035711cd0282fe3c80fa385e13765fb255b382`) and the final tests were run against the original production code. The fix was then restored byte-identically.

| # | Required coverage | Test | Original code | Fixed code |
|---|---|---|---|---|
| 1 | stolen after handler returns, before unit completion commit | `test_no_progress_or_checkpoint_after_losing_the_job_before_the_completion_commit` | FAIL | pass |
| 2 | stolen before final SUCCEEDED | `test_final_success_is_not_written_after_losing_the_job` | FAIL | pass |
| 3 | stale A cannot extend B's lease | `test_a_stale_worker_cannot_extend_the_new_owners_lease` | FAIL | pass |
| 3 | (contract) | `test_renew_lease_has_no_unowned_form` | FAIL | pass |
| 4 | handler raises after heartbeat knows ownership is lost | `test_failure_after_the_heartbeat_saw_the_loss_writes_nothing` | FAIL | pass |
| 4 | (variant) loss not yet noticed | `test_failure_after_an_unnoticed_loss_writes_nothing` | FAIL | pass |
| 5 | stale ORM transition cannot overwrite newer owner/status | `test_stale_worker_transition_cannot_overwrite_a_newer_owner` | FAIL | pass |
| 5 | (API path) | `test_stale_resume_cannot_reopen_a_cancelled_job` | FAIL | pass |
| 5 | (worker BLOCKED path) | `test_worker_block_path_cannot_overwrite_a_newer_owner` | FAIL | pass |
| 5 | (contract) owner checked even from a fresh view | `test_owner_is_checked_even_from_a_fresh_view` | FAIL | pass |
| 5 | (contract) failure bookkeeping untouched on refusal | `test_fail_job_refuses_before_touching_retry_bookkeeping` | FAIL | pass |
| 6 | ordinary live worker completion | `test_a_live_worker_with_a_beating_heartbeat_completes_normally` | pass (preservation) | pass |
| 7 | reaped work recoverable by Worker B | `test_reaped_work_is_completed_by_the_new_owner` | FAIL | pass |
| — | static: owned writers name their owner | `test_every_worker_owned_status_write_names_its_owner` | FAIL | pass |
| — | static: no unowned renewal | `test_renew_lease_cannot_be_called_without_a_worker` | FAIL | pass |
| — | static: no raw UPDATE in the loop | `test_the_executing_worker_never_bypasses_the_guard_with_a_raw_update` | pass (regression guard) | pass |

On the original code: **14 of 16 fail**; the 2 that pass are a preservation test and a regression guard, by design. On the fixed code: **16 of 16 pass**. The first reproduction (the 10 scenario tests written before any fix) failed 9 of 10, identically, on three consecutive runs.

A seventeenth candidate test ("ownership proof held through the completion commit") was removed: it also passed on the original code, because an autoflushed `UPDATE` happened to hold the row lock at that moment. It therefore proved nothing about the fix.

## 7. Preserved behaviour

All pre-existing PostgreSQL suites pass unchanged, and no test was weakened, skipped or edited:

- `test_110_06_11_lease_concurrency.py` (C-1: stale reaper snapshot, concurrent reapers, heartbeat ownership loss, persistent heartbeat failure);
- `test_110_06_11_durable_jobs.py` (roundtrip, progress independent of UI, resume, forced rerun no-op, checkpoints, pause/cancel/drain, retry/backoff, lease reclaim, blocked capability, standalone worker process);
- `test_110_11_dependency_concurrency.py` (C-2);
- `test_110_11_remediation.py`.

Database-clock timing, content-addressed effects, graceful drain and the standalone worker boundary are unchanged. The Source Vault is not involved in any job path; this pass touched no Vault file.

## 8. Gate results (live PostgreSQL)

Production/test code at `81aa80d` (the gates were run on the identical working tree immediately before that commit):

| Gate | Result |
|---|---|
| `docker compose ps` | `continuum-db` healthy, `127.0.0.1:5433->5432` |
| `uv run alembic current` / `heads` | `0001_phase0 (head)` / `0001_phase0 (head)` |
| `uv run alembic upgrade head` | exit 0 |
| `uv run pytest -q` | exit 0 — **315 passed, 1 skipped** (`test_110_04_traversal.py:135` POSIX-only filesystem semantics) |
| `uv run pytest tests/acceptance/test_110_06_11_lease_concurrency.py tests/acceptance/test_110_06_11_durable_jobs.py -q -ra` | **30 passed**, 0 skipped |
| all job suites (lease, durable, ownership, dependency, remediation) | **70 passed**, 0 skipped |
| Windows path suite (`test_110_03`, `test_110_04`) | 52 passed, 1 skipped (POSIX-only); no Windows-case skip |
| Offline (empty environment, no database): `test_110_12_providers.py` + `tests/invariants` | 60 passed |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 138 files already formatted |
| `uv run mypy packages apps workers` | Success: no issues found in 56 source files |
| `uv run lint-imports` | Contracts: 4 kept, 0 broken |
| `pnpm install --frozen-lockfile` | done |
| `pnpm lint` | No ESLint warnings or errors |
| `pnpm typecheck` | exit 0 |
| `pnpm test` | 5 passed |
| `pnpm build:web` | Compiled successfully, exit 0 |
| OpenAPI: `uv run python scripts/export_openapi.py` + `pnpm --filter @continuum/web api:client` | zero drift |

GitHub Actions on `81aa80d`: all required jobs **success** in both runs:

| Job | push run `34774312398` | pull_request run `34774315586` |
|---|---|---|
| Python (ubuntu-latest, PostgreSQL) — lint, format, mypy, import boundaries, clean-database migrations, tests, durable-suite assertion | success | success |
| Python (windows-latest, path semantics) — tests, Windows path-suite assertion | success | success |
| Offline / no-credential run (110.12) | success | success |
| Web — lint, typecheck, test, build | success | success |
| OpenAPI client drift (D-10) | success | success |

## 9. Remaining items (none Critical or High)

- **Independence:** the fix was implemented and self-audited by Claude Code; ChatGPT's review of this document, the diff and CI is the independent check before merge.
- **C-2 depth:** the pre-audit's additional dependency-lock patterns (deeper synchronized cycles, advisory-lock reentrancy in one transaction, rollback while another writer waits) were not extended in this pass. The existing C-2 suite passes, and the lock scope was not changed.
- **110.4:** the one POSIX-only traversal case is skipped on Windows by platform marker. It is intended to execute on the Ubuntu CI job, whose quiet output does not list individual tests.
- **Stand-down leaves duplicate compute possible:** a worker that loses its job mid-unit may still finish that unit's effect. Effects are content-addressed, so the new owner's re-run is a byte-identical no-op. Nothing is written for the stale worker.
- **Worker-less execution:** `execute_job()` without `worker_id` (tests and tools only) raises `StaleJobStateError` on a refused write instead of returning `OWNERSHIP_LOST`, because there is no lease to lose.
- **Scope, outside this audit:** PR #7 also carries Library Acquisition, the read-only media viewer and the Project workspace, merged into the branch by explicit instruction. That work touches no job-system code. It is not a concurrency finding and does not change this verdict. **Reviewer decision (ChatGPT, 2026-09-13):** finalization gate #7 is accepted as an explicit scope exception. These are deliberately pre-integrated product surfaces carried through the Phase 0 closure; Phase 1 is not complete, none of its requirements are waived, and it begins as its own phase after closure. Recorded in `PHASE_0_REPORT.md` §6 and §8.

The verdict below covers what this audit was asked to settle. H-1, H-2 and H-3 were confirmed, fixed at the root and covered by deterministic PostgreSQL regressions that fail on the original code. No Critical or High job-system defect is known to remain, and every required local gate and GitHub Actions job is green. It authorizes nothing by itself: merge, tag and closure follow review of PR #7.

APPROVE FOR PHASE 0 FINALIZATION
