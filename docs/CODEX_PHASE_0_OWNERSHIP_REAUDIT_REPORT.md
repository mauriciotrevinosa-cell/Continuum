# Phase 0 — Independent Re-Audit of the Stale-Worker Ownership Remediation

| | |
|---|---|
| **Candidate under audit** | `388d30085bfdc5e3c35b5d47ac6ad66f199991b6` |
| **Audit branch** | `audit/codex-phase-0-ownership-388d300` |
| **Audit worktree** | `C:\Continuum-Codex-Audit` (isolated) |
| **Database** | `continuum_codex_ownership_audit` (isolated) |
| **Data root** | `C:/ContinuumData-Codex-Ownership-Audit` (isolated) |
| **Date** | 2026-09-05 |
| **Production code modified** | None. Working tree contains only `audit_artifacts/` and this report. |

---

## VERDICT

**REJECT — DO NOT TAG**

Three defects were found in the candidate, all of them violations of the very
invariant the remediation was written to establish. All three are reproduced
deterministically against real PostgreSQL, with no sleeps and no weakened
assertions.

---

## Disclosure: this audit is not fully independent

**I wrote the remediation being audited.** An audit performed by the same agent
that produced the code does not have the property the review process assumes:
I share the blind spots of the implementation, and a defect I failed to imagine
while writing the fix is a defect I may fail to imagine while auditing it.

This is stated first because it bears on how the CLEARED results below should
be read. The three DEFECT results are load-bearing — a reproduction that fails
is evidence regardless of who wrote it. The three CLEARED results are weaker
evidence than they would be from a genuinely separate auditor, and should be
treated as "no violation found by these probes" rather than "proven correct."

To reduce the correlation as far as the setting allows, H-1/H-2/H-3 were
**reconstructed from the stated invariant** rather than copied from the
remediation's own suite, and were not taken on the implementer's word that the
prior audit artifacts had been ported faithfully. Ownership transfer in every
test goes through the **real** reaper and claim paths (`reap_expired_leases`
then `claim_next_job`), never through a hand-written `UPDATE` that fakes a
handover.

---

## The invariant under test

> No worker may mutate durable job coordination state, progress state, or final
> status after it no longer owns the current RUNNING lease. Ownership validation
> and the mutation must occur within a single PostgreSQL serialization unit.

---

## Findings

### H-1 — CLEARED

*Hypothesis: a stale worker can finalize or write to a job after the lease has
been reclaimed.*

**Serialization reasoning.** `transition()` performs
`SELECT ... FOR UPDATE` with `populate_existing=True` (`lock_job_row`), so the
row is both locked and re-read from durable storage; the ownership comparison
against `job.lease_owner` and the subsequent status write then occur under a
lock held to the end of the caller's transaction. Validation and mutation are
therefore one serialization unit. Independently, `renew_lease()` carries
`status = RUNNING AND lease_owner = :worker` in the `WHERE` clause of a single
`UPDATE`, which is atomic by construction and returns `False` rather than
touching the row when the predicate fails.

**Evidence.** Reclaim forced while worker A is suspended inside its only unit;
full durable snapshot captured immediately after the handover, compared byte-
for-byte after A resumes and exits. A returns `StopReason.OWNERSHIP_LOST`,
raises nothing, and the snapshot is unchanged. A second probe confirms a stale
worker cannot renew the new owner's lease.

### H-2 — CLEARED

*Hypothesis: a stale worker whose unit raises can write failure state onto the
new owner's job.*

Ownership loss dominates the exception path: the failure is discarded rather
than recorded, because a worker that no longer owns the job has no standing to
declare it failed. Verified that no step failure, no `attempt` increment, no
`last_error`, no `error_history` entry and no job-level failure is written.

### H-3 — CLEARED

*Hypothesis: some transition path remains reachable without an ownership check.*

The check is **default-on rather than opt-in**: in `transition()`, a caller that
identifies itself with `worker_id` while targeting any status other than
`RUNNING` has `expected_owner` inferred automatically. This is the structurally
important part of the fix — an opt-in `require_owner` would leave every present
and future call site one forgotten keyword away from reintroducing the defect.
Verified across finalization, failure, BLOCKED, pause and cancel: each raises
`OwnershipLostError`, and a stale in-memory ORM object cannot overwrite durable
state because `lock_job_row` re-reads with `populate_existing`.

