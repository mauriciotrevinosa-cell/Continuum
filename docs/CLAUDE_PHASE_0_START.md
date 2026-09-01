# Claude Runbook — Implement Continuum Phase 0

**Role:** primary Phase 0 implementer
**Status:** READY TO START after foundation approval is on `master`
**Hard stop:** do not implement Phase 1

---

## 0. Read this before touching code

You are implementing **Phase 0 only** of Project Continuum.

The architecture has already been reviewed and approved. This is not another greenfield design pass. Your job is to implement the approved foundation faithfully, identify only implementation-blocking contradictions, run the required tests, produce the Phase 0 report, and stop.

### Required reading order

Read these files completely before writing implementation code:

1. `docs/FOUNDATION_APPROVAL.md`
2. `docs/ADR/0001-storage-and-source-vault.md`
3. `docs/ADR/0002-durable-jobs-and-worker-boundary.md`
4. `docs/ADR/0003-database-and-versioned-state.md`
5. `docs/ADR/0004-provider-and-privacy-contract.md`
6. `docs/ADR/0005-artifact-recipes-and-lineage.md`
7. `docs/ADR/0006-phase-0-scope.md`
8. `docs/ARCHITECTURE_REVIEW.md`
9. `PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md` — especially §§90–112; §109 phase numbering is authoritative
10. `CONTINUUM_CLAUDE_CODEX_HANDOFF_v0.3.md`
11. `docs/CONTINUUM_FRANCHISE_MASTER_POOL_v0.2.md` only to understand that franchise content is creative documentation, **not runtime seed data**

### Conflict rule

For Phase 0, `docs/FOUNDATION_APPROVAL.md` has the highest authority for its explicit amendments. Do not revert its decisions to older wording found elsewhere.

---

## 1. First action: preflight, then report

Before implementation, inspect the current machine/repo and produce a concise preflight result in the working session. Do not ask the user questions that you can answer by inspection.

Verify at least:

- active git branch and clean/dirty state;
- working copy is not under OneDrive/Dropbox/Google Drive/iCloud sync;
- local folder spelling is `Continuum` rather than `Continnum` where practical;
- Python 3.12 availability through `uv`;
- Node and `pnpm` availability;
- Docker Desktop / Docker Engine availability;
- PostgreSQL + pgvector database strategy can be started via Docker Compose;
- no existing implementation code conflicts with Phase 0 scope;
- `.gitattributes` can land before implementation code.

If a required machine prerequisite is missing, distinguish:

- **can be installed/configured safely by the user/normal dev setup** — document exact command/step;
- **requires changing the user's OS/account/personal files** — do not silently change it; report the blocker and continue only with work that remains valid.

Do not treat a missing optional future dependency such as FFmpeg or an AI model as a Phase 0 blocker.

---

## 2. Phase 0 scope — exhaustive

Implement the accepted scope from ADR-0006 and nothing beyond it.

### Monorepo / tooling

- Python 3.12 project, managed by `uv`.
- Node workspace managed by `pnpm`.
- FastAPI API app.
- Next.js + React + TypeScript web app.
- One standalone worker process with pluggable handlers.
- PostgreSQL 16+ with pgvector extension provisioned via Docker Compose **for the database only**.
- Alembic migrations, exactly one head.
- `.gitattributes` with LF policy before substantive code.
- `.gitignore`, `.env.example`, `README.md` with reproducible commands.

### Phase 0 API surface

Only the minimum foundation endpoints:

- `/health`
- `/ready`
- jobs: list/get/enqueue/pause/cancel/retry as required by the accepted contract
- workers: list/drain as required by the accepted contract

**Network rule:** Phase 0 binds to `127.0.0.1` only. Configuration attempting non-loopback binding must fail validation. Do not implement a future-auth escape route now.

**Filesystem rule:** no API endpoint accepts an arbitrary filesystem path parameter.

### Phase 0 web surface

Only:

- system/status page;
- jobs list;
- job detail/progress/error state.

Do not add placeholder nav/screens for Library, Reader, Story Studio, Character Brain, Visual Lab, etc.

### Database — exactly six application tables

Implement only:

- `job`
- `job_step`
- `job_checkpoint`
- `job_dependency`
- `job_event`
- `worker`

Plus Alembic's own table.

Do **not** add franchise, source asset, character, canon, project, branch, artifact, visual, provider, approval, or story tables in Phase 0.

Install/create the pgvector extension in the initial database migration only to prove the database environment. No vector column exists in Phase 0.

### Durable job system

