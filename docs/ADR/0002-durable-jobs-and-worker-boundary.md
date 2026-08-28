# ADR-0002 — Durable jobs and the worker boundary

- **Status:** Proposed — awaiting human approval (handoff §2 gate)
- **Date:** 2026-08-28
- **Implements:** Master Plan §91 (Durable Production Job Manager)
- **Supersedes:** §4's "Redis for jobs/cache", §3's five worker services
- **Related findings:** F-05, F-22, F-23, F-24, F-25, F-26, F-27, F-28, F-29, F-30, F-31, F-32, F-59, F-70

---

## Context

§91 makes durable execution a foundation invariant, and §110.6–110.11 turn it into six acceptance tests. The specification's job model is good and incomplete: it defines states and checkpoint policy, but omits leasing, retry scheduling, deduplication, cancellation asynchrony, and — most importantly — any statement of what makes a *resumed* unit safe to re-run.

The last gap is the one that matters. "Checkpoint frequently" does not prevent duplicate work; it only narrows the window. Between performing an effect and recording it, a crash means the unit re-runs. If the effect is not repeat-safe, the system produces duplicates or corruption, and no checkpoint policy can fix it.

---

## Decision

### 1. PostgreSQL is the sole job store (F-05)

No Redis, no Celery, no Temporal, no in-memory queue. Claiming uses:

```sql
SELECT id FROM job
 WHERE status = 'QUEUED' AND run_after <= now()
   AND resource_class = ANY(:worker_classes)
 ORDER BY priority DESC, created_at
 FOR UPDATE SKIP LOCKED
 LIMIT 1;
```

Rationale: the database is already required, already backed up, already transactional, and already the state of record. Every §110 crash-recovery test is about durable state — putting that state anywhere else adds a second consistency problem for no benefit at this scale. Redis may return later purely as a notification transport or cache, **never as state of record**.

### 2. Effect idempotency is a foundation invariant (F-22) — the central decision

Every job unit must satisfy **one** of:

- **Content-addressed write** — temp file → fsync → atomic rename to a hash-named final path (ADR-0001 §4). A repeat is a byte-identical no-op.
- **Deterministic upsert** — keyed by a natural key derived from the input, never by an autoincrement or a wall-clock value.

Ordering, without exception: **perform effect → durably land the effect → commit the completion record.** The unit's completion row and the checkpoint advance commit in the *same transaction*. A crash at any point re-runs a unit whose effect is a no-op.

This makes at-least-once execution behave as effectively-once, which is what §110.10 actually requires. A handler that cannot satisfy either form must declare itself non-resumable and run as a single unit.

### 3. States, with two corrections to §91.1

```
QUEUED · BLOCKED · RUNNING · PAUSING · PAUSED · CANCELLING · CANCELLED
       · SUCCEEDED · FAILED_RETRYABLE · FAILED_FINAL
```

Terminal: `SUCCEEDED`, `FAILED_FINAL`, `CANCELLED`.

- **`CANCELLING` added** (F-23). Cancelling a running step is asynchronous exactly as pausing is. Without it, the UI lies or the implementation hard-kills the worker.
- **`BLOCKED` carries a reason** (F-24): `blocked_reason ∈ {DEPENDENCY, MISSING_PROVIDER, MISSING_MODEL, MISSING_SOURCE_ASSET, AWAITING_APPROVAL, RESOURCE_UNAVAILABLE}` plus a structured `remediation` payload naming what is missing and what the user should do. This is what makes §107's Production Queue actionable rather than a wall of "blocked". `AWAITING_APPROVAL` is reserved now for §103's approval gates so no migration is needed later.

### 4. Transitions are guarded; requests are flags (F-28)

Only the worker and the lease reaper may write `status`, and only through a single transition function holding the row lock, validating against an explicit allowed-transition table. Illegal transitions **raise**; they do not silently no-op.

