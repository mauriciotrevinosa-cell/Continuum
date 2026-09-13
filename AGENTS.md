# AGENTS.md — engineering rules for Continuum

Rules for anyone writing code in this repository, human or agent. They are
derived from the accepted architecture, not invented here. Where this file and
an ADR disagree, the ADR wins; where an ADR and
[`docs/FOUNDATION_APPROVAL.md`](docs/FOUNDATION_APPROVAL.md) disagree, the
approval wins.

**Read before changing anything:** `docs/FOUNDATION_APPROVAL.md`, then
`docs/ADR/0001`–`0006`, then `docs/ARCHITECTURE_REVIEW.md`.

---

## 0. The current phase gates everything

Continuum is at **Phase 0**. Phase numbering follows Master Plan **§109 only** —
§43 and §86 are historical and must never appear in code, commits, tags, branch
names or issues.

`docs/PHASE_0_SCOPE_LOCK.md` is short and binding. If a change is useful *only*
because a later phase might need it, do not make it — unless ADR-0006 or the
foundation approval explicitly provisioned that field now to avoid an expensive
migration. Exactly three such pre-provisioned fields exist: `resource_class`,
`hardware_signature`, and the `AWAITING_APPROVAL` blocked reason.

---

## 1. The Source Vault is never written. There is no exception.

This is the product's foundational promise, and it is enforced structurally
rather than by convention (ADR-0001).

- `SourceVaultReader` has **no** write, delete, rename, mkdir or touch method.
  Not a disabled one. Not one that raises. A vault write must remain
  *unrepresentable*, because a method that exists is a method someone will be
  tempted to "fix".
- `DerivedStore` cannot be constructed over the vault: it is absent from the
  writable-root table by construction.
- **Never probe vault protection by writing** — not a temp file, not a
  diagnostic, not a cleanup (FOUNDATION_APPROVAL **A-01**). Where OS hardening
  cannot be observed non-mutatively, report `not_verified` and move on.
- **There is no escape hatch** (D-13/OQ-5): no force flag, no admin mode, no
  "just this once". A future requirement for Continuum-managed source mutation
  is a new architecture decision, not a parameter.

If you find yourself needing to write to the vault, you have found a design
problem, not a missing feature.

---

## 2. Only `packages/storage` touches the filesystem

ADR-0001 Layer 3, enforced by `.importlinter` **and** an AST walk in
`tests/invariants/test_import_boundaries.py`.

Outside `continuum_storage` you may not import `pathlib`, `shutil`, `tempfile`,
`zipfile`, `tarfile`, `glob` or `fileinput`, nor call `open()`, `Path()`,
`os.remove`, `os.mkdir`, `.read_bytes()` and friends. `os` itself is fine for
`os.environ` and `os.name`.

Route access through `SourceVaultReader` (read) or `DerivedStore` (write). If
you genuinely need an exemption, the marker is `# continuum: allow-filesystem`
and it is deliberately noisy to write — expect it to be challenged in review.

**All derived writes are content-addressed.** No user-supplied string ever
reaches a write path, which is why write-side traversal and zip-slip are
impossible here rather than merely defended against.

---

## 3. Durable work: effects must be idempotent

The central Phase 0 invariant (ADR-0002 §2, F-22). Read it before writing a
handler.

"Checkpoint often" is necessary and **insufficient**. A worker that completes a
unit and dies before the completion record commits *will* re-run that unit. If
the effect is not repeat-safe, you get duplicates or corruption, and no
checkpoint policy prevents it — the window is between the effect and the record
of the effect.

So every job unit's effect must be either:

1. a **content-addressed write** (temp → fsync → atomic rename), so a repeat is
   a byte-identical no-op; or
2. a **deterministic upsert** keyed by the input — never by an autoincrement,
   timestamp or random value.

Order is not negotiable: **perform effect → durably land it → commit the
completion record**, with the completion row and the checkpoint advance in the
*same* transaction.

`plan()` must be deterministic: re-planning after a crash has to produce
identical `unit_key`s, or resume cannot recognise completed work.

A handler that cannot satisfy either form must declare itself non-resumable and
run as a single unit. Say so explicitly; do not pretend.

---

## 4. Job state: guarded transitions, flags for requests

- **Only the worker and the lease reaper write `status`**, and only through
  `assert_transition`, which **raises** on an illegal transition. A silent
  no-op is how a job ends up in a state nobody can explain three hours into a
  render.
- **Pause and cancel are request flags** (`pause_requested`,
  `cancel_requested`), never direct status writes. This removes the race where
  the UI writes `PAUSED` while the worker writes `SUCCEEDED`.
- **All lease and scheduling timestamps come from the database clock**
  (`func.now()`), never a worker's local clock. Skew must not expire a live
  lease.
- **A failed dependency blocks dependents; it never cancels them.** Cascade
  cancellation silently destroys queued work the user may still want.
- **`BLOCKED` always carries a reason and a remediation payload.** "Blocked"
  alone is useless: a missing model and an unmet dependency need different
  actions from the user.

---

## 5. Process topology

```text
web ──HTTP──▶ api ──SQL──▶ postgres ◀──SQL── worker
```

- The API **enqueues and reads**. It never executes durable work.
- There is **no API↔worker channel**. All coordination is PostgreSQL (A-02).
  The worker may of course use the storage and provider abstractions to *do* its
  work; it is *coordination* that is database-only.
