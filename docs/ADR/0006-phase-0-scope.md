# ADR-0006 — Phase 0 scope

- **Status:** Proposed — awaiting human approval (handoff §2 gate)
- **Date:** 2026-08-28
- **Implements:** Master Plan §109 (Phase 0), §110 (acceptance tests), §111 (do-not-build-first)
- **Depends on:** ADR-0001 … ADR-0005
- **Related findings:** F-01, F-09, F-32, F-38, F-59, F-60, F-61, F-62, F-63, F-67

---

## Context

Phase 0's job is to make the *invariants* real, not to make the product feel real. §112 names the primitives in order — immutable sources → durable jobs → provenance → versioned state → branches → approvals → replaceable providers → reproducible artifacts — and Phase 0 owns exactly the first two, plus the boundaries the rest will need.

The main risk is scope creep dressed as foundation work: schemas for entities nobody will use for a year, placeholder screens, "just one small" real provider, or a media parser "to prove the pipeline". §111 exists to prevent this, and this ADR makes it specific.

Everything here is scoped against **§109's numbering, which is authoritative** (F-01). §43 and §86 are historical.

---

## Decision

### 1. In scope — exhaustively

| Area | Deliverable |
|---|---|
| **Monorepo** | The tree in `ARCHITECTURE_REVIEW.md` §Q. `uv` workspace (Python), `pnpm` workspace (Node). |
| **API** | FastAPI: `/health`, `/ready`, jobs (list, get, enqueue, pause, cancel, retry), workers (list, drain). Bound to `127.0.0.1`. |
| **Web** | Next.js shell: a system-status page and a Jobs list + detail screen. **Nothing else.** |
| **Database** | PostgreSQL 16+, pgvector extension installed, Alembic, six tables (§3 below). |
| **Storage** | Eight roots per ADR-0001; `SourceVaultReader` / `DerivedStore` split; `resolve_within`; content-addressed writes; OS read-only probe; sync-folder detection. |
| **Jobs** | Full ADR-0002 model: states, guarded transitions, request flags, leases, reaper, units, checkpoints, dependencies, dedupe, backoff, resource classes, audit events. |
| **Worker** | One standalone process, handler registry, signal + drain-flag shutdown. Two synthetic handlers. |
| **Providers** | ADR-0004 contracts, registry, policy, and **fakes only**. |
| **Observability** | Structured JSON logging, correlation ids (request → job → step → provider call), `job_event` table, secret redaction. |
| **Config** | Typed settings, `SecretStr`, boot validation of roots and the bind/auth pairing, `.env.example` with no real values. |
| **Tests & CI** | Acceptance tests for all 15 §110 items, the §S.1 invariant tests, lint, typecheck, import-linter, OpenAPI contract-drift check. |
| **Docs** | `AGENTS.md`, `docs/DEPENDENCIES.md` (with a Model Assets section), `docs/PHASE_0_REPORT.md`. |

### 2. Explicitly out of scope

No media reader of any kind. No file scanning, hashing of real assets, or classification. No source segments, no locator *implementation* (the format is decided in ADR-0005; no code). No embeddings, no vector columns, no retrieval. No canon entities — no Character, Event, CanonClaim, Relationship, Location, Faction, Ability. No Project, Branch, Story Bible, Calendar, or world state. No Character Brain, no Craft Vault. No Change Graph, no continuity validator. No Visual Lab. No artifact, recipe, or lineage tables. No approval-gate engine. No prompt templates (nothing generates). No real AI provider or SDK. No authentication, no multi-user. No desktop wrapper. No Redis, S3, Neo4j, Temporal, or Kubernetes.

**And no placeholder UI** (F-67). An empty "Visual Lab" nav item creates an impression of progress that does not exist and invites premature backend stubs. Screens appear in the phase that builds their feature.

### 3. Exactly six tables

`job`, `job_step`, `job_checkpoint`, `job_dependency`, `job_event`, `worker` — columns as specified in `ARCHITECTURE_REVIEW.md` §R.1 — plus Alembic's `alembic_version`.

The pgvector extension is created by the first migration to prove the database image is correct. **No column uses it.**

The tier-classification registry and the FK-direction CI test (ADR-0003 §2) are scaffolded in Phase 0 even though all six tables are infrastructure rather than tiered domain data — so that the very first domain table added in Phase 1 is checked from the moment it exists.

### 4. Two synthetic job handlers

1. **`synthetic.counted_work`** — N units, each writing a content-addressed marker file into `/cache`. Fault injection via configuration: `die_at_unit` (hard process kill mid-unit), `fail_at_unit` (retryable), `fail_permanently_at_unit`. Proves §110.6–110.11.
2. **`synthetic.blocked_capability`** — requests a capability nothing satisfies. Proves `BLOCKED(MISSING_PROVIDER)` and the remediation payload (§110.12).

