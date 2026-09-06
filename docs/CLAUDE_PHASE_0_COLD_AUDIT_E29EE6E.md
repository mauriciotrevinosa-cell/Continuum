# Phase 0 — Cold Final Lifecycle Audit

| | |
|---|---|
| **Production candidate audited** | `e29ee6ec902a252610c9b6a4e028ee7dcbc57fcb` |
| **Audit branch** | `audit/claude-cold-phase-0-e29ee6e` |
| **Audit worktree** | `C:\Continuum-Claude-ColdAudit` (isolated) |
| **Database** | `continuum_claude_cold_e29` (isolated) |
| **Data root** | `C:/ContinuumData-Claude-ColdAudit` (isolated) |
| **Date** | 2026-09-06 |
| **Production code modified** | None. `git diff --stat` against the candidate is empty for `packages`, `apps`, `workers` and `tests`. |
| **Permanent tests modified** | None. |

---

## VERDICT

**REJECT — DO NOT TAG**

Three High defects were found, all deterministic, all reproduced against real
PostgreSQL with ownership handed over through the genuine reaper and claim
paths. Each failed identically on three consecutive full runs of the audit
artifacts.

---

## Disclosure: reduced auditor independence

**The same model family implemented the H-4/H-5/H-5b remediation being audited
here, and I wrote the audit that preceded it.** This is not an independent
audit in the sense the review process assumes: I share the blind spots of the
implementation, and a defect I failed to imagine while writing the fix is one I
may fail to imagine while auditing it.

Two things follow, and they are not symmetric:

* The **DEFECT** findings are strong evidence regardless of authorship — a
  reproduction that fails is a fact.
* The **CLEARED** findings are weaker than they would be from a genuinely
  separate auditor. Read them as "no violation found by these probes", not as
  "proven correct".

To reduce the correlation as far as this setting allows, every hypothesis was
reconstructed from the invariant rather than adapted from the shipped suites,
and every ownership handover uses `reap_expired_leases` followed by
`claim_next_job` — never a direct UPDATE that fakes a final state.

---

## The invariant under test

> A worker that no longer owns the current RUNNING lease must not mutate
> durable state and must not continue acting as the executor of that job.
> Ownership validation and the mutation must be one PostgreSQL serialization
> unit.

Note the second clause. Prior audits tested only the first. **H-6 is the first
finding that turns on "must not continue acting as the executor".**

---

## Lifecycle walk

Ownership transfer was attempted at every boundary:

| Boundary | Result |
|---|---|
| claim → handler resolution | **H-7b DEFECT** |
| handler resolution → plan | covered by H-7b |
| plan (unbounded handler time) | CLEARED (H-5) |
| materialise plan / `units_total` | CLEARED (H-5) |
| pre-unit ownership proof | CLEARED (H-4) |
| step start (`status`/`started_at`/`attempt`) | CLEARED (H-4) |
| **step start → effect start** | **H-6 DEFECT** |
| effect heartbeat | CLEARED (H-1) |
| unit exception | CLEARED (H-2) |
| **BLOCKED exception** | **H-7 DEFECT** |
| completion / checkpoint / progress | CLEARED (H-1) |
| lease renewal between units | CLEARED (H-1) |
| final transition | CLEARED (H-3) |

---

## Findings

### H-1 — CLEARED

Reconstructed independently. A worker suspended inside its only unit, with the
job reclaimed underneath it, returns `StopReason.OWNERSHIP_LOST`, raises
nothing, and leaves a full durable snapshot — status, owner, `units_done`,
`units_total`, `attempt`, `last_error`, `error_history`, every step tuple and
the checkpoint count — byte-identical.

**Serialization reasoning.** `transition()` pairs `SELECT … FOR UPDATE` with
`populate_existing` (`lock_job_row`), so the ownership comparison and the
status write happen under a lock held to the end of the caller's transaction.
`renew_lease()` carries `status = RUNNING AND lease_owner = :worker` in the
`WHERE` of a single `UPDATE`, atomic by construction.

### H-2 — CLEARED

A handler raising after ownership transfer writes no step failure, no
`attempt`, no `last_error`, no `error_history` entry and no job failure status.

### H-3 — CLEARED

