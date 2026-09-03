# Phase 0 Final Audit Handoff

**Purpose:** independent final attempt to falsify Phase 0 before tagging.  
**Target branch:** `phase-0/integrated-candidate`  
**Production-code integration merge:** `5e99d42fa1bc202005c80d2beeb84081ffdc9821`  
**Important:** the branch may contain documentation-only descendants of that merge. Before auditing, fetch and record the exact current branch HEAD; audit that immutable SHA.

## Auditor role

Act as an auditor, not an implementer.

- Do not change production code while auditing.
- Do not weaken tests.
- Do not start Phase 1.
- Do not create `continuum-phase-0`.
- If a defect is found, report a deterministic reproduction, severity, violated invariant/ADR, and a root-fix direction. Stop before implementing unless explicitly reassigned later.

## Authority order

1. `docs/FOUNDATION_APPROVAL.md`
2. approved ADRs
3. architecture review / Phase 0 coordination docs
4. Master Plan §109/§110 for phase order and acceptance

Read at minimum:

- `docs/FOUNDATION_APPROVAL.md`
- `docs/PHASE_0_ACCEPTANCE_CHECKLIST.md`
- `docs/PHASE_0_REPORT.md`
- `docs/CODEX_PHASE_0_AUDIT.md`
- historical first audit report
- historical second audit report from branch `audit/codex-phase-0-9629a72`
- relevant ADRs, especially ADR-0002

## Historical rejection that must be independently retested

The second audit rejected candidate `9629a729b1f97de3816d5819bacd676ec70d6f1c` for two PostgreSQL concurrency defects.

### C-1 — stale reaper snapshot can overwrite a fresh live lease

Remediation lineage:

- branch `phase-0/fix-lease-race`
- commit `a36242af23b6f8098ff78d76ca94cd798c6f633f`
- permanent suite `tests/acceptance/test_110_06_11_lease_concurrency.py`

Audit the invariant, not merely the shipped tests. Attempt adversarial interleavings around:

- renewal vs reaper;
- two reapers;
- ownership transfer/loss;
- long units;
- heartbeat transient vs persistent failure;
- reaped job followed by stale worker activity;
- second-worker claiming behavior.

### C-2 — concurrent dependency mutations can jointly commit a cycle

Remediation lineage:

- branch `phase-0/fix-dependency-race`
- commit `f405a3a370be5f8262d39f1df1d67aadadc4215b`
- permanent suite `tests/acceptance/test_110_11_dependency_concurrency.py`

Attempt at minimum:

- simultaneous opposing edges;
- three-node concurrent cycle;
- deeper concurrent cycle patterns;
- valid concurrent DAG mutations;
- rollback/retry after rejected mutation;
- lock release and graph usability after failure.

The implementation uses a PostgreSQL transaction-scoped advisory lock. Verify the locking scope actually covers the reachability decision and insert through commit/rollback semantics.

## Explicit ownership question that must be answered

`packages/jobs/src/continuum_jobs/execution.py` contains a post-unit call equivalent to:

```python
renew_lease(session, job.id, lease_seconds)
```

without passing `worker_id`, even though `renew_lease()` now supports an ownership-guarded form.

Do **not** assume this is a bug and do **not** assume it is safe because tests pass.

Determine whether a deterministic interleaving can cause the executing worker, after losing ownership between unit completion and that renewal, to extend a lease it no longer owns or otherwise interfere with the rightful owner/reaper. Consider transaction boundaries, the unit completion commit, heartbeat lifetime, status/owner changes, and when the next `_stop_requested()` check occurs.

Required audit result for this point:

- **CLEARED:** explain the exact invariant/serialization reason it cannot violate ownership, ideally backed by an adversarial test; or
- **DEFECT:** provide a deterministic PostgreSQL reproduction and severity.

## Required gates

Run against live PostgreSQL/pgvector and record exact outputs:

```text
git fetch --all --prune
git rev-parse HEAD
git status --short
docker compose ps
uv run alembic current
uv run alembic heads
uv run alembic downgrade base
uv run alembic upgrade head
uv run pytest -q
uv run pytest tests/acceptance/test_110_06_11_lease_concurrency.py tests/acceptance/test_110_11_dependency_concurrency.py -q -ra
uv run ruff check .
uv run ruff format --check .
uv run mypy packages apps workers
uv run lint-imports
corepack pnpm --filter @continuum/web lint
corepack pnpm --filter @continuum/web typecheck
corepack pnpm --filter @continuum/web build
```

Also rerun the relevant path/vault suites. On Windows with Developer Mode enabled, all Windows symlink/junction cases should execute; a POSIX-only case may remain platform-skipped and must be reported honestly.

## Final report format

Create an audit report on a dedicated audit branch containing:

1. exact audited SHA;
2. environment actually observed;
3. §110 acceptance tally;
4. each historical finding retested independently;
5. explicit verdict on the post-unit ownership question;
6. all commands/gate outputs;
7. new findings ranked Critical / High / Medium / Low;
8. final verdict exactly one of:
   - `APPROVE FOR PHASE 0 FINALIZATION`, or
   - `REJECT — DO NOT TAG`.

Approval means no unresolved Critical/High Phase 0 defect remains and all required gates are green. It does **not** authorize Phase 1 by itself; merge/tag/finalization happens only after review of the audit report.
