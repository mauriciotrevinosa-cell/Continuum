# Phase 0 Report

**Status:** implementation, integrated verification and the final concurrency closure audit (H-1/H-2/H-3) complete; PR #7 review pending.  
**Recommendation:** **DO NOT TAG** `continuum-phase-0` until PR #7 is reviewed, approved and merged, CI is green on merged `master`, a final local smoke test passes and closure is explicitly decided.  
**Branch:** `phase-0/integrated-candidate`  
**Integrated production-code merge:** `5e99d42fa1bc202005c80d2beeb84081ffdc9821`  
**Latest production-code commit:** `81aa80d4520b88dfb58418e8311a487cc1ce9369` (ownership guard, final audit H-1/H-2/H-3)  
**Report date:** 2026-09-03, updated 2026-09-13  
**Environment:** Windows 11 (`10.0.26200`), repository at `C:\Continuum` and data at `C:\ContinuumData` (both outside OneDrive/cloud sync), PostgreSQL + pgvector healthy on `127.0.0.1:5433`, Windows Developer Mode enabled.

---

## 1. Current verdict

Phase 0 is no longer blocked by the two concurrency defects from the second independent audit. Both remediations were implemented on isolated branches from the exact rejected candidate `9629a729b1f97de3816d5819bacd676ec70d6f1c`, then merged without production-file overlap into `phase-0/integrated-candidate`.

The integrated candidate has been exercised locally against live PostgreSQL. The combined concurrency suites passed, the full pytest suite returned exit code `0`, and all Python and web quality gates passed. One Windows run still skips the intentionally POSIX-only traversal case; the Windows symlink/junction cases are no longer privilege-blocked because Developer Mode is enabled.

**2026-09-13 update.** The final closure audit tested the three open ownership hypotheses (H-1, H-2, H-3) against the candidate. All three were **real defects**, reproduced deterministically on live PostgreSQL: a worker that had lost its job could still record progress, extend the new owner's lease and mark the job SUCCEEDED; a handler exception after the loss wrote failure state onto the new owner's job; and transitions applied stale in-memory state. The latter included an API resume that reopened a terminal CANCELLED job. They were fixed at the root in `81aa80d`: every worker-owned write now proves ownership under the job row lock in the same transaction, and `transition()` itself refuses stale state. Permanent regression tests fail on the original code and pass on the fix. Details, gate outputs and the verdict are in `docs/PHASE_0_FINAL_CONCURRENCY_AUDIT.md`.

This report does **not** by itself close Phase 0. No Phase 0 tag is authorized before PR #7 is reviewed and merged and the closure decision is made (§8).

---

## 2. Integrated remediation lineage

### Second-audit C-1 — stale reaper snapshot vs fresh live lease

Second audit severity: **Critical**.

Implementation branch: `phase-0/fix-lease-race`  
Commit: `a36242af23b6f8098ff78d76ca94cd798c6f633f`

The remediation:

- makes expired-lease selection a PostgreSQL row-locking operation using `FOR UPDATE SKIP LOCKED`;
- re-verifies RUNNING/expiry state while holding the row lock;
- makes `renew_lease()` capable of atomically requiring RUNNING state and the current `lease_owner`;
- makes `LeaseHeartbeat` surface/refuse lost ownership instead of swallowing it forever;
- makes execution stand down without writing job status when ownership is known lost;
- adds permanent real-PostgreSQL adversarial coverage in `tests/acceptance/test_110_06_11_lease_concurrency.py`.

The implementation branch reported `208 passed, 1 skipped, 0 failed` before integration, with ruff, formatting, mypy strict, and all four import contracts clean.

### Second-audit C-2 — concurrent dependency inserts can form a cycle

Second audit severity: **High**.

Implementation branch: `phase-0/fix-dependency-race`  
Commit: `f405a3a370be5f8262d39f1df1d67aadadc4215b`

The remediation serializes dependency-graph mutation across PostgreSQL transactions with a transaction-scoped advisory lock covering both reachability check and edge insertion. This prevents individually valid-looking concurrent mutations such as `A -> B` and `B -> A` from jointly committing a cycle.

Permanent PostgreSQL concurrency coverage was added in `tests/acceptance/test_110_11_dependency_concurrency.py`, including opposing two-node insertion, concurrent three-edge cycle, valid DAG, and post-rejection graph usability.

