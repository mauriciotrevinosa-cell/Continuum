# Codex Second Independent Phase 0 Audit Report

**Exact audited SHA:** `9629a729b1f97de3816d5819bacd676ec70d6f1c`  
**Source branch:** `phase-0/remediation`  
**Audit branch:** `audit/codex-phase-0-9629a72`  
**Audit date:** 2026-09-01  
**Final verdict:** **REJECT**

The statement `PHASE 0 CANDIDATE APPROVED FOR FINALIZATION` is intentionally
not made. Two PostgreSQL concurrency defects violate accepted Phase 0 durable
job invariants. No production code was changed, no Phase 1 work was added, and
the `continuum-phase-0` tag was not created.

## Environment Actually Observed

- Windows NT `10.0.26200.0`, Windows Home
- Repository: `C:\Continuum`, outside OneDrive/cloud sync
- Audit data root supplied explicitly as `C:\ContinuumData`, outside cloud sync
- Docker Desktop `4.88.1`; Docker Engine `29.7.2`
- `continuum-db` healthy, `pgvector/pgvector:pg16`, exposed only at `127.0.0.1:5433`
- Python `3.12.10` through `uv 0.11.27`
- Node `v24.15.0`; pnpm `9.15.4` through Corepack
- Windows Developer Mode registry value `AllowDevelopmentWithoutDevLicense=1`
- Candidate SHA was verified after `git fetch --all --prune`; the audit branch
  was created directly from that SHA and did not audit moving HEAD.

## Acceptance Tally

**12 PASS, 1 PARTIAL, 0 NOT RUN, 2 FAIL.**

| Section 110 item | Result | Independent evidence |
|---|---|---|
| 110.1 clean setup/migrations/boot | **PASS** | PostgreSQL healthy; `downgrade base -> upgrade head` executed twice; one Alembic head. |
| 110.2 API health/web | **PASS** | Health/readiness suite and web lint/typecheck/build passed. |
| 110.3 path normalization | **PASS** | Full path-normalization suite passed. |
| 110.4 traversal/symlink/junction | **PARTIAL** | Every Windows case, including symlink and junction escapes, passed. One POSIX-only test skipped on Windows. |
| 110.5 Source Vault immutability | **PASS** | Structural and behavioral tests passed; the audit performed no vault write probe. |
| 110.6 durable queue processing | **FAIL** | A live heartbeat can be overwritten by a stale reaper snapshot, making the job concurrently claimable. |
| 110.7 durable progress | **PASS** | PostgreSQL-backed cross-session progress test passed. |
| 110.8 UI/API independence | **PASS** | Standalone worker/process-boundary tests passed. |
| 110.9 pause/drain/resume | **PASS** | Flag ownership, worker application, pause/resume and drain/resume tests passed. |
| 110.10 crash resume/idempotent effect | **PASS** | Audit launched a real worker that died after effect landing; replacement completed with one step, attempt 2, `already_present=True`, and the same verified artifact. |
| 110.11 failure/retry/lease recovery | **FAIL** | Reaper race reproduced against real PostgreSQL; live work was moved from `RUNNING` to `QUEUED` after a newer lease committed. |
| 110.12 providers/privacy/FREE_LOCAL | **PASS** | Fake/provider suite and end-to-end BLOCKED path passed. |
| 110.13 secret logging | **PASS** | Exact-value and pattern-redaction tests passed. |
| 110.14 migrations/schema | **PASS** | Upgrade/downgrade/upgrade succeeded; schema and single-head checks passed. |
| 110.15 documents | **PASS with documentation defect** | Required files exist, but `PHASE_0_REPORT.md` contains stale environment/results claims described below. |

## Findings

### C-1: Fresh live lease can be reaped from a stale snapshot

**Severity:** Critical  
**Classification:** code defect and missing concurrency test  
**Status:** reproducibly failed against PostgreSQL

`reap_expired_leases()` selects stale jobs without `FOR UPDATE`, a conditional
update, or a lease-owner/version comparison at
`packages/jobs/src/continuum_jobs/lease.py:194`. It decides from that snapshot
and later writes `QUEUED`. Concurrently, `renew_lease()` updates solely by job
ID at `packages/jobs/src/continuum_jobs/lease.py:86`; it does not require the
job to remain `RUNNING` or owned by the heartbeating worker.

The audit probe locked the row, wrote a future lease, and held the transaction.
The reaper read the previously committed expired lease and blocked only when it
tried to flush. After the fresh lease committed, the reaper resumed and
overwrote it: observed status `QUEUED`, expected `RUNNING`.

This violates F-27 and ADR-0002 section 5. A second worker can claim and execute
work whose original worker is alive. Content addressing may prevent artifact
corruption, but it does not prevent concurrent duplicate compute or make a
non-content effect safe.

The heartbeat thread also catches all exceptions indefinitely at
`packages/jobs/src/continuum_jobs/lease.py:144` without surfacing loss of lease
to the executing unit. The remediation test proves ordinary periodic renewal,
not safe behavior under renewal/reaper races or persistent heartbeat failure.

**Reproduction:**

```text
uv run pytest audit_artifacts/test_second_audit_concurrency.py::test_fresh_heartbeat_cannot_be_overwritten_by_stale_reaper_snapshot -q
```