Neither touches real media. Their purpose is to make the durability invariants testable *before* anything valuable depends on them — which is exactly the point of building the job system first.

### 5. Toolchain decisions

| Decision | Choice | Rationale |
|---|---|---|
| Python | **3.12** (pinned), not the installed 3.14 | The Phase 3/4 ML stack (torch, ctranslate2, opencv) lags new CPython by 6–18 months. Pinning now avoids a forced downgrade mid-project. (D-04) |
| Python tooling | `uv` (already installed) | Fast, lockfile-based, workspace-capable |
| Node | pnpm workspace | Needs installing |
| Database provisioning | **Docker Desktop, database container only**; API/worker/web run natively | pgvector is unpleasant to build natively on Windows; native API/worker/web keep the inner loop fast and debuggable. **Blocked on OQ-1.** |
| Lint / format / types | ruff, mypy (strict on `packages/`), ESLint, TypeScript strict | |
| Boundaries | import-linter | Enforces the ADR-0001 filesystem boundary |
| API↔web contract | OpenAPI → generated TypeScript client, CI fails on drift | (D-10, F-63) |
| Line endings | `.gitattributes` with `* text=auto eol=lf` **before any code lands** | (D-20) |

### 6. Definition of done

Phase 0 is complete when **all** of the following hold:

1. All 15 §110 acceptance tests pass, each mapped in `PHASE_0_REPORT.md` to the exact command that proves it.
2. All §S.1 invariant tests pass — in particular the import-boundary test, the FK-direction test, and the forced-re-run byte-identity assertion.
3. The full suite passes with **no network access** and an **empty `.env`**.
4. Lint, typecheck, and contract-drift checks are clean.
5. `AGENTS.md`, `docs/DEPENDENCIES.md`, `docs/ARCHITECTURE_REVIEW.md`, `docs/ADR/0001–0006`, and `docs/PHASE_0_REPORT.md` exist and are current.
6. `README.md` contains exact, verbatim-runnable setup, start, and test commands, verified on a clean checkout.
7. The Codex audit (handoff §4) returns PASS.

Only then: `git tag continuum-phase-0`. The tag is a recovery point and is never moved (handoff §5).

### 7. Anti-goals for the implementing agent

- **Do not add a table because §106 names the concept.** A concept earns a table when it needs its own foreign keys, indexes, or constraints (ADR-0003 §14).
- **Do not build extension points "for later."** ADR-0002's `resource_class` and `hardware_signature` and ADR-0002's `AWAITING_APPROVAL` reason are the *only* pre-provisioned fields, each justified by a specific avoided migration. Nothing else.
- **Do not implement a real provider "to prove it works."** Fakes prove the contract; §110.12 proves the absence of coupling.
- **Do not parse a single real media file.**
- **Keep the Phase 0 implementation smaller than the architecture it serves.** The architecture describes years; Phase 0 should be readable in an afternoon.

---

## Consequences

**Positive**

- The durability and immutability invariants are proven by tests before anything valuable depends on them.
- Phase 1 begins with a job system that has already survived crash, pause, resume, retry, and drain testing.
- The dependency inventory starts minimal and honest.
- The FK-direction and import-boundary tests are in place before the first domain table exists, so they never have to be retrofitted against existing violations.

**Negative / accepted costs**

- Phase 0 produces nothing a user can visibly use. This is correct and intended by §109; `PHASE_0_REPORT.md` is the deliverable, not a demo.
- Building a job system against synthetic work feels indirect. It is the only way to test crash recovery without risking real data, and §110 requires exactly this.
- Pinning Python 3.12 while 3.14 is installed adds one setup step. Far cheaper than a forced downgrade at Phase 3.

---

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Fold Phase 1's scanner into Phase 0 "since it's small" | The scanner is the first thing that touches real user media. It should run on a job system that has already been proven under crash testing, not one being written alongside it. |
| Define all §106 entities now, implement later | Schemas written before their use cases are wrong in ways nobody notices until migration time. ADR-0003 fixes the *rules*; the tables come with their features. |
| Ship placeholder screens for the §107 UI | Creates false progress and invites premature backend stubs. |
| Use SQLite for Phase 0 | `FOR UPDATE SKIP LOCKED` does not exist; the job queue would be built on a different concurrency model than it ships with, and §110.6–110.11 would test the wrong thing. |
| Skip the synthetic handlers, test with real ingestion | Cannot safely fault-inject against a user's real library, and it makes Phase 0 depend on Phase 1. |

---

## Verification

`docs/PHASE_0_REPORT.md` must contain the §110 matrix from `ARCHITECTURE_REVIEW.md` §S with PASS/FAIL and the exact proving command per row, plus the §S.1 invariant tests, plus the documented output of the thirteen runs required by handoff §3.
