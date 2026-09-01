# Codex Runbook — Independent Audit of Continuum Phase 0

**Role:** independent Phase 0 auditor / defect fixer
**Starts after:** Claude has completed the Phase 0 candidate and `docs/PHASE_0_REPORT.md`
**Hard rule:** do not add Phase 1 features

---

## 0. Mission

Audit the Phase 0 candidate independently against the accepted architecture. Treat Claude's implementation and report as claims to verify, not as authority.

Your job is to:

1. read the approved architecture;
2. inspect the implementation and commit history;
3. re-run the relevant checks in your environment;
4. find violations, unsafe shortcuts, race conditions, drift, missing tests, or dishonest PASS claims;
5. fix only verified Phase 0 defects when the fix is clear and within scope;
6. update the audit record;
7. stop before Phase 1.

Do **not** redesign the product, add future systems, or broaden scope merely because you prefer a different architecture.

---

## 1. Required reading order

Read completely:

1. `docs/FOUNDATION_APPROVAL.md`
2. `docs/CODEX_PHASE_0_AUDIT.md`
3. `docs/PHASE_0_REPORT.md`
4. `docs/ADR/0001-storage-and-source-vault.md`
5. `docs/ADR/0002-durable-jobs-and-worker-boundary.md`
6. `docs/ADR/0003-database-and-versioned-state.md`
7. `docs/ADR/0004-provider-and-privacy-contract.md`
8. `docs/ADR/0005-artifact-recipes-and-lineage.md`
9. `docs/ADR/0006-phase-0-scope.md`
10. `docs/ARCHITECTURE_REVIEW.md`
11. `docs/CLAUDE_PHASE_0_START.md`
12. `AGENTS.md`
13. `docs/DEPENDENCIES.md`
14. relevant code/tests/migrations/workflows

For Phase 0 conflicts, `docs/FOUNDATION_APPROVAL.md` has highest authority for its explicit amendments.

---

## 2. Audit posture

Assume subtle bugs are more likely at boundaries than in happy paths.

Prioritize:

- persistence across process death;
- state-machine races;
- lease expiry/recovery;
- idempotency after a crash between side effect and checkpoint;
- Source Vault write escapes;
- path traversal/symlink/junction/Windows path handling;
- UI/API ownership accidentally cancelling worker jobs;
- migration reproducibility;
- API/web contract drift;
- cloud/paid-provider leakage;
- secret leakage;
- scope creep hidden as "foundation" work;
- tests that pass without actually proving the invariant they claim to prove.

Do not reward quantity of code. A smaller correct foundation is preferable.

---

## 3. First audit: scope diff

Before running tests, inspect the Phase 0 candidate for forbidden scope.

Flag as a defect if Phase 0 contains unnecessary implementation for:

- real media parsing/reader;
- real source scanning or user-media hashing;
- canon entities or extraction;
- Source Intelligence/RAG;
- Character Brain;
- projects/branches/story engine;
- Visual Lab;
- real image/audio/video generation;
- real AI SDK/provider;
- authentication/network sharing;
- desktop wrapper;
- Redis/Celery/Temporal/Neo4j/S3/Kubernetes;
- franchise-specific runtime schemas, seeds, fixtures, logic, or tests.

Do not flag the human-facing franchise Markdown documentation; the real-franchise-string prohibition applies to executable/test data, not prose docs.

---

## 4. Source Vault audit — highest sensitivity

Verify structurally, not only by reading comments:

- `SourceVaultReader` exposes no write/delete/rename/mkdir capability;
- write-capable storage cannot resolve the Source Vault as a destination;
- there is no `force`, admin, cleanup, test, diagnostic, CLI, env var, or hidden escape hatch that writes to the vault;
- no read-only probe creates a temporary file inside the vault;
- all write destinations are generated/content-addressed rather than derived from user-controlled filenames;
- path containment occurs after canonicalization/realpath resolution;
- traversal and escape tests cover the architecture-review cases;
- filesystem access does not bypass the storage package boundary in application code.

**Critical amendment:** Continuum itself must never write to the Source Vault, even to test whether the OS would allow it.

If your runner cannot exercise Windows-specific junction/ADS/8.3/device-name behavior, report those checks explicitly as not executed on this runner. Do not convert that into a universal PASS.

---

## 5. Durable jobs audit — highest sensitivity

### State machine

Verify:

- allowed states match the accepted ADR;
- `CANCELLING` exists;
- API requests set pause/cancel flags rather than directly forcing terminal states;
- only authorized worker/reaper paths perform guarded status transitions;
- illegal transitions fail loudly and are tested.

### Lease and crash recovery

Verify:

- worker claim uses PostgreSQL locking semantics appropriate to the accepted design;
- active work has a lease owner and DB-clock expiry;
- heartbeat extends the lease;
- a dead worker's expired lease is recoverable;
- recovery does not depend on the dead process running cleanup code;
- lease recovery is covered by a hard-kill test, not just a raised exception.

### Idempotency

This is not satisfied merely because checkpoints exist.

Verify a deliberately interrupted unit can be re-run safely when a crash occurs after landing its effect but before completion/checkpoint commit.

The test must prove at least one of:

- content-addressed re-write is byte-identical and produces no duplicate effect; or
- deterministic upsert is a no-op/update on the same natural key rather than a duplicate row.

A test that only asserts "completed units were not scheduled again" is insufficient.

### Retry/dedupe/dependencies

Verify:

- deterministic job dedupe prevents equivalent concurrent active jobs;
- retryable failures schedule future attempts rather than spin immediately;
- final failures stop retrying;
- errors are structured/actionable;
- dependencies cannot form cycles;
- failed dependency blocks dependent work rather than silently deleting/cancelling it unless explicitly designed otherwise.

---

## 6. Process-boundary audit

Verify by code and test topology:

- worker is a standalone process;
- API does not execute durable jobs via FastAPI background tasks or in-process threads as the durable mechanism;
- worker is not spawned as a child of the web dev server/API reload process;
- UI/API can restart without cancelling the running worker job;
- progress exists in PostgreSQL independently of browser memory;
- DB-visible drain mechanism works and is portable;
- all durable coordination is PostgreSQL-backed.

It is acceptable for workers to use storage/provider abstractions while executing handlers; the prohibition is against a separate hidden coordination/state channel.

---

## 7. Provider/privacy audit

Verify:

- no real AI/cloud SDK dependency is present in Phase 0 lockfiles;
- no cloud account/credential is needed to boot or pass the core suite;
- fake providers are deterministic;
- provider policy requires data classification;
- `FREE_LOCAL` cannot silently resolve to paid/remote;
- missing provider/model yields actionable `BLOCKED` state rather than silent fallback;
- model identifiers are limited to registry/config locations as intended;
- no source excerpt can accidentally flow to a remote provider in the Phase 0 fake setup;
- dependency/model-license documentation does not claim licenses that have not been verified.

Run tests with empty cloud credentials and, where practical, network disabled.

---

## 8. API/security audit

Verify:

- Phase 0 rejects non-loopback bind addresses;
- API defaults to `127.0.0.1`;
- no arbitrary filesystem path is accepted by endpoints;
- CORS is not wildcard-open;
- secrets are not stored in DB or committed config;
- logging redacts exact loaded secret values as well as recognizable token patterns;
- health/readiness endpoints do not leak sensitive config.

Do not add authentication as a "fix" in Phase 0. The accepted solution is loopback-only.

---

## 9. Database/migration audit

Verify:

- exactly the six Phase 0 application tables exist, plus migration bookkeeping;
- pgvector extension setup does not introduce vector/domain tables prematurely;
- UUID/timestamp choices match the accepted decisions;
- job lease/scheduling logic uses DB time where required;
- Alembic has one head;
- clean DB migration works;
- documented downgrade/upgrade test behaves as reported;
- API schemas and ORM models are not improperly fused contrary to ADR-0003;
- TypeScript client is generated from OpenAPI and drift check is meaningful.

Flag any premature franchise/canon/project/visual/artifact schema as Phase 0 scope creep.

---

## 10. Test-quality audit

For every PASS in `docs/PHASE_0_REPORT.md`, ask: **does this test actually prove the stated invariant?**

Pay special attention to false-positive patterns:

- mocking away PostgreSQL concurrency while claiming queue correctness;
- never actually killing a worker while claiming crash recovery;
- checking a class lacks one write method while another public path can still write to the vault;
- skipping platform tests without surfacing them;
- provider tests that do not clear credentials/network;
- dedupe tests that run serially but not under concurrent enqueue;
- path traversal tests that normalize before symlink/junction resolution incorrectly;
- tests that assert implementation details instead of user-visible durability invariants.

Improve tests when a Phase 0 invariant is under-proven. Do not broaden product scope.

---

## 11. Cross-platform requirement

Your environment may differ from the user's primary Windows machine.

Use explicit classifications:

- `PASS_ON_THIS_RUNNER`
- `FAIL`
- `NOT_APPLICABLE_ON_THIS_RUNNER`
- `REQUIRES_WINDOWS_CONFIRMATION`

A Linux/macOS/container audit may pass the platform-independent portions, but the final Phase 0 gate still requires the Windows-specific path/security checks on Windows.

Do not mark a Windows-only test as fully passed because it was skipped.

---

## 12. Fix policy

You may fix a defect directly when all of these are true:

- it is clearly inside Phase 0;
- the accepted architecture determines the intended behavior;
- the fix does not introduce a new irreversible design decision;
- a regression test can accompany the fix.

Do not silently choose between competing architectures. If the approved docs genuinely leave an irreversible choice unresolved, report it as `NEEDS_DECISION` and stop that part.

Prefer root-cause fixes. Do not weaken a failing test, bypass a boundary, or add retries around a deterministic bug just to obtain green status.

---

## 13. Required audit output

Create or update:

`docs/CODEX_PHASE_0_AUDIT_REPORT.md`

It must include:

- audited commit SHA/branch;
- environment/OS/runtime versions;
- files/areas reviewed;
- commands executed;
- acceptance matrix outcome;
- Windows-specific checks status;
- defects found, severity, root cause, and fix commit if fixed;
- any divergence between Claude's report and observed behavior;
- explicit statement that no Phase 1 feature was added;
- final verdict: `PASS`, `PASS_PENDING_WINDOWS`, `FAIL`, or `NEEDS_DECISION`.

If you commit fixes, keep them narrow and separately reviewable.

---

## 14. Final gate

Do **not** create or move the `continuum-phase-0` tag.

When the audit is complete:

1. provide the audit report;
2. provide the exact commit SHA that should receive final human/ChatGPT review;
3. state any required Windows/local-machine checks still outstanding;
4. **STOP.**

Phase 1 begins only after the Phase 0 candidate passes Claude's report, Codex's independent audit, and final human/ChatGPT approval.