### H-4 — DEFECT (High)

*The window between the pre-unit ownership check and the step-start commit is
unguarded.*

**Location.** `packages/jobs/src/continuum_jobs/execution.py:238-256`

```python
stop = _stop_requested(session, job, worker_id)   # unlocked session.refresh()
...
step = session.execute(select(JobStep)...).scalar_one()
step.status = StepStatus.RUNNING
step.started_at = dt.datetime.now(dt.UTC)
step.attempt += 1
session.commit()                                  # no ownership predicate
```

**Why it is not one serialization unit.** `_stop_requested()` reads via
`session.refresh(job, attribute_names=[...])`, which takes **no lock**. Nothing
is held between that read and the `commit()` three statements later, so
ownership can change in between. The step mutation itself carries no ownership
predicate of any kind.

**Reproduction** (`audit_artifacts/test_ownership_reaudit.py::test_h4_pre_unit_window_cannot_write_step_state_after_ownership_loss`):
worker A is released past the ownership check and suspended before the step
commit; the lease is then reclaimed by worker B through the real reaper.

```
before: steps [('unit-0', PENDING, 0, False)]
after:  steps [('unit-0', RUNNING, 1, True)]     # owner at the time was B
```

**Impact.** A non-owner stamps `status`, `started_at` and `attempt` on the
rightful owner's step row. The blast radius is bounded but real: `job.attempt`
— which drives the `max_attempts` failure budget — is **not** affected, so this
does not by itself fail a job prematurely. `step.attempt` is, however, read by
handlers to make retry decisions (the shipped synthetic handler branches on it
at `workers/runner/src/continuum_worker/handlers/synthetic.py:159`), so an
inflated count causes the rightful owner's handler to take a different branch
than the one its real attempt history warrants. `started_at` is clobbered
outright. This is a direct violation of the stated invariant, which is absolute
about coordination and progress state.

### H-5 — DEFECT (High)

*The entire planning phase runs before any heartbeat exists and is never
re-validated.*

**Location.** `packages/jobs/src/continuum_jobs/execution.py:223-225`

```python
units = list(handler.plan(ctx))
plan_units(session, job, units)   # creates JobStep rows, sets units_total
session.commit()                   # no ownership check, before any heartbeat
```

**Why it is not one serialization unit.** There is no ownership predicate at
all on this path, and `LeaseHeartbeat` is not started until after the first
step commit — so for the whole duration of `plan()`, which is unbounded
handler-controlled time, the lease is neither being renewed nor being checked.
A slow plan is therefore *expected* to outlive its lease, not merely able to.

**Reproduction** (`::test_h5_planning_window_cannot_write_after_ownership_loss`):

```
before: units_total None, steps []
after:  units_total 3,    steps [unit-0, unit-1, unit-2 all PENDING]   # owner was B
```

**Impact.** A non-owner writes `JobStep` rows and `units_total` onto another
worker's job. The consequence outlives the moment because of how `plan_units`
is written: it **skips unit keys that already exist** and only ever **grows**
`units_total`. So if the rightful owner's plan differs from the stale worker's
— non-deterministic planning, or planning that reads state which changed during
the handover — the stale plan is silently pinned in place and the rightful
owner executes it. Worse, if the owner plans *fewer* units than the stale
worker did, `units_total` stays at the larger stale value while the owner only
ever completes its own smaller set, leaving `units_done < units_total`
permanently and the completion accounting inconsistent.

### H-5b — DEFECT (High) — found during this audit, not previously hypothesized

*A stale worker whose `plan()` raises crashes the worker process instead of
standing down.*

**Location.** `packages/jobs/src/continuum_jobs/execution.py:226-229`

```python
except Exception as exc:
    fail_job(session, job, _structured(exc), worker_id=worker_id)
```