Exercised directly rather than through the executor: after a real handover,
`transition()` to `SUCCEEDED`, `PAUSING` and `CANCELLING`, plus `fail_job()`
and `block_job()`, each raise `OwnershipLostError` for the stale worker, and
the durable snapshot is unchanged. Ownership is default-on rather than opt-in,
which is what makes this structural rather than per-call-site.

### H-4 — CLEARED

The pre-unit proof and the step-start write are one serialization unit. With a
worker suspended inside that interval, a concurrent reclaim was observed
**blocked on a lock** in `pg_stat_activity` and was still incomplete when the
worker was released; the step then showed exactly one `attempt`. A worker that
was already stale at the check writes nothing at all.

### H-5 / H-5b — CLEARED

A planner suspended mid-`plan()` and reclaimed underneath creates no `JobStep`
rows, leaves `units_total` at `None`, and stands down with
`OWNERSHIP_LOST`. When the planner also raises, nothing escapes `execute_job`.

### Planning purity / session side effects — CLEARED

`lock_job_row()` calls `session.flush()` **before** taking the row lock, so an
adversarial planner's pending ORM state does reach the database before
ownership is proven. Tested rather than assumed: a planner that adds a
`JobCheckpoint` and then loses the lease leaves **zero** checkpoints durable.
The flush is uncommitted, and the `session.rollback()` on the ownership-loss
path discards it. The ordering is worth keeping in mind for future call sites,
but it is safe as written.

### H-6 — DEFECT (High)

*A worker whose lease has expired still passes the pre-unit check, commits the
step start, and executes the effect after another worker owns the job.*

**Location.** `packages/jobs/src/continuum_jobs/execution.py` — `_stop_requested`
validates `lease_owner` and `status` but **not** `lease_expires_at > now()`.

**Why the window exists.** The sequence is: prove ownership → commit step start
→ release the row lock → emit `STEP_STARTED` → *enter* `LeaseHeartbeat` →
`handler.execute_unit()`. The heartbeat's first beat is one interval away, and
it is entered *after* the lock is released. So a worker holding an expired
lease — an OS stall, a GC pause or a VM migration longer than
`worker_lease_seconds` is enough — is accepted as the owner, starts the step,
and then has an unguarded gap in which the reaper may legitimately reclaim.

The H-4 lock does not help here: it guarantees ownership cannot change *inside*
the proof-to-step-write interval, but it is released at that commit, and it
never asserted the lease was alive in the first place.

**Reproduction**
(`audit_artifacts/test_cold_lifecycle_audit.py::test_h6_expired_lease_owner_executes_effect_after_reclaim`).
The handler reads the durable `lease_owner` at the instant its effect begins.
That single value settles the question:

```
owner recorded at effect start: worker B
```

A executed the unit effect while B was the durable owner. Deterministic across
three consecutive full runs.

**Supporting evidence** (`::test_expired_lease_is_renewable_by_its_previous_owner`,
passing): `renew_lease` deliberately omits an expiry predicate, so an expired
lease can be renewed back to life by its previous owner. That is a defensible
decision — reaping, not the clock, is what transfers ownership — but it is the
mechanism that lets a worker with a dead lease keep behaving as the executor.

**Impact, stated precisely.** The companion test
`::test_h6_expired_lease_owner_writes_no_durable_completion` **passes**: the
completion record, progress and checkpoint are all correctly withheld by the
H-1 guards. So this is **not durable corruption**. What is lost is **executor
exclusivity**: two workers run the same unit's effect concurrently. ADR-0002
§2 makes that survivable — every effect must be content-addressed or a
deterministic upsert, so a repeat is a no-op — but §2 is a safety net for
*crash recovery*, not a licence to run two executors at once. The duplicated
compute is real, and for a multi-hour render it is expensive; a handler that is
idempotent in its final artifact but not in its intermediate resource use
(GPU memory, a temp scratch area, an external rate limit) has no protection at
all.

**Is a synchronous owner-scoped renewal before effect execution required?**
**Yes.** Two changes are needed and they are not interchangeable:

1. `_stop_requested` must also require `lease_expires_at > now()`, so a worker
   with a dead lease is never accepted as the owner; and