Implement the accepted ADR-0002 contract, including:

- PostgreSQL as sole durable job store;
- `QUEUED`, `BLOCKED`, `RUNNING`, `PAUSING`, `PAUSED`, `CANCELLING`, `CANCELLED`, `SUCCEEDED`, `FAILED_RETRYABLE`, `FAILED_FINAL`;
- guarded transition table/function;
- `pause_requested` / `cancel_requested` flags;
- deduplicated enqueue via deterministic dedupe key for non-terminal equivalent work;
- `run_after`, attempts, max attempts, retry backoff;
- structured errors and remediation;
- worker leases, heartbeat, expiry recovery/reaper using database clock;
- durable job units/steps;
- checkpoints;
- dependency DAG with cycle rejection;
- append-only `job_event` audit;
- resource class field and simple per-class concurrency limit;
- hardware signature string only, not a premature hardware-profile entity;
- progress stored independently of UI/API process;
- conservative ETA (`Estimating…` until enough samples, then simple rolling estimate).

### Process topology

The required invariant is:

```text
web -> HTTP -> API -> PostgreSQL
worker -----------> PostgreSQL
```

The API enqueues/reads. It does not execute durable work.

The worker is a separate OS process, never a child of the web dev server or API reload process.

There is no Phase 0 API-to-worker RPC/control plane. Durable coordination is through PostgreSQL. The worker may of course use approved storage/provider abstractions while executing a handler.

### Storage foundation

Implement the eight root concepts from ADR-0001, configured outside the repository:

- source vault
- library
- projects
- generated
- jobs
- models
- cache
- config

Requirements:

- `SourceVaultReader` exposes read operations only; it has **no write/delete/rename/mkdir API**;
- `DerivedStore` can write only to approved writable roots;
- one hardened path resolver with containment after normalization/realpath resolution;
- Windows path edge cases from the review are tested;
- content-addressed derived writes use temp -> fsync -> atomic landing;
- sync-folder detection/warning;
- synthetic demo vault only in `fixtures/demo_vault/`;
- no real copyrighted/franchise fixtures.

**Critical amendment:** do not verify Source Vault read-only status by attempting a test write. Continuum must never write into the vault, including diagnostics. If OS-level read-only cannot be proven non-mutatively, report `not_verified`/equivalent.

### Provider foundation

Implement contracts/registry/policy and deterministic **fakes only**.

No real AI SDK and no model download in Phase 0.

The full test suite must pass offline with empty cloud credentials.

Preserve:

- provider capability metadata;
- locality/cost/privacy/license metadata;
- required `DataClass` on calls;
- `FREE_LOCAL` cannot silently choose remote/paid;
- model identifiers live only in registry/config, not application logic;
- missing capability/model creates actionable `BLOCKED` state rather than silent substitution.

### Observability/config

Implement:

- structured logging;
- correlation id propagation request -> job -> step -> provider invocation;
- secret redaction by pattern and loaded-secret exact value;
- typed settings;
- `SecretStr`/equivalent redaction;
- no secrets in database or committed config;
- health/ready information sufficient to diagnose Phase 0 services without leaking secrets.

---

## 3. Synthetic handlers required

Implement the two Phase 0 synthetic handlers and use them to prove the foundation rather than touching real media.

### `synthetic.counted_work`

Purpose: prove durable progress, idempotent effects, checkpoint/resume, pause/drain, retry, crash recovery, and UI/API independence.

Requirements:

- N deterministic units;
- each unit writes a content-addressed marker under `/cache` or approved synthetic derived root;
- fault injection for hard death mid-unit;
- retryable failure injection;
- permanent failure injection;
- forced re-execution of a completed unit must be a byte-identical no-op with no duplicate row/effect.

### `synthetic.blocked_capability`

Purpose: prove provider policy/remediation.

It requests a capability with no permitted provider and becomes `BLOCKED(MISSING_PROVIDER)` or the approved equivalent with a structured remediation payload. It must not silently use cloud/paid work.

---

## 4. Tests are the product of Phase 0

Implement the full §110 acceptance-test matrix and the additional architecture-review invariant tests.

At minimum verify:

1. clean install/migration/boot using documented commands;
2. web can call API health;
3. root/path normalization safety;
4. traversal/symlink/junction escape rejection;
5. Source Vault cannot be modified through Continuum APIs/abstractions;
6. synthetic job roundtrip;
7. progress continues with web/API absent as specified;
8. web/API restart does not cancel worker work;
9. graceful worker drain leaves resumable state;
10. hard worker death resumes unfinished units safely and completed-unit forced rerun is idempotent;
11. retryable/final failure and expired-lease recovery are recorded correctly;
12. provider tests require no network/cloud credentials/real AI SDK;
13. logs redact secrets;
14. migrations cleanly install and meet documented downgrade/upgrade policy;
15. required documents exist before Phase 0 tag.

Also implement the additional invariants from the review, including as applicable:

- tier/FK direction scaffold;
- no real-franchise strings in executable/test data **but documentation is excluded from this grep**;
- model literals restricted to registry/config;
- OpenAPI-generated TS client has no drift;
- illegal job transitions fail;
- duplicate enqueue dedupes;
- sync-folder warning works.

### Windows-specific tests

Do not silently skip Windows-only path tests and count the project as fully passing.

If the current runner is not Windows, mark them explicitly not applicable to that runner and record that a Windows run remains required. The final `PHASE_0_REPORT.md` must say where/when the Windows checks passed before the phase is tagged complete.

---

## 5. Required documentation you must produce/update

Before stopping, ensure these are present and current:

- `README.md` — exact setup/start/test commands that have actually been run;
- `AGENTS.md` — repository rules for future coding agents, derived from the accepted architecture;
- `docs/DEPENDENCIES.md` — Phase 0 code dependencies and an explicit empty/future Model Assets section;
- `docs/PHASE_0_REPORT.md` — acceptance matrix with PASS/FAIL/NOT-APPLICABLE-PENDING-WINDOWS as appropriate, exact command, and relevant evidence;
- any small implementation ADR note only if a genuinely new irreversible implementation decision was unavoidable.

Do not rewrite the Master Plan merely to make code easier.

---

## 6. Required quality gates

Run and record the applicable commands for:

- Python formatting/linting (`ruff` or accepted equivalent from ADR);
- Python type checking (`mypy`, strict where specified);
- Python tests (`pytest`);
- import-boundary checks;
- TypeScript typecheck;
- ESLint;
- frontend tests;
- OpenAPI client regeneration/drift check;
- Alembic clean migration and single-head check;
- Docker database startup/health;
- end-to-end Phase 0 acceptance suite;
- offline/no-cloud-credential provider tests.

Fix root causes. Do not weaken tests to make them pass unless the test contradicts an approved architecture decision; if so, stop and document the exact contradiction.

---

## 7. Forbidden scope creep

Do not implement any of the following in Phase 0:

- manga/CBZ/PDF/EPUB/video reader;
- real source scanning or media hashing jobs;
- real SourceAsset/SourceSegment tables;
- source locator parser/resolver beyond any harmless schema/type placeholder absolutely needed by Phase 0 (prefer none);
- embeddings or RAG;
- canon extraction;
- Character Brain;
- Story Studio / projects / branches;
- relationship engine;
- Story Calendar;
- civilization/city/faction implementation;
- Visual Lab;
- image/TTS/video generation;
- real model integration;
- cloud AI;
- download/scrape functionality;
- authentication/multi-user/network sharing;
- desktop wrapper;
- Redis/Celery/Temporal/Neo4j/S3/Kubernetes;
- franchise-specific runtime logic or test fixtures.

If a future feature would be easier if you add a speculative table/interface now, **do not add it** unless the accepted Phase 0 ADR explicitly provisioned it.

---

## 8. Git workflow

Work on a dedicated Phase 0 implementation branch. Keep commits reviewable and scoped.

Suggested sequence:

```text
chore: bootstrap Continuum phase 0 monorepo
feat: add safe storage foundation
feat: add durable job database model
feat: add standalone worker and synthetic handlers
feat: add local provider contracts and fakes
feat: add phase 0 web and api surfaces
test: add phase 0 acceptance and invariant suite
docs: complete phase 0 report
```

Exact commit boundaries may differ, but do not mix Phase 1 work in these commits.

Do not tag `continuum-phase-0` yourself unless the later independent Codex audit and human/ChatGPT review have passed. Your job is to produce a **candidate** for the tag.

---

## 9. Your stopping condition

When implementation and available tests are complete:

1. update `docs/PHASE_0_REPORT.md` with honest results;
2. list any remaining machine/environment prerequisite that prevents a required test from passing;
3. give the exact commit/branch that Codex should audit;
4. **STOP.**

Do not begin Phase 1. Do not create the Library scanner. Do not ingest user media.

The next actor is Codex, following `docs/CODEX_PHASE_0_AUDIT.md`.