A planning exception is funnelled into `fail_job`. Under the new default-on
ownership rule, if the lease was reclaimed during `plan()`, that `fail_job`
call **itself** raises `OwnershipLostError` — from inside the `except` block —
and the error escapes `execute_job()` entirely.

**This is the exact failure mode the remediation's own docstring claims to
prevent.** That comment argues the ownership check must raise
`OwnershipLostError` rather than let `IllegalTransitionError` "escape
`execute_job()` and crash the worker." On this path the fix swapped one
escaping exception for another.

**Reproduction** (`::test_h5b_stale_worker_failing_to_plan_stands_down_without_crashing`):

```
execute_job propagated OwnershipLostError instead of standing down:
[OwnershipLostError('This worker no longer owns the job and must not transition it.')]
```

**Impact — availability, and it is not contained.** The worker loop catches only
`UnknownJobTypeError` and `SyntheticBlockedError` around `execute_job`
(`workers/runner/src/continuum_worker/main.py:143,174`), and the outer
`run_forever` loop is `try/finally` with **no `except`**
(`workers/runner/src/continuum_worker/main.py:219-227`). The exception therefore
terminates the worker process. A routine, fully expected race — a slow plan
whose lease is reaped, which then fails — takes down the whole worker rather
than yielding the job to its rightful owner.

### Deadlock / lock-inversion probe — CLEARED

Concurrent reaper activity against jobs expiring under an executing worker
produced no deadlock, no lock inversion and no `IllegalTransitionError`. All 24
state-machine invariant tests pass, so no previously-valid transition was
turned invalid by the ownership rule.

---

## Gate results at `388d3008`

| Gate | Result |
|---|---|
| Shipped test suite | **226 passed, 1 skipped, 0 failed** (227 collected; the skip is POSIX-only) |
| Audit artifacts | **7 passed, 3 failed** (10 total) — every failure is a confirmed production defect |
| Claude's ownership suite | 11 / 11 pass |
| C-1 lease concurrency suite | 13 / 13 pass |
| C-2 dependency concurrency suite | 7 / 7 pass |
| `ruff check` (production) | clean |
| `ruff format --check` (production) | clean (68 files) |
| `mypy --strict` | clean (49 files) |
| `import-linter` | 4 / 4 contracts kept |
| Alembic | single head `0001_phase0`; `downgrade base` verified to leave only `alembic_version`, `upgrade head` verified to restore all six tables |
| web lint | no ESLint warnings or errors |
| web typecheck | clean |
| web build | succeeds |

The shipped suite is fully green. **That is precisely the problem**: the three
defects sit in windows the shipped suite does not probe, so a green suite is
not evidence of the invariant holding.

The seven ruff findings initially reported were traced to the audit artifact
file written during this audit, not to production; production was clean before
and after. They were formatted rather than reported as a finding.

---

## Required before this candidate can be tagged

1. **H-4** — bring the pre-unit ownership check and the step-start write into
   one serialization unit. The check must take a row lock (or the step write
   must carry an ownership predicate) such that no window exists between
   proving ownership and committing the step mutation.
2. **H-5** — re-validate ownership after `plan()` returns and before
   `plan_units`/`commit` lands, within the same locked transaction; or start
   the lease heartbeat before planning so a long plan cannot silently outlive
   its lease. Both are likely wanted: the heartbeat narrows the window, the
   post-plan check closes it.
3. **H-5b** — `execute_job` must not let `OwnershipLostError` escape. Losing
   the lease is a stand-down (`StopReason.OWNERSHIP_LOST`), not a crash, on
   *every* path including the planning `except`. Adding a catch in the worker
   loop would mask the symptom; the stand-down belongs in `execute_job`, where
   the other paths already implement it.
4. Re-run this audit's artifacts. All ten must pass **without modification to
   the tests**.

Fixes must be root fixes in the ownership model, not patches to the three
reproductions.

---

## Scope not audited

Vault immutability, Library, Story systems, Phase 1, the dependency-graph
concurrency work (C-2, verified only as a regression check), and performance
characteristics. This audit covered the stale-worker ownership model and its
interaction with the lease, reaper, state machine and worker loop.