### Integration

Merge commit: `5e99d42fa1bc202005c80d2beeb84081ffdc9821`

Its two parents are exactly:

- Claude lease remediation: `a36242af23b6f8098ff78d76ca94cd798c6f633f`
- Codex dependency remediation: `f405a3a370be5f8262d39f1df1d67aadadc4215b`

The two engineers modified separate production areas (`lease.py`/`execution.py` vs `queue.py`) and separate new concurrency-test files.

### Final audit H-1 / H-2 / H-3 — worker writes after ownership loss

Severity: H-1 **Critical**, H-2 **High**, H-3 **High**. All three were reproduced deterministically against `bc7836f` and fixed in `81aa80d4520b88dfb58418e8311a487cc1ce9369`.

- **Violated invariant:** no worker-owned mutation after ownership has been lost; one writer of `status` (ADR-0002 §4–5).
- **Root causes:**
  - post-unit progress/checkpoint writes had no ownership check;
  - `renew_lease()` was called without `worker_id`;
  - the final `SUCCEEDED` was written unchecked;
  - the handler-exception path wrote failure state unchecked;
  - `transition()` validated only the caller's in-memory object. Sessions use `expire_on_commit=False`, so stale views are normal.
- **Root fix:**
  - `lock_job()` (`FOR NO KEY UPDATE`).
  - `transition()` refuses a non-owner (`owner=`) or stale state (`JobOwnershipLostError` / `StaleJobStateError`) before writing.
  - `fail_job`/`block_job` prove ownership before bookkeeping.
  - `renew_lease()` requires `worker_id`.
  - `execute_job()` begins each worker-owned transaction (plan, step start, completion with lease renewal, failure, final status) with a locked ownership proof held until commit.
  - Worker BLOCKED paths use the same guard.
  - The request-applier and dependency-release passes lock rows as they select them.
  - The unused unguarded `touch_progress()` was removed.
- **Permanent coverage:**
  - `tests/acceptance/test_110_06_11_ownership_finalization.py` (13 PostgreSQL tests, forced by hooks and events, no sleeps);
  - `tests/invariants/test_worker_ownership_contract.py` (3 static checks).
  - 14 of these 16 fail against the original production code; the other 2 are a preservation test and a regression guard. All 16 pass on the fix.

Full record: `docs/PHASE_0_FINAL_CONCURRENCY_AUDIT.md`.

---

## 3. Integrated local verification — 2026-09-03

The following was run from `C:\Continuum` on `phase-0/integrated-candidate` with live PostgreSQL.

| Gate | Command | Result |
|---|---|---|
| Exact candidate | `git rev-parse HEAD` | `5e99d42fa1bc202005c80d2beeb84081ffdc9821` before this documentation-only update |
| PostgreSQL | `docker compose ps` | `continuum-db` healthy, pgvector/pgvector:pg16, `127.0.0.1:5433->5432` |
| Migration | `uv run alembic upgrade head` | exit 0 |
| Combined new concurrency suites | `uv run pytest tests/acceptance/test_110_06_11_lease_concurrency.py tests/acceptance/test_110_11_dependency_concurrency.py -q` | 100%, no failures |
| Full Python suite | `uv run pytest -q` | exit code `0`; one expected POSIX-only skip visible on Windows; no failures |
| Ruff | `uv run ruff check .` | `All checks passed!` |
| Format | `uv run ruff format --check .` | `98 files already formatted` |
| Mypy | `uv run mypy packages apps workers` | `Success: no issues found in 49 source files` |
| Import contracts | `uv run lint-imports` | `Contracts: 4 kept, 0 broken.` |
| Web lint | `corepack pnpm --filter @continuum/web lint` | `No ESLint warnings or errors` |
| Web typecheck | `corepack pnpm --filter @continuum/web typecheck` | `tsc --noEmit`, exit 0 |
| Web build | `corepack pnpm --filter @continuum/web build` | `Compiled successfully`; production build completed |

The FastAPI/Starlette test client emitted a deprecation warning recommending direct `httpx` use. It is not an acceptance failure and is intentionally not changed in this candidate merely to silence a warning.

### Final concurrency closure audit — 2026-09-13