2. a **synchronous owner-scoped `renew_lease`** must run inside the pre-unit
   lock, before it is released. That both proves ownership and pushes the
   deadline past the heartbeat's first interval, closing the gap between the
   step-start commit and the first beat.

(1) alone leaves a narrower version of the same gap — the lease can expire
between the check and the first beat. (2) alone leaves the check accepting a
worker that should already have stood down. Together they make "this worker is
the executor" true for the whole interval in which it acts as one.

### H-7 — DEFECT (High)

*A BLOCKED exception raised after ownership loss terminates the worker process.*

**Location.** `packages/jobs/src/continuum_jobs/execution.py:316-321`

```python
except Exception as exc:
    if isinstance(exc, ContinuumError) and exc.context.get("blocked_reason"):
        raise                      # <-- before any ownership check
    # OWNERSHIP LOSS DOMINATES THE EXCEPTION (final audit H-2)
    ...
```

The blocked re-raise is evaluated **before** the ownership-dominance block that
H-2 installed directly beneath it. `Worker.run_once()` then catches
`SyntheticBlockedError` and calls `block_job(..., worker_id=self.worker_id)`,
which under default-on ownership raises `OwnershipLostError`. Nothing catches
it: `run_once` handles only `UnknownJobTypeError` and `SyntheticBlockedError`,
and `run_forever` is `try/finally` with no `except`.

**Reproduction**
(`::test_h7_blocked_exception_after_ownership_loss_through_worker_loop`) — driven
through the **real** `Worker.run_once()`, not a stub:

```
OwnershipLostError escaped Worker.run_once() and would terminate run_forever()
```

**Impact.** Availability, not integrity. The durable-state assertion in the same
test **passes** — `transition` raises before it writes, and `run_once`'s
`session_scope` rolls back — so the new owner's job is untouched. The damage is
that a routine race kills the worker. This is the same shape as H-5b, which was
fixed on the planning path; the BLOCKED path was left behind because its
`raise` sits above the guard.

### H-7b — DEFECT (High)

*The unknown-handler BLOCKED path has the same crash.*

`registry.get(job.job_type)` raises `UnknownJobTypeError`, and `run_once` calls
`block_job(..., worker_id=self.worker_id)` directly. With a handover between
the claim and that mutation, `block_job` raises `OwnershipLostError`, which
again escapes `run_once` and `run_forever`.

**Reproduction** (`::test_h7b_unknown_handler_blocked_path_after_ownership_loss`),
also through the real worker loop. Durable state is again intact; the worker
process again dies.

Note this path has no `execute_job` involvement at all, so it cannot be fixed
by the same edit as H-7. Both `block_job` call sites in `Worker.run_once`
need an ownership stand-down.

---

## Lock and regression audit

| Probe | Result |
|---|---|
| Deadlock between heartbeat, reaper and the new pre-unit lock | **None.** A reaper looping continuously against a live 4-unit worker produced no deadlock, no reaper error, and a normal `SUCCEEDED` completion. |
| API pause while the worker holds the pre-unit lock | **No deadlock.** The flag write blocks briefly on the lock, completes, and the job pauses at the next unit boundary (`PAUSED`, owner released). |
| Drain while the lock is held | **No deadlock.** The drain request completes and the job is requeued (`QUEUED`, owner released). |
| Rightful owner, full lifecycle | Plans, materialises, runs 3 units, records progress and finishes. One `attempt` per step. |
| Planning failure while still owner | Still fails the job. The H-5b stand-down does not swallow genuine errors. |
| Ownership transfer during planning | CLEARED (H-5) |
| Ownership transfer during unit execution | CLEARED (H-1) |
| Finalization after transfer | CLEARED (H-1, H-3) |
| C-1 lease concurrency | 13 / 13 |
| C-2 dependency concurrency | 7 / 7 |

### Obsolete artifact, as permitted

The H-4 artifact from `db056ba` is **structurally obsolete** and was not
counted as a production failure. Its synchronisation requires a lease steal to
succeed while the worker sits inside the pre-unit window — precisely what the
new row lock makes impossible — and it sets its own release gate only after
that steal returns, so it self-deadlocks and times out. The invariant was
instead reconstructed as a valid serialization test that observes the reclaim
blocked in `pg_stat_activity`.

