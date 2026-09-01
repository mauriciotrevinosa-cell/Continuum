# Project Continuum — Foundation Architecture Approval

**Status:** APPROVED FOR PHASE 0
**Approval date:** 2026-08-31
**Scope:** Phase 0 foundation architecture only
**Applies to:** `PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md`, `docs/ARCHITECTURE_REVIEW.md`, ADR-0001 through ADR-0006

---

## 1. Decision

The architecture review is accepted. The six proposed ADRs are accepted **with the amendments in this document**.

Phase 0 may begin only under the scope and acceptance gates defined here, in `docs/ADR/0006-phase-0-scope.md`, and in the Phase 0 agent runbooks.

This approval does **not** authorize Phase 1 work, real media ingestion, canon extraction, Character Brain implementation, Visual Lab implementation, story-specific hardcoding, or real AI provider integration.

### Authority order for Phase 0

When two documents conflict, use this order:

1. **This file — `docs/FOUNDATION_APPROVAL.md`** for the explicit amendments below.
2. `docs/ADR/0001-0006` for accepted architectural decisions.
3. `docs/ARCHITECTURE_REVIEW.md` for findings, rationale, and acceptance-test detail.
4. `PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md`.
5. Historical sections of the Master Plan.

Only Master Plan **§109** numbering is authoritative for phases. Historical phase-numbering schemes must not be used in code, commits, tags, issues, tests, or implementation docs.

---

## 2. Amendments to the accepted ADRs

These amendments are binding and override only the conflicting wording in the referenced ADR/review.

### A-01 — Source Vault verification must never write to the vault

**Amends:** ADR-0001 Layer 5 / any architecture-review text that proposes probing read-only status by creating a file in `/source-vault`.

Continuum must **never attempt a test write, delete, rename, mkdir, temporary-file creation, or cleanup write inside the Source Vault**, even as a diagnostic.

OS hardening may be detected only through non-mutating inspection where reliable. If the application cannot prove OS-level write denial without mutating the vault, it reports an informational state such as:

- `verified_readonly`
- `not_verified`
- `not_hardened`

Application-level structural protections remain mandatory regardless of this OS-level signal.

The invariant is simple: **Continuum itself is never the process that writes to the vault.**

### A-02 — Worker coordination versus worker work

**Clarifies:** ADR-0002 process-topology language.

All **durable job coordination and state transitions** occur through PostgreSQL. There is no API-to-worker RPC/control channel in Phase 0.

This does not mean the worker is prohibited from using approved storage abstractions or provider abstractions to perform its job. The worker may use those modules as required by a handler; PostgreSQL remains the sole durable coordination/state-of-record substrate.

### A-03 — Phase 0 network binding is loopback-only

**Amends:** ADR-0004 §8 and D-16 for Phase 0.

Because Phase 0 contains no authentication, the API must bind to **`127.0.0.1` only**. A non-loopback bind is rejected by configuration validation.

Do not implement a dormant "bind to LAN if auth exists" path in Phase 0 because authentication does not yet exist. If remote/LAN access is introduced later, it requires an explicit future security decision/ADR and authentication implementation first.

The existing rule remains: **no API endpoint accepts an arbitrary filesystem path parameter.**

### A-04 — Source Locator format is versioned from the first implementation

**Amends:** ADR-0005 source-locator grammar.

The canonical outer form is:

```text
loc:v1:<medium>:sha256:<asset_content_hash>#<unit-address>
```

Examples:

```text
loc:v1:cbz:sha256:ab12...#page=12
loc:v1:pdf:sha256:ef56...#page=88&span=1204-1319
loc:v1:video:sha256:0a1b...#t=00:12:03.400-00:12:07.100
```

The version prefix is part of the stored locator. If parsing/segmentation semantics change years later, old locators remain interpretable by the resolver for their original version rather than being silently reinterpreted.

No locator implementation belongs in Phase 0; this only fixes the future wire/storage format before data exists.

### A-05 — Real-franchise-string prohibition applies to executable/test data, not prose documentation

**Clarifies:** ADR-0006 / F-10 / D-18.

The no-real-franchise-string CI rule applies to:

- application source code,
- runtime seed data,
- database migrations,
- fixtures,
- automated-test data.

It does **not** apply to human-facing Markdown documentation, creative planning files, the franchise master pool, architecture rationale, license/reference notes, or similar prose docs. Documentation is allowed to name the franchises the project is discussing.

The implementation engine itself remains franchise-agnostic.

---

## 3. Official answers to OQ-1 through OQ-6