- **The worker is never a child process** of the API, the dev server, or a
  future desktop wrapper. Electron and Tauri kill child processes on window
  close — that is precisely the trap Master Plan §91.4 warns about.
- **No `BackgroundTasks`** for anything durable. It dies with the request.

---

## 6. Providers

- **`DataClass` is required on every call and has no default.** A defaulted
  privacy parameter is a forgotten one, and the first forgotten one ships
  source excerpts to a third party.
- **Privacy is filtered before cost.** `SOURCE_EXCERPT` never leaves the
  machine, whatever the profile says and however cheap the remote option is.
- **`FREE_LOCAL` has no path to PAID or REMOTE.** When only a paid provider
  could serve a capability, the result is `BLOCKED(AWAITING_APPROVAL)` naming
  what is available but not permitted. It never falls back.
- **Model identifiers appear only in `packages/providers/registry.py`,
  `packages/providers/fakes/` and config.** Enforced by
  `tests/invariants/test_no_model_literals.py`.
- Phase 0 ships **no AI SDK at all**, which is what makes "no cloud credentials
  required" checkable from `docs/DEPENDENCIES.md` rather than by code audit.

---

## 7. Data model rules (for when domain tables arrive)

Nothing below exists yet. The rules are here so the first table added in Phase 1
obeys them from its first commit.

- **Four tiers, one direction.** A → observed source; B → interpretation of
  source; C → project continuity; D → generated artifacts. **Foreign keys point
  only downward: D → C → B → A.** Never upward. This is what keeps canon and
  project continuity separate (§2.2), and it is mechanically testable.
- **Four time axes, never sharing a column:** `source_time`, `project_time`,
  `narrative_order`, `record_time`. `narrative_order` is the one people forget
  and the one the continuity validator needs most.
- **In-universe time must tolerate imprecision.** "Some weeks later" is a normal
  source statement; do not force implementers to invent a fake precise date.
- **Locators are content-derived, never row-derived**:
  `loc:v1:<medium>:sha256:<hash>#<unit>` (A-04). If a locator came from a
  database id, re-ingesting the same file would silently repoint every stored
  citation.
- **Asset identity is the content hash.** Paths are *observations*, not
  identity. A missing file becomes `OFFLINE`, never deleted.
- **Corrections are never destroyed.** Never `ON DELETE CASCADE` from an asset
  to a claim — mark `provenance_status = MISSING_SOURCE` instead. Silently
  discarding a user's review work is the worst bug this product could have.
- **Embeddings are model-versioned rows**, never a column on a segment.

---

## 8. Security

- The API binds **loopback only** while there is no authentication (A-03).
- **No endpoint accepts a filesystem path.** Ever. Address by id. A
  `GET /files?path=…` is a directory-traversal machine no matter how carefully
  it validates — and it will be proposed, because it is convenient.
- **Secrets** live in the environment, never in the database and never in
  committed config. Redaction is by pattern **and** by exact registered value:
  pattern matching alone misses a password like `postgres`.
- **Untrusted parsing runs in the worker, never the API**, with timeouts. A
  parser crash must be a job failure, not an application failure.
- Archive handling: never write using an entry name; cap size, ratio and count;
  reject symlink and absolute entries.

---

## 9. Franchise-agnostic engine

The engine hardcodes **no** franchise, character, city, government, romance or
plot. Real franchise names may appear in **prose documentation only** (A-05) —
`docs/creative/` is fine, and so is architecture rationale.

They may **not** appear in application source, runtime seed data, migrations,
fixtures or automated test data. `tests/invariants/test_no_franchise_strings.py`
derives its denylist from the franchise pool documentation at test time, so it
covers every franchise you add without anyone maintaining a list.

`fixtures/demo_vault/` is wholly invented and must stay that way.

---

## 10. Testing standards

- **Never weaken or delete a test to make it pass.** If a test contradicts an
  approved decision, stop and document the contradiction.
- **Never report a skipped test as PASS.** Every skip must print its reason and
  the command that would un-skip it.
- **Guard the guards.** An invariant test that could pass vacuously must assert
  it is actually inspecting something — see `test_storage_package_is_the_exception`
  and `test_pool_document_yields_a_usable_denylist`.
- **Windows-only tests may not be silently skipped and counted as a pass**
  (OQ-6). CI runs both Windows and Linux because neither alone gives full
  coverage: Windows has junctions and 8.3 names; Linux can create symlinks.

---

## 11. Workflow

- Work on a phase branch, never directly on `master`.
- Keep commits reviewable and scoped; do not mix phases in one commit.
- Explain **why** in the commit message, not just what. The findings this
  project is built on (F-nn) are worth citing.
- **Do not create the `continuum-phase-0` tag** until Claude's report, the
  independent Codex audit, and the final human review have all passed.
- If you approach a usage limit, follow
  [`docs/CLAUDE_CREDIT_HANDOFF_PROTOCOL.md`](docs/CLAUDE_CREDIT_HANDOFF_PROTOCOL.md):
  clean checkpoint, coherent commit, updated handoff, then stop. Never claim a
  phase is complete because time ran out.

---

## 12. Style

- Fix root causes, not symptoms. Prefer boring, reliable infrastructure.
- Comments explain *why* — a constraint, a rejected alternative, a trap. Do not
  narrate what the code already says.
- Keep Phase 0 smaller than the architecture it serves. The architecture
  describes years; this phase should stay readable in an afternoon.
- `ruff` and `mypy --strict` are clean before every commit. So are
  `lint-imports`, `pnpm lint` and `pnpm typecheck`.