---

## Test-reliability findings (not production defects)

**F-A — the shipped ownership suite's `_steal` helper is racy.**
`tests/acceptance/test_110_06_11_worker_ownership.py::_steal` expires the lease
in one transaction and reaps in a **separate** one. With
`heartbeat_seconds=0.1`, a beat can land in that gap and renew the lease —
proven deterministically by
`::test_expired_lease_is_renewable_by_its_previous_owner` — after which the
reaper finds nothing and the steal fails.

Observed: `test_stale_worker_writes_no_unit_completion_or_checkpoint` failed
**2 times in ~19 runs** of that file, and passed 8/8 when run alone. It is a
spurious *failure*, so it cannot hide a defect — but an intermittently red
regression suite erodes the guarantee it exists to provide. The fix is to
expire and reap in one transaction, as
`test_110_06_11_preunit_planning_ownership.py` and this audit's artifacts
already do.

**F-B — one unreproduced intermittent in this audit's own harness.**
`test_h5_stale_planner_writes_no_steps_and_no_units_total` failed once inside
`_steal` during an early run and did not reproduce in 8 targeted runs or in the
three final full runs. I could not capture the failing assertion and therefore
do **not** claim a root cause. Recording it rather than omitting it.

**F-C — `continuum_worker/__init__.py` shadows its own submodule.**
`from continuum_worker.main import Worker, main, …` binds the *function* `main`
as an attribute of the package, so `import continuum_worker.main as m` yields
the function, not the module. Cosmetic, no runtime impact, but it breaks
attribute-style access and monkeypatching; `importlib.import_module` is the
workaround used here.

---

## Gates at `e29ee6e`

| Gate | Result |
|---|---|
| Shipped suite `pytest -q` | **235 passed, 1 skipped, 0 failed** (236 collected; the skip is POSIX-only) |
| `test_110_06_11_preunit_planning_ownership.py` | 9 / 9 |
| `test_110_06_11_worker_ownership.py` | 11 / 11 (intermittently 10 / 11 — see F-A) |
| `test_110_06_11_lease_concurrency.py` | 13 / 13 |
| `test_110_11_dependency_concurrency.py` | 7 / 7 |
| **Audit artifacts (reported separately)** | **15 passed, 3 failed** of 18 — identical failures on three consecutive runs |
| `alembic current` / `heads` | single head `0001_phase0` |
| `alembic downgrade base` → `upgrade head` | round-trip clean |
| `ruff check .` | clean |
| `ruff format --check .` | 103 files already formatted |
| `mypy packages apps workers` | 49 files, no issues |
| `lint-imports` | 4 / 4 contracts kept |
| web lint / typecheck / build | clean |

**The shipped suite is fully green, and that is the point.** All three defects
sit at boundaries the shipped suite does not probe. A green suite is evidence
about the tests, not about the invariant.

---

## Required before this candidate can be tagged

1. **H-6** — add `lease_expires_at > now()` to the pre-unit ownership check,
   **and** perform a synchronous owner-scoped `renew_lease` inside the pre-unit
   lock before releasing it. Both, for the reasons given above.
2. **H-7** — move the `blocked_reason` re-raise *below* the ownership-dominance
   block in `execute_job`, so a stale worker stands down with
   `OWNERSHIP_LOST` instead of re-raising into a fatal `block_job`.
3. **H-7b** — give both `block_job` call sites in `Worker.run_once` an
   ownership stand-down. This path never enters `execute_job`, so it needs its
   own fix.
4. **F-A** — make the shipped `_steal` helper expire and reap in one
   transaction.
5. Re-run this audit's artifacts. All 18 must pass **without modifying the
   tests**.

Fixes must be root fixes in the lifecycle, not patches to the reproductions.
In particular, do not resolve H-7/H-7b by adding a catch-all `except` to
`run_forever`: that would mask the stand-down rather than implement it.

---

## Scope not audited

Vault immutability, Library, Story systems, Phase 1, provider policy internals,
and performance characteristics. This audit covered the worker lifecycle state
machine and its interaction with leases, the reaper, the transition guard, the
BLOCKED paths and the worker loop.