Pause and cancel are **request flags** (`pause_requested`, `cancel_requested`), never status writes. This eliminates the entire class of race where the UI writes `PAUSED` while the worker concurrently writes `SUCCEEDED`. Both are cooperative: the worker checks flags between units.

### 5. Leases and a reaper (F-27)

`lease_owner`, `lease_expires_at`, refreshed by heartbeat while a unit runs. A reaper transitions expired-lease `RUNNING` jobs back to `QUEUED` with `attempt += 1`, recording a `job_event`. Combined with effect idempotency (§2), crash recovery is automatic rather than manual.

**All lease and scheduling timestamps use the database clock** (`now()`), never worker local time. Clock skew between machines must not be able to expire a live lease.

### 6. Retry scheduling (F-25)

`attempt`, `max_attempts`, `run_after` (timestamptz), exponential backoff with jitter. Errors are **structured** (F-70) — `code`, `category`, `retryable`, `user_message`, `technical_detail`, `remediation` — raised as typed exceptions by handlers, not stringified at the boundary. `last_error` holds the most recent; `error_history` is an append-only capped JSONB list.

Categories: `RETRYABLE_TRANSIENT`, `RETRYABLE_RESOURCE`, `PERMANENT_INPUT`, `PERMANENT_CONFIG`. The **handler** classifies; the framework never guesses from an exception type.

### 7. Enqueue is deduplicated (F-26)

`dedupe_key = hash(job_type, input_hash, recipe_version)` with a partial unique index over non-terminal statuses. Enqueue is get-or-create. Double-clicking "Scan Library" yields one job, not a race between two scanners over the same vault.

### 8. One unit mechanism covers both checkpoint patterns (F-29)

`job_step(job_id, unit_key UNIQUE per job, ordinal NULL, status, attempt, last_error)`.

- Unordered sets (per-file ingestion): use `unit_key`, ignore `ordinal`.
- Ordered streams (subtitle segments, frame batches): set `ordinal`; the resume cursor is "max completed ordinal".

`job_checkpoint(job_id, seq, payload JSONB | locator, created_at)` holds handler-specific resume state; latest-wins with a small retained history for diagnosis. Two separate mechanisms are explicitly avoided.

### 9. Dependencies block; they do not cancel

`job_dependency(job_id, depends_on_job_id, kind)`, with a cycle check at insert. A dependency reaching `FAILED_FINAL` puts dependents in `BLOCKED(DEPENDENCY)` — **not** `CANCELLED`. The user decides whether to retry the parent or abandon the chain. Automatic cascade cancellation destroys queued work the user may still want.

### 10. Resource classes, now (F-30)

`resource_class` (e.g. `cpu`, `gpu`, `network`, `disk`) on the job row, with a per-class max-concurrency limit consulted at claim time. Phase 0's limiter is deliberately naive. The **field** is what matters: "one GPU job at a time, eight hashing jobs" is inevitable, and adding it later is a schema change plus a scheduler rewrite.

### 11. Append-only audit

`job_event(job_id, event_type, from_status, to_status, detail, worker_id, correlation_id, created_at)` records every transition, lease acquisition and expiry, checkpoint, error, and flag observation. This is what makes the Codex audit's "incomplete error state / retry recording" checkable rather than a judgment call, and it is the only practical way to debug a failed six-hour job after the fact.

### 12. Process topology (F-32, §110.7–110.8)

```
[ web (Next.js) ] --HTTP--> [ api (FastAPI) ] --SQL--> [ postgres ]
                                                            ^
                          [ worker (separate OS process) ]--+
```

- The API **enqueues and reads**. It never executes job work.
- There is **no API→worker channel at all**: no RPC, no socket, no shared memory. All coordination is through the database.
- **No FastAPI `BackgroundTasks`** for anything durable — it dies with the request and the process.
- **The worker is never a child of the API or the dev server.** A `uvicorn --reload` or Next.js hot reload must not be able to kill it.
- **A future desktop wrapper (§91.4) must attach to an already-running worker service, never spawn one as a child of the window.** Electron and Tauri kill child processes on window close by default; this is precisely the trap §91.4 warns about, and it is written down here before the wrapper exists and the shortcut becomes tempting.