Run on `81aa80d` with live PostgreSQL (`continuum-db`, pgvector pg16, healthy on `127.0.0.1:5433`):

| Gate | Result |
|---|---|
| `uv run alembic upgrade head` | exit 0; `0001_phase0 (head)` |
| `uv run pytest -q` | exit 0; **315 passed, 1 skipped** (POSIX-only traversal case) |
| `uv run pytest tests/acceptance/test_110_06_11_lease_concurrency.py tests/acceptance/test_110_06_11_durable_jobs.py -q -ra` | 30 passed, 0 skipped |
| All job suites (lease, durable, ownership, dependency, remediation) | 70 passed, 0 skipped |
| Windows path suites | 52 passed, 1 skipped (POSIX-only) |
| Offline (empty environment): providers + invariants | 60 passed |
| `ruff check` / `ruff format --check` / `mypy packages apps workers` / `lint-imports` | clean / 138 formatted / no issues in 56 files / 4 kept, 0 broken |
| `pnpm install --frozen-lockfile`, `lint`, `typecheck`, `test`, `build:web` | all pass (5 web tests) |
| OpenAPI regeneration | zero drift |
| GitHub Actions on `81aa80d` | runs `34774312398` (push) and `34774315586` (pull_request): all five jobs success |

---

## 4. Acceptance matrix — Master Plan §110

This is the integrated-candidate **local verification** state, not the final independent-audit verdict.

| # | Requirement | Current result | Evidence / note |
|---|---|---|---|
| 110.1 | Clean setup / migrations / boot | **PASS** | Docker/PostgreSQL healthy; migration command green. |
| 110.2 | Web UI can call API health | **PASS** | Previously independently exercised; health/API tests remain green and web build passes. |
| 110.3 | Vault path normalization | **PASS** | Existing acceptance coverage remains green. |
| 110.4 | Traversal / symlink / junction escape | **PARTIAL** | All Windows-relevant traversal, symlink and junction cases have executed successfully with Developer Mode enabled; one POSIX-only case remains skipped on Windows. |
| 110.5 | Source Vault immutable | **PASS** | Existing structural and behavioral acceptance coverage remains green. |
| 110.6 | Durable job queued and processed | **PASS** | Lease/reaper suite plus the final-audit ownership suite (stale-worker completion, lease extension and final-status races refused) green on PostgreSQL and in CI. |
| 110.7 | Durable progress independent of UI | **PASS** | Existing PostgreSQL-backed coverage remains green. |
| 110.8 | UI/API restart does not cancel worker | **PASS** | Existing standalone-worker/process-boundary coverage remains green. |
| 110.9 | Graceful stop / pause / drain resumable | **PASS** | Worker-owned state transition remediation remains green. |
| 110.10 | Resume only unfinished / idempotent effect | **PASS** | Existing post-effect crash and forced rerun coverage remains green. |
| 110.11 | Structured failure / retry / lease recovery | **PASS** | Stale-reaper race (C-1) and stale-worker failure/finalization races (H-1/H-2/H-3) covered adversarially; reaped work proven recoverable by a second worker. |
| 110.12 | Fake providers / no cloud credentials | **PASS** | Existing FREE_LOCAL/provider coverage remains green. |
| 110.13 | No secret leakage | **PASS** | Existing logging/redaction coverage remains green. |
| 110.14 | Migration strategy / round trip | **PASS** | Previously executed against live PostgreSQL; current migration to head green. |
| 110.15 | Required docs before tag | **PASS** | Required docs exist; final concurrency closure audit recorded in `docs/PHASE_0_FINAL_CONCURRENCY_AUDIT.md`. Independent review of PR #7 still required before tag. |

**Tally: 14 PASS · 1 PARTIAL (110.4 cross-platform coverage) · 0 NOT RUN · 0 FAIL.**

---

## 5. Environment blockers from earlier reports

| Earlier blocker | Current state |
|---|---|
| Docker/PostgreSQL unavailable | **RESOLVED.** `continuum-db` is healthy. |
| Repository/data under OneDrive | **RESOLVED.** `C:\Continuum` and `C:\ContinuumData` are outside cloud sync. |
| Windows Developer Mode disabled | **RESOLVED.** Developer Mode is enabled; Windows symlink tests have executed. |
| Port 8000 occupied | Cosmetic/local environment issue only; alternate loopback port may be used for live API runs. |
| Docker Desktop failing to start (2026-09-13) | **RESOLVED locally.** Stale Windows AF_UNIX socket files could not be removed by Docker. Moving the stale socket directories aside let the engine start; no volume or data was affected. |