### C-2: Concurrent dependency inserts can create a cycle

**Severity:** High  
**Classification:** code defect and missing concurrency test  
**Status:** reproducibly failed against PostgreSQL

`add_dependency()` at `packages/jobs/src/continuum_jobs/queue.py:386` performs a
recursive reachability check and then inserts the edge. Under PostgreSQL's
ordinary transaction isolation, two transactions proposing `A -> B` and
`B -> A` both see the pre-insert graph, both return no cycle, and both commit.
The recursive CTE at `packages/jobs/src/continuum_jobs/queue.py:427` makes the
single-transaction check correct but does not serialize graph mutations.

The audit synchronized the two checks before either insert. Both opposing
edges committed and no exception occurred. This violates ADR-0002 section 9's
requirement that dependencies cannot form cycles. Existing tests cover only
serial self/two/three-node cases and a valid diamond.

**Reproduction:**

```text
uv run pytest audit_artifacts/test_second_audit_concurrency.py::test_concurrent_opposing_dependency_edges_cannot_form_cycle -q
```

### D-1: Phase 0 report is stale and understates executed coverage

**Severity:** Medium  
**Classification:** documentation defect

`docs/PHASE_0_REPORT.md:28`, `:45`, `:151-155`, `:217`, and `:433` state that
Developer Mode is disabled and five symlink tests skip. Developer Mode is now
enabled and all five Windows symlink cases executed successfully. The report
also claims `190 passed, 6 skipped`; the independent counted run observed
`195 passed, 1 skipped`. The remaining skip is POSIX-only, not privilege
related.

## Regression Verification of First-Audit Findings

| First-audit finding | Result | Evidence |
|---|---|---|
| Long-unit lease heartbeat | **FAIL** | Normal two-worker test passes, but adversarial fresh-heartbeat/reaper race fails. Remediation is incomplete. |
| API/worker status ownership | **PASS** | API helpers set flags/events only; worker invokes `apply_pending_requests`; no alternate API status mutation found. |
| Transitive dependency cycles | **FAIL** | Serial deep cycles and valid diamonds pass; concurrent opposing inserts form a cycle. |
| Due retry automatically claimable | **PASS** | PostgreSQL regression test failed once, made due by DB clock, and normal claim returned it `RUNNING`. |
| Retry/reaper DB clock | **PASS** | Behavioral comparison to `SELECT now()` passed; static scan found no worker clock in lease scheduling. |
| Post-effect crash injection | **PASS** | Real subprocess died with step `RUNNING`, effect present, and no completion/checkpoint; replacement resumed to `SUCCEEDED` with one step and `already_present=True`. |
| Blocked provider reaches BLOCKED | **PASS** | End-to-end worker/provider regression passed; it did not become `FAILED_FINAL`. |
| Engine cache scoped by URL | **PASS** | Reachable and unreachable readiness tests passed while live PostgreSQL remained online; distinct settings receive distinct URL-keyed engines. |
| Scoped engine disposal | **PASS** | Full suite passed without unrelated live-pool disposal; targeted readiness isolation tests passed. |

## Gates Executed

```text
git fetch --all --prune
docker version
docker compose ps
uv run alembic current
uv run alembic downgrade base
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
uv run alembic current
uv run alembic heads
uv run pytest tests --override-ini='addopts=' -q -ra
uv run pytest tests/acceptance/test_110_03_path_normalization.py tests/acceptance/test_110_04_traversal.py tests/acceptance/test_110_05_vault_readonly.py -q -ra
uv run pytest tests/acceptance/test_110_06_11_durable_jobs.py tests/acceptance/test_110_11_remediation.py tests/acceptance/test_110_12_providers.py tests/acceptance/test_110_14_migrations.py -q -ra
uv run pytest tests/acceptance/test_110_02_health_and_api.py -q -ra
uv run pytest audit_artifacts/test_second_audit_concurrency.py --override-ini='addopts=' -q -ra
uv run ruff check .
uv run ruff format --check .
uv run mypy packages apps workers
uv run lint-imports
corepack pnpm --filter @continuum/web lint
corepack pnpm --filter @continuum/web typecheck
corepack pnpm --filter @continuum/web build
```

Observed shipped-suite result: **195 passed, 1 skipped, 0 failed**. The only
skip was `test_110_04_traversal.py:135`, explicitly POSIX-only. Observed audit
artifact result: **1 passed, 2 failed**; the real hard-death recovery passed and
both concurrency invariants failed. Ruff, formatting, mypy strict, all four
import contracts, web lint, web typecheck, and web production build passed.

The root pnpm wrapper commands could not locate the pnpm shim on this shell's
`PATH`; the identical workspace scripts were executed successfully through
`corepack pnpm --filter @continuum/web ...`. This is an environment invocation
detail, not a product failure.

## Final Verdict

**REJECT** `9629a729b1f97de3816d5819bacd676ec70d6f1c`.

The candidate clears the prior environment blockers and most remediations are
behaviorally correct. It cannot be approved while a reaper can reclaim a live
heartbeat-renewed job and concurrent dependency inserts can commit a cycle.
Both defects require production fixes plus PostgreSQL concurrency regression
tests, followed by another independent run of the complete Phase 0 gate set.