Consequently §110.8 is *structurally* true, not incidentally true.

### 13. Graceful shutdown works on Windows (F-31)

Two channels, one code path:

1. `SIGINT`/`SIGTERM` handler where the platform provides it.
2. A **database-visible drain flag** — `worker.drain_requested`, polled between units, set by `POST /workers/{id}/drain`.

Windows has no real `SIGTERM`; a POSIX-only design would be untested on the platform this project actually runs on. The flag path works identically everywhere, survives the API being down, is observable in the UI, and makes "graceful stop" a testable state transition rather than a signal-delivery race.

The `worker` table (`id`, `hostname`, `pid`, `resource_classes`, `started_at`, `last_heartbeat_at`, `drain_requested`, `stopped_at`) also gives the Production Queue honest liveness data and makes the reaper's decisions auditable.

### 14. One worker process, pluggable handlers (F-59)

§3's five worker directories describe *modules*, not deployables. Phase 0 ships one worker process with a `job_type → handler` registry. Future horizontal scaling differs by `resource_class`, not by module. Five services would be the microservice architecture §111 forbids.

### 15. Progress and ETA

`units_done` / `units_total`, `current_step` / `total_steps`, `elapsed_active_ms`. ETA displays `Estimating…` until N samples, then a naive rolling mean with a wide displayed range (F-66). A `hardware_signature` **string column** exists now so telemetry can be partitioned later; `HardwareExecutionProfile` is **not** built as an entity (F-60).

---

## Consequences

**Positive**

- Every §110 durability test is satisfied by construction rather than by careful coding.
- Crash recovery is automatic (leases) and safe (effect idempotency).
- No infrastructure beyond PostgreSQL — §111 respected, and one less thing to back up consistently.
- Pause/cancel races are eliminated structurally, not patched.
- The audit log makes long-job debugging tractable.

**Negative / accepted costs**

- Database polling is less elegant than a push queue. At single-user scale (one worker, sub-second latency tolerance), it is entirely adequate and vastly simpler. `LISTEN/NOTIFY` can reduce latency later without changing the state model.
- Effect idempotency constrains handler authors. This is intentional and is the load-bearing constraint of the whole design.
- The drain flag adds polling latency to graceful stop (bounded by unit duration). Accepted: correctness on Windows outweighs a few seconds.

---

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Celery + Redis | Job state ends up outside the database of record; §110.7–110.11 become hard to guarantee; adds infrastructure §111 forbids. |
| Temporal | Correct problem, enormous operational weight for a single-user local app. §4 already says "later, if workflows become complex". |
| In-process `BackgroundTasks` | Fails §110.7 and §110.8 by construction. |
| Checkpoint-frequency alone as the resume guarantee | Narrows the crash window without closing it; produces duplicates under real crashes. This is the failure mode §2 exists to prevent. |
| Direct status writes from the API | Guarantees the pause/cancel race the audit checklist explicitly looks for. |
| Cascade-cancel dependents on failure | Silently destroys queued work the user may still want. |
| POSIX signals only | Untested on the project's actual primary platform. |

---

## Verification

Acceptance tests §110.6–§110.11; review §S. Two tests carry unusual weight:

- **§110.10** must assert both that completed units do not re-run **and** that a *forced* re-run of a completed unit is a byte-identical no-op with no duplicate row. Without the second assertion, a handler that simply never retries would pass.
- **§110.11** must cover the lease-expiry path (hard-killed worker) in addition to the handled-error path, since only the former exercises the reaper.

Plus: `test_transition_table.py` (illegal transitions raise), `test_dedupe_enqueue.py` (double enqueue yields one job), and drain-flag graceful stop tested on both the signal and flag paths.