### OQ-1 — PostgreSQL + pgvector provisioning

**Decision:** Docker Desktop, with Docker Compose running **the database only**. API, worker, and web run natively during development.

Do not use SQLite as the Phase 0 queue substrate. Phase 0 must test the same PostgreSQL concurrency semantics the application will actually use, including `FOR UPDATE SKIP LOCKED`.

### OQ-2 — Repository and data roots under OneDrive

**Decision:** the active development working copy and all Continuum data roots must be moved to non-synced local storage before Phase 0 acceptance is declared.

The GitHub remote remains the distribution/backup remote for source code and docs. The local repository path should use the correct spelling `Continuum`.

No PostgreSQL data directory, Source Vault, generated root, cache root, or active git working tree should intentionally live under OneDrive/Dropbox/Google Drive/iCloud sync.

### OQ-3 — Source Vault physical size/location

**Decision:** do not design around a small internal-laptop-only vault. Assume the vault can grow to **hundreds of GB or multiple TB** and may later live on another SSD, an external disk, or be temporarily disconnected.

Consequences:

- hashing is streaming/resumable rather than whole-file-in-memory;
- paths are observations, not identity;
- content hash is durable identity;
- a disconnected/missing vault or asset becomes `OFFLINE`, never silently deleted;
- the concrete physical path is configuration, not schema identity.

### OQ-4 — Near-term product emphasis

**Decision:** **Library / Reader first**, while protecting the provenance and locator foundations required by Source Intelligence.

This does not reorder §109. It means Phase 1–2 usability receives priority, while Phase 0 still establishes the boundaries that Phase 3+ will rely on.

### OQ-5 — Source Vault write escape hatch

**Decision:** **none.** No force flag, admin setting, cleanup mode, hidden override, or "temporary" write capability.

If a future product requirement genuinely needs Continuum-managed source mutation, it requires a new architecture decision rather than bypassing this invariant.

### OQ-6 — Codex audit environment

**Decision:** assume Codex may run in a different environment from the primary Windows development machine.

Cross-platform CI/audit is useful but cannot substitute for Windows-specific validation. Windows path-security tests must not be silently skipped and then counted as a full PASS.

Phase 0 cannot be tagged complete until:

1. platform-independent checks pass in the audit environment; and
2. the Windows-specific acceptance/security checks have been executed successfully on the primary Windows environment or an equivalent Windows runner.

Wrong-platform tests may be reported as `NOT_APPLICABLE_ON_THIS_RUNNER` / explicit xfail with reason, but the final Phase 0 report must show where the required Windows run passed.

---

## 4. D-01 through D-20 — approved decisions

All twenty architecture-review decisions are approved, with D-16 and D-18 interpreted through amendments A-03 and A-05.

| ID | Approved decision |
|---|---|
| D-01 | Eight configured data roots live outside the git repository. |
| D-02 | PostgreSQL is the sole durable job store; no Redis/Celery/Temporal state of record. |
| D-03 | Docker Desktop provisions PostgreSQL + pgvector only; app processes run natively in development. |
| D-04 | Pin Python 3.12 for the project. |
| D-05 | Use `uv` for Python and `pnpm` for Node workspaces. |
| D-06 | SQLAlchemy 2.0 ORM + separate Pydantic v2 API schemas. |
| D-07 | UUIDv7 primary keys for durable domain/job identities. |
| D-08 | `franchise.yaml` is read-only user-authored input; Continuum never writes it. |
| D-09 | `timestamptz`, UTC; database clock for leases/scheduling. |
| D-10 | Generate TypeScript API client from OpenAPI; CI rejects drift. |
| D-11 | Graceful worker stop supports signals and DB-visible `drain_requested`. |
| D-12 | Phase 0 ships no real AI SDK; fakes only. |
| D-13 | No Source Vault write escape hatch. |
| D-14 | Source locators are content-derived and versioned per A-04. |
| D-15 | Derived/generated storage is content-addressed with atomic landing. |
| D-16 | Phase 0 API is `127.0.0.1` only per A-03. |
| D-17 | No copied/ported GPL code; architectural/UX reference only where appropriate. |
| D-18 | Synthetic fixtures only; real-franchise-string restriction scoped per A-05. |
| D-19 | Active repo/data move off cloud-sync folders; correct local folder spelling. |
| D-20 | Add `.gitattributes` with LF policy before implementation code lands. |

---

## 5. Disposition of the 12 BLOCKER findings

All twelve blockers identified by the architecture review have an approved resolution before Phase 0 implementation:

| Blocker | Resolution |
|---|---|
| F-01 | §109 is the only authoritative phase numbering. |
| F-02 | `franchise.yaml` is read-only input. |
| F-03 | Data roots are outside the repository. |
| F-15 | No vault-write override exists. |
| F-17 | `SourceBrain` and `ProjectBrainOverlay` remain separate Tier B/Tier C concepts. |
| F-18 | Source snapshots separate material cutoff from interpretation/extraction version. |
| F-22 | Safe resume depends on idempotent effects, not checkpoint frequency alone. |
| F-27 | Running jobs use leases/heartbeats and expired-lease recovery. |
| F-32 | PostgreSQL provisioning is Docker Desktop database-only. |
| F-46 | Source locators are content-derived and versioned (`loc:v1:...`). |
| F-50 | Phase 0 API is loopback-only and takes no raw filesystem-path parameters. |
| F-68 | `source_time`, `project_time`, `narrative_order`, and `record_time` are separate axes. |

No blocker remains open at the architecture-decision level. Machine setup requirements still have to be satisfied before the related acceptance tests can pass.

---

## 6. Phase 0 invariants that must survive implementation

Phase 0 is successful only if implementation preserves these properties:

1. **Closing/restarting the web UI does not own or cancel durable work.**
2. **Hard-killing a worker does not strand a job forever.** Lease recovery resumes safely.
3. **Re-running an interrupted unit is safe.** Effects are content-addressed or deterministic upserts.
4. **The Source Vault is structurally read-only from Continuum.** No test-write loophole.
5. **No cloud account, paid API, or AI SDK is required.** Phase 0 operates fully offline with fakes.
6. **No real franchise logic or copyrighted fixtures enter executable/test data.**
7. **The API is local-loopback only.**
8. **Jobs, errors, progress, checkpoints, and worker liveness are durable and inspectable.**
9. **Database migrations are repeatable from a clean checkout.**
10. **Phase 0 stays Phase 0.** No scanner, reader, canon engine, Story Studio, Character Brain, Visual Lab, or generation feature is smuggled in as "foundation" work.

---

## 7. Human/machine preflight before Phase 0 can be declared complete

These are setup gates, not new product features:

- Docker Desktop is installed and usable for PostgreSQL + pgvector.
- Python 3.12 is available to `uv`.
- `pnpm` is available.
- The active local repo is outside OneDrive/other sync folders.
- Continuum data roots are configured outside the repo and outside cloud-sync folders.
- `.gitattributes` lands before implementation code.
- The Source Vault path used for testing is synthetic and contains no copyrighted fixture material.

Claude may automate/document setup checks, but should not silently change the user's operating system, cloud-sync configuration, or personal files.

---

## 8. Implementation authorization

**Claude is authorized to begin Phase 0 after reading `docs/CLAUDE_PHASE_0_START.md`.**

Claude must stop after Phase 0 implementation, tests, and `docs/PHASE_0_REPORT.md` are complete. It must not proceed to Phase 1 without a new explicit instruction.

**Codex is not the primary Phase 0 implementer.** Codex begins the independent audit only after Claude has produced a Phase 0 candidate and must follow `docs/CODEX_PHASE_0_AUDIT.md`.

The intended sequence is:

```text
Foundation approved
    -> Claude implements Phase 0
    -> Claude runs and documents acceptance suite
    -> STOP
    -> Codex independently audits/re-runs checks
    -> defects only, no feature expansion
    -> human/ChatGPT review
    -> tag continuum-phase-0 only after PASS
```

---

## 9. What remains deliberately deferred

Approval of the foundation does **not** pre-approve design details that should be learned from later implementation/use. Among the explicitly deferred systems are:

- real media parsing and ingestion,
- Reader/Media Center,
- Source Intelligence / RAG,
- Character Brain implementation,
- canon/project branch engine,
- relationships and Story Calendar implementation,
- city/civilization/faction systems,
- Continuum Visual Lab,
- real image/audio/video generation,
- model training/fine-tuning,
- exact third-party voice likeness workflows,
- power-system unification,
- full episode generation.

Their architectural boundaries remain protected, but their concrete schemas/workflows are not to be invented prematurely in Phase 0.

---

## 10. Approval statement

The architecture review did its job: it surfaced expensive-to-reverse decisions before code existed. With the amendments and decisions recorded here, the Continuum foundation is approved to move from **architecture review** to **Phase 0 implementation**.

**Next document for the implementing agent:** `docs/CLAUDE_PHASE_0_START.md`.