The previous report's `190 passed, 6 skipped` and Developer-Mode-disabled statements are obsolete and must not be used as current evidence.

---

## 6. Scope compliance

No Phase 1+ production feature was added by either concurrency remediation, their integration, or the H-1/H-2/H-3 ownership fix.

**Scope note for the closure decision (2026-09-13).** By explicit instruction, the PR #7 branch also carries product work beyond this foundation list:
- Library Acquisition (read-only library coverage over the Source Vault);
- a read-only media viewer addressed by opaque ids;
- a generic Project workspace for Markdown story documents;
- the Story Room creative documents from `master`.

That work touches no job-system code and adds no database table. The Source Vault stays read-only. Finalization gate item 7 below ("no Phase 1 work has entered the candidate") therefore needs an explicit decision by the reviewers, not an assumption.

The list below describes the Phase 0 foundation as originally scoped:

- Vault/Library ingestion UI and scanners;
- media reader/parsing;
- source intelligence/RAG;
- canon/character/project/world/story systems;
- power synchronization;
- Visual Lab;
- image/video/audio generation;
- voice systems;
- The Arrivals runtime/story implementation.

Phase 0 remains foundation-only: storage boundaries, API/web shell, PostgreSQL durable state, workers/jobs/checkpoints/recovery, providers/privacy metadata, observability, migrations, tests, and operational documentation.

---

## 7. Explicit final-audit review point

During integration review, one call site in `packages/jobs/src/continuum_jobs/execution.py` was noted for adversarial examination: after a unit commits successfully, the code calls `renew_lease(session, job.id, lease_seconds)` without supplying `worker_id`.

**Resolved 2026-09-13: DEFECT, fixed.** The unguarded renewal did let a worker that had lost its job extend the new owner's lease. It was one of several unguarded post-unit writes: progress, checkpoint, final `SUCCEEDED`, and failure state on handler exceptions. `test_a_stale_worker_cannot_extend_the_new_owners_lease` reproduced it deterministically ("stale worker moved B's lease").

`renew_lease()` now requires `worker_id`, and the renewal runs inside the completion transaction after a locked ownership proof. See §2 ("Final audit H-1 / H-2 / H-3") and `docs/PHASE_0_FINAL_CONCURRENCY_AUDIT.md`.

---

## 8. Finalization gate

Before creating `continuum-phase-0`, all of the following must be true:

1. final auditor checks the exact current candidate SHA, not a moving branch;
2. second-audit C-1 and C-2 adversarial scenarios pass independently on PostgreSQL;
3. the ownership-review point in §7 is explicitly cleared or fixed;
4. full Phase 0 tests and quality gates remain green;
5. 110.4's remaining POSIX-only coverage is either executed on POSIX/CI or explicitly accepted as platform-specific coverage;
6. no unresolved critical/high Phase 0 defect remains;
7. no Phase 1 work has entered the candidate;
8. only then may the immutable `continuum-phase-0` tag be created.

Status on 2026-09-13 (candidate branch, before PR #7 review):

| # | Condition | Status |
|---|---|---|
| 1 | exact candidate SHA audited | production code `81aa80d`; the audit document names it and is a documentation-only descendant |
| 2 | C-1 and C-2 scenarios pass on PostgreSQL | yes (lease-concurrency and dependency-concurrency suites green locally and in CI) |
| 3 | ownership review point (§7) cleared or fixed | **fixed** (H-1/H-2/H-3) |
| 4 | full tests and quality gates green | yes, locally with PostgreSQL and in GitHub Actions |
| 5 | 110.4 POSIX-only coverage | skipped on Windows by marker; intended to run on the Ubuntu CI job |
| 6 | no unresolved Critical/High defect | none known |
| 7 | no Phase 1 work in the candidate | **needs a reviewer decision**: see the scope note in §6 |
| 8 | tag | not created |

After review: PR #7 approval and merge, green CI on merged `master`, final local smoke test, explicit closure decision. Until those conditions are met: **DO NOT TAG, DO NOT START PHASE 1.**
