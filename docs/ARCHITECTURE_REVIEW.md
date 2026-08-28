# Project Continuum — Architecture Review

**Reviewer role:** senior architecture reviewer (Claude), per `CONTINUUM_CLAUDE_CODEX_HANDOFF_v0.3.md` §1.
**Inputs reviewed:** `PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md` (all 3,436 lines: base spec §1–60, v0.2 Living Story Vault addendum §61–89, v0.3 consolidation §90–112), `CONTINUUM_GITHUB_REPO_SHORTLIST.md`, `CONTINUUM_CLAUDE_CODEX_HANDOFF_v0.3.md`.
**Authority rule applied:** v0.3 (§90–112) > v0.2 addendum (§61–89) > base spec (§1–60).
**Status:** review only. No implementation code was written. Phase 0 has not started.

---

## 0. Verdict

The v0.3 specification is **architecturally sound and unusually well-sequenced for a project of this ambition**. The core instinct — immutable sources → durable jobs → provenance → versioned state → branches → approvals → replaceable providers → reproducible artifacts — is correct, and the discipline of putting durable execution in Phase 0 rather than Phase 9 is the single best decision in the document.

It is **not ready for Phase 0 implementation as written.** Not because it is wrong, but because it is under-specified in exactly the places where a wrong Phase 0 guess is expensive to undo later. Twelve findings are marked BLOCKER: each one is a decision that becomes a painful migration if an implementer picks the obvious-but-wrong option.

The four most important structural corrections this review recommends:

1. **The data roots must live outside the git repository.** The spec's §3 tree puts `source-vault/`, `library/`, and `cache/` inside the monorepo. That is a data-loss hazard (`git clean -xdf` deletes the user's source media) and it contradicts §108, which treats them as configured data categories. (F-03)
2. **Idempotency must be a property of job *effects*, not of job bookkeeping.** "Checkpoint often" is necessary but insufficient — it does not make a re-run of an interrupted unit safe. Content-addressed writes plus deterministic upserts are what make at-least-once execution behave as effectively-once. (F-22)
3. **Source locators must be derived from content, not from database row IDs.** Every provenance claim in the entire product hangs off locator stability. If re-ingesting the same file produces different locators, the whole provenance layer silently rots in Phase 3+. Decide the locator format now, implement it later. (F-46)
4. **The three (really four) time axes must never share a column.** Source in-universe time, project in-universe time, narrative order, and real-world record time are conflated across §11, §69, and §97. Separating them costs nothing now and is a full-schema migration later. (F-68)

Recommendation: **resolve the 12 BLOCKER findings and the 6 genuinely-blocking open questions (§T), approve the six ADRs, then proceed to Phase 0.** The rest can be resolved inside the phase they belong to.

---

## 1. Environment findings (this machine, probed 2026-08-28)

These are not spec defects, but they change what Phase 0's "one command starts the app" can honestly mean.

| Finding | Detail | Impact |
|---|---|---|
| **E-1** | **No Docker / Docker Desktop installed.** | §4 and §43 assume Docker Compose for PostgreSQL + pgvector. Acceptance test §110.1 ("clean clone/install/migrations/boot succeeds using documented commands") cannot pass until a database strategy is chosen. See **OQ-1**. |
| **E-2** | **No PostgreSQL, no `psql`.** | Same as above. |
| **E-3** | **Python 3.14.4 installed.** Spec says 3.12+. | 3.14 satisfies the spec, but the future ML stack (torch, ctranslate2/faster-whisper, PySceneDetect's numpy/opencv chain) historically lags new CPython by 6–18 months. Pinning the project to **3.12** now avoids a forced downgrade at Phase 3/4. See **D-04**. |
| **E-4** | **Node v24.15.0, `uv` 0.11.27 present; `pnpm` absent.** | Fine. `uv` is a good default for the Python side. |
| **E-5** | **No FFmpeg.** | Not needed until Phase 2/4. Phase 0 must not depend on it. Worth installing before Phase 2. |
| **E-6** | **The repository currently lives under OneDrive** (`C:\Users\mauri\OneDrive\Desktop\Continnum`). | **HIGH.** OneDrive sync against a live `.git` directory and a running PostgreSQL data directory is a known source of index corruption, file locks, and `-PCNAME` conflict copies. It is also the wrong place for a multi-terabyte source vault, where OneDrive "Files On-Demand" produces placeholder entries that `stat()` reports as real files but which block for minutes on read. **Recommend: move the repo and all data roots to a non-synced local path** (e.g. `C:\Continuum\repo`, `D:\ContinuumData\source-vault`). See F-13. |
| **E-7** | Directory is named `Continnum` (double-n typo); handoff §0 specifies `Continuum/`. | Cosmetic, but the name will end up in paths, docs, and possibly a remote. Worth fixing at the same time as E-6. |
| **E-8** | Git reports CRLF conversion warnings on commit. | Add `.gitattributes` in Phase 0 (`* text=auto eol=lf`) before any code exists, or line-ending churn will pollute every future diff and break shell scripts. |

---

## 2. How to read this review

Findings are `F-nn` with a severity:

- **BLOCKER** — resolve before writing Phase 0 code; the wrong choice is a schema or filesystem migration later.
- **HIGH** — resolve within Phase 0.
- **MEDIUM** — resolve in the phase that first needs it; record the decision now.
- **LOW** — note and move on.

Decisions requiring sign-off are `D-nn` (§O). Genuinely blocking questions are `OQ-n` (§T).

---

## A. Contradictions and stale assumptions surviving v0.3

*(Review item 1)*

### F-01 — Three incompatible phase-numbering schemes — **BLOCKER**

The document contains three complete, conflicting phase plans:

| Phase | §43 (base) | §86 (v0.2) | §109 (v0.3, authoritative) |
|---|---|---|---|
| 2 | Canon Extraction MVP | Reader MVP | Reader / Media Center MVP |
| 3 | Anime Intelligence | Canon Extraction | Source Intelligence Foundation |
| 4 | Project + Branch Engine | Anime Intelligence | Anime / Multimodal Intelligence |
| 5 | Story Planner | Project + World Studio | Character / Canon Intelligence |

"Phase 4" therefore means three different things depending on which section an agent reads. The handoff's own §6–§9 uses v0.3 numbering, and the git tag scheme (`continuum-phase-0`) will encode it permanently.

**Fix (root cause, not patch):** add a one-line HISTORICAL banner to the top of §43 and §86 stating that they are superseded, and that **only §109 numbering is used in code, commits, tags, issues, branch names, and docs**. Do not renumber §109. Also note that §57 ("First 20 implementation issues") interleaves Phase 0 and Phase 1 work — items 8–10 and 13–20 are Phase 1 under v0.3 — and its closing line "Then start Phase 2" refers to the *old* Phase 2.

### F-02 — `franchise.yaml` inside the vault contradicts vault immutability — **BLOCKER**

§5 places `franchise.yaml` inside `source-vault/franchises/<id>/`. §2.1 and §108 say the vault is never modified. The moment the UI offers "edit franchise title / aliases / notes" — which §33 and §48 both require — the obvious implementation writes back to `franchise.yaml`, inside the vault.

This is the single most likely way vault immutability gets broken in practice, because it will feel like a *feature*, not a violation.

**Decision required (D-08):** `franchise.yaml` is **read-only user-authored input**. It is parsed on scan and its values seed database records. All app-managed franchise metadata lives in the database and `/library`. Continuum never writes it. If a user wants to change it, they edit the file themselves and re-scan. The storage layer must make this structurally impossible, not merely discouraged (see §B).

### F-03 — Data roots are shown inside the repository tree — **BLOCKER**

§3's monorepo tree lists `source-vault/`, `library/`, `projects/`, and `cache/` as siblings of `apps/` and `packages/`, inside `continuum/`. §108 instead treats them as data categories with no statement about location.

Consequences of the §3 reading: `git add -A` stages terabytes of media; `git clean -xdf` **permanently deletes the user's source library**; `.gitignore` becomes the only thing standing between a routine git command and irreversible data loss; and the repo cannot be cloned to a second machine without dragging data semantics along.

**Fix:** the data roots are **configured absolute paths outside the repository**, resolved at boot from config. The repository contains only `fixtures/demo_vault/` — a tiny synthetic vault used by tests. The `.gitignore` entries for the root names are a backstop, not the mechanism. Recorded in ADR-0001.

### F-04 — Storage root list differs in three places — **HIGH**

§3 defines 4 roots; §61 defines 5; §108 (authoritative) defines 8 (`/source-vault`, `/library`, `/projects`, `/generated`, `/jobs`, `/models`, `/cache`, `/config`); §109's Phase 0 bullet names only 5, omitting `/jobs`, `/models`, `/config`.

§3 also *mis-describes* `/projects` as "optional human-readable project exports" — under §108 it holds authoritative project state, which is a backup-criticality difference, not a wording difference.

**Fix:** §108's eight roots are canonical. Phase 0's path resolver must know all eight and validate `/config`, `/library`, `/projects`, `/generated`, `/cache` at boot (creating them if absent); `/jobs` and `/models` are optional and created lazily. Only `/source-vault` is read-only.

### F-05 — Redis is offered as a job substrate — **HIGH**

§4 lists "Redis for jobs/cache if background worker architecture is enabled." §91 requires durable job state that survives process death and PC shutdown; §111 forbids unnecessary infrastructure. An implementer reading §4 in isolation will reach for Celery + Redis, and job state will end up in a process-adjacent store that is not the database of record — which fails acceptance tests §110.7–110.10 in ways that only surface under crash testing.

**Fix:** PostgreSQL is the **sole** job store. Claiming via `SELECT … FOR UPDATE SKIP LOCKED`. No Redis, no Celery, no Temporal in Phase 0. Redis may return later purely as a cache or pub/sub *notification* transport, never as state of record. Recorded in ADR-0002.

### F-06 — Provider config example hardcodes cloud vendors — **HIGH**

§37's example configuration assigns `openai` and `anthropic` to planning/drafting/extraction. §90 requires `FREE_LOCAL` as the shipped default and boot with no cloud account; §111 forbids a cloud requirement for core library use.

**Fix:** the shipped default configuration resolves every capability to a local or null provider. §37's example should be relabeled as "an example of a *user-enabled hybrid* configuration," not the default. Phase 0 ships **no vendor SDK at all** (see F-38), which makes acceptance test §110.12 verifiable by dependency inventory rather than by inspection.

### F-07 — Cost tiers read as a cloud escalation ladder — **MEDIUM**

§50's Tier 2 ("cheap cloud model structured extraction") and Tier 3 ("frontier model") are written as normal parts of the extraction pipeline. Under §90 they are opt-in paths requiring explicit approval (§103).

**Fix:** reframe the tiers as escalation options **gated by the active `ProductionProfile`**. Under `FREE_LOCAL`, a task that cannot complete at Tier 0/1 must terminate as `BLOCKED(AWAITING_APPROVAL)` or produce a low-confidence record queued for review — never silently escalate. The enforcement point is designed in ADR-0004.

### F-08 — `SourceAsset.path` is a bare path column — **HIGH**

§9 gives `SourceAsset` a `path` field. §108 requires projects to move between machines. An absolute path breaks on migration; a relative path with no declared root is ambiguous once multiple vault roots exist (which §5's `franchises/` + `original/` split already implies).

**Fix:** `(root_key, relative_path, content_hash)`. `root_key` resolves through config. `content_hash` is the durable identity; the path is a *hint* for relocation. An asset whose file is missing becomes `OFFLINE`, not deleted (see F-33).

### F-09 — §44's "MVP" now spans eight v0.3 phases — **MEDIUM**

§44 defines the MVP as library → canon → project → bible → arc plan → chapter → validation. Under §109's order that is Phase 1 through Phase 8. Read as a near-term target it will create scope pressure on Phase 0–2.

**Fix:** relabel §44 as **"First Vertical Slice Goal (Phase 8 era)"**. It remains a good definition of when the product first becomes useful; it is not a milestone anyone should steer toward in the next several phases.

### F-10 — Real franchise names appear as layout examples — **LOW (with a hard rule attached)**

§5, §10, §18, §23, and §33 use real franchise, character, and title names illustratively. That is fine in prose. It is **not** fine anywhere else.

**Rule to enforce mechanically:** no real franchise/character/title string may appear in source code, database seed data, migrations, test fixtures, or fixture directory names. Only `fixtures/demo_vault/` synthetic content. §111 already forbids "actual copyrighted test fixtures," and §45's demo universe gives the correct pattern; a CI grep is cheap insurance.

### F-11 — §2.5's provider sketch predates v0.3's requirements — **MEDIUM**

The `TextModelProvider` / `EmbeddingProvider` / `ImageProvider` / `SpeechProvider` sketch has no capability metadata, no locality, no privacy class, no license note, and no model/version identity — all of which §90 requires and §91.2 requires jobs to record. Not a contradiction, but the sketch will be copied verbatim if left as the only concrete artifact. ADR-0004 supersedes it.

### F-12 — §35/§11 commit to delta-only branching without stating the cost — **MEDIUM**

"A branch references a parent event/state and stores only its changes. Never duplicate entire universes." is the right instinct and a significant design commitment: every read of project state becomes a resolve-through-ancestry operation, and §104's "archive/restore branch" and §35's "merge selected decisions" become materially harder than they look.

**Fix:** accept delta-only branching, but decide *now* that state resolution is a single, tested, centrally-owned function (`resolve_state(branch_id, at_time)`) with a materialization cache, rather than something each feature re-implements. Recorded in ADR-0003. Nothing is built in Phase 0.

### F-13 — Cloud-sync folders are unsafe for vault, database, and repo — **HIGH**

Not a spec defect; a deployment reality the spec never addresses (§108 covers backup but not sync). See E-6. Continuum should **detect** at boot whether any configured root sits under a known sync provider (OneDrive / Dropbox / Google Drive / iCloud) and warn prominently — the failure mode (silently blocking reads of placeholder files, and conflict-copy duplicates appearing as new assets in a scan) is very hard to diagnose from its symptoms.

### F-14 — Spoiler boundary spans phases with no stated hook — **MEDIUM**

§82 requires `indexed_through` (Phase 1/3) to be separated from `user_read_through` (Phase 2 reader progress), with enforcement in retrieval (Phase 3) and generation (Phase 5+). Nothing is needed in Phase 0, but the retrieval layer must carry a mandatory spoiler-boundary parameter from its first commit — retrofitting an *omission* filter into a retrieval API after callers exist is exactly how spoiler leaks happen.

---

## B. Can source-vault immutability be enforced structurally?

*(Review item 2)*

**Answer: yes, at four of five layers. The fifth (OS-level) can be offered and verified but not required.** Convention alone is not acceptable, and the spec currently only states the convention.

The design goal is that a future contributor — human or agent — who *tries* to write to the vault must fail at compile/lint/test time, not at code-review time.

### B.1 Layer 1 — Type-level separation (primary mechanism)

Two distinct, non-interchangeable types, in two distinct modules:

- `SourceVaultReader` — exposes `open_read()`, `stat()`, `iter_entries()`, `exists()`. **It has no write, delete, rename, or mkdir method at all.** Not a disabled one. Not one that raises. There is no method to call.
- `DerivedStore` — full read/write, but its root resolver physically cannot return a path under the vault root, because the vault root is not in its root table.

A write to the vault is therefore not "forbidden" — it is unrepresentable in the type system. This is the difference between a guard and a structural guarantee, and it is the one that survives contact with a future agent that is trying to be helpful.

### B.2 Layer 2 — One path-resolution function, TOCTOU-aware

A single `resolve_within(root, candidate) -> ResolvedPath` used by every filesystem operation in the product:

1. Reject absolute inputs and inputs containing NUL bytes or control characters.
2. Normalize, then **fully resolve symlinks** (`os.path.realpath` / `Path.resolve(strict=False)`), then confirm containment with `Path.is_relative_to(real_root)` where `real_root` is itself realpath'd. Containment must be checked **after** resolution, never before — checking first and resolving second is the classic bypass.
3. Re-verify after opening: `os.stat` the open file descriptor and compare `st_dev`/`st_ino` against the resolved target. This closes the TOCTOU window where a path is swapped between the check and the open. Use `O_NOFOLLOW` on the final component where the platform supports it.

**Windows-specific cases that must each have a test** (the primary machine is Windows 11, so these are not hypothetical):

| Case | Risk |
|---|---|
| Directory junctions and reparse points | Not POSIX symlinks; `realpath` resolves them in CPython 3.8+, but only if the code calls it |
| 8.3 short names (`PROGRA~1`) | Alias to a different literal path that string comparison misses |
| Alternate Data Streams (`file.txt:evil`) | A "path" that is not the file it appears to be |
| UNC and extended-length prefixes (`\\?\`, `\\server\share`) | Bypass normalization assumptions; `\\?\` explicitly disables normalization |
| Case-insensitivity | `SOURCE-VAULT` vs `source-vault` string compare |
| Reserved device names (`CON`, `NUL`, `COM1`, `LPT1`) | Open succeeds and is not a file |
| Trailing dots/spaces (`name. `) | Silently stripped by the filesystem, so two different strings address one file |
| Drive-relative paths (`C:foo`) | Resolve against a per-drive cwd, not the root |

Recommend property-based/fuzz testing (Hypothesis) over path inputs in addition to the enumerated cases.

### B.3 Layer 3 — Import-boundary enforcement in CI

Type separation only helps if nobody bypasses the module. Enforce in CI:

- No module outside `packages/storage` may import `os`, `shutil`, `pathlib`, `aiofiles`, `open()`, `zipfile`, `tempfile` for filesystem work. Enforce with `import-linter` contracts plus an AST check for bare `open(`.
- The check runs on every commit and is a hard failure.

This is the layer that actually prevents drift over years, and it costs about a day to build once.

### B.4 Layer 4 — Derived writes are content-addressed, not name-derived

All derived/generated files are written to `<root>/<sha256[0:2]>/<sha256>` (plus a DB row carrying the human name), never to a path built from a user-supplied filename or archive entry name.

This is a **root-cause fix rather than a guard**: if no user-controlled string ever reaches a write path, write-side traversal is structurally impossible and zip-slip is impossible, so those defenses never need to be correct. Writes are `write to temp in same directory → fsync → atomic rename`, which also gives crash-safety for free (see F-22).

### B.5 Layer 5 — OS-level hardening: offer and verify, do not require

Continuum cannot require the user to configure ACLs. It can:

- ship `scripts/harden_vault` (Windows: deny-write ACE for the app's user on the vault root via `icacls`; POSIX: read-only bind mount or an unprivileged runtime user);
- run a **startup capability probe** that attempts one write to a temp name inside the vault root, reports whether the OS refused, deletes it if it unexpectedly succeeded, and surfaces the result on the health endpoint as `vault_os_readonly: true|false`.

The probe is reported as a **health signal, not a boot failure** — otherwise the app is unusable for users who cannot change permissions.

### F-15 — No admin escape hatch should exist — **BLOCKER (decision)**

There must be **no** "advanced: allow vault writes" flag, no `--force`, no admin endpoint. The moment one exists, it becomes the thing a future agent reaches for when a feature is inconvenient, and the guarantee is gone. Deleting or reorganizing source media is the user's job, in their file manager.

Recorded as **D-13**.

### F-16 — Vault identity cannot be a marker file — **HIGH**

The obvious way to detect "you pointed Continuum at a different vault" after a machine move is to drop a `.continuum-vault-id` file in the root. **That is a vault write.** It looks harmless and it breaks the invariant on day one.

**Fix:** vault identity lives in `/config`, as a declared `root_key` plus a *non-authoritative* fingerprint (e.g. a hash over the sorted top-level entry names and sizes) used only to warn "this does not look like the vault this project was built against." Never written into the vault.

---

## C. Data-model boundaries

*(Review item 3)*

The spec names the layers but never states the invariant that keeps them apart. Without one, "canon leaks into project state" is a bug class that recurs forever and is caught only by careful review.

### C.1 The proposed invariant: four tiers, one direction

| Tier | Contents | Mutability |
|---|---|---|
| **A — Observed source** | `SourceAsset`, `SourceSegment`, raw locators | Append-only. Never edited by the app. Keyed by content hash. |
| **B — Interpretation of source** | `CanonClaim`, source `Character`/`CharacterVersion`, `Event`, `Relationship`, `SourceBrain`, `CraftPrinciple` — all carrying provenance → Tier A, plus confidence and status (explicit / inferred / user-defined) | Versioned and correctable. Corrections create new revisions; history is never destroyed. Grouped by `SourceCanonSnapshot`. |
| **C — Project continuity** | `Project`, `Branch`, `ProjectCharacterState`, `StoryCalendarEvent`, world/institution/faction state, `VisualDesign`, `OutfitAssignment`, `ChangeGraph` edges | Mutable via events/deltas, branchable |
| **D — Generated artifacts** | `Artifact`, `ArtifactVersion`, `GenerationRecipe`, lineage edges | Reproducible from recipe; disposable with recipe retained |

**The invariant: dependency arrows point only downward — D → C → B → A. Never upward, never sideways across a project boundary.**

Concretely:

- **No foreign key may exist from Tier A or B to Tier C or D.** This is mechanically testable: a CI test reflects the SQLAlchemy metadata, classifies each table by tier, and asserts no FK violates the ordering. That single test enforces "canon and project continuity are separate" (§2.2) better than any amount of review discipline.
- **Tier C never writes Tier B.** A "canon sync" (§71–74) is *not* an edit to canon. It is: (1) a new Tier B snapshot appears; (2) a Tier C **adoption decision record** describes what the project does about it. This is precisely §89's principle, expressed as a schema rule.
- **Tier B never references "current."** Everything is snapshot-scoped.

### F-17 — `CharacterBrain` must be two entities, not one — **BLOCKER**

§94 describes the Character Brain as one concept and then, in its final paragraph, admits it has "Source Brain material and Project Character State material." Modelled as one table with a `project_id NULL` column, the first "learn from the project's own chapters" feature writes project-derived behavior into rows that canon retrieval also reads — and source canon is quietly corrupted with project fiction. That is unrecoverable without provenance archaeology.

**Fix:** two entities in two tiers.

- `SourceBrain` (Tier B): snapshot-scoped, every rule carries evidence links to Tier A locators and a confidence.
- `ProjectBrainOverlay` (Tier C): branch-scoped, references a `SourceBrain` revision as its base, holds divergence and project-earned growth.

The "brain" a writer prompt consumes is **composed at read time** from `(SourceBrain@snapshot) + (overlay@branch, at project time)`. Never a merged stored row. This also makes §70's example (source Okarun vs project Okarun) fall out of the schema for free rather than needing special handling.

### F-18 — `SourceCanonSnapshot` has two incompatible meanings — **BLOCKER**

§69 defines a snapshot as source cutoff + assets + claims + arc boundaries. But that bundles two independent axes:

1. **Material cutoff** — which source assets exist / how far the user has ingested ("through chapter 190").
2. **Interpretation version** — which extractor, model, and prompt version produced the claims.

Re-running extraction with a better model at the same story cutoff changes the claims but not the material. If both live in one snapshot ID, then either (a) re-extraction silently mutates what a project believes it branched from, or (b) the user cannot ever improve extraction without orphaning projects.

**Fix:** `SourceCanonSnapshot = (material_cutoff_descriptor, asset_set_hash, extraction_run_id, extractor_version)`. Re-extraction at the same cutoff produces a **new snapshot**. A project pins a snapshot ID; moving to a newer one is an explicit, diffable, user-approved action — reusing the machinery §71–74 already defines for canon deltas. Nothing is built in Phase 0; the *definition* must be settled now because it determines the shape of the pinning FK.

### F-19 — Change Graph must be rebuildable, never authoritative — **HIGH**

§76 makes the Change Graph the mechanism for "what does this break." If a dependency is recorded *only* as a graph edge, a bug in edge-writing silently loses continuity relationships with no way to detect it.

**Fix:** the Change Graph is a **derived index** over facts that exist elsewhere (a chapter references a character state; a scene references an event). It must be droppable and fully rebuildable by a job. That gives a strong acceptance test — `rebuild_change_graph()` must be a no-op on a healthy database — and it removes an entire class of silent corruption.

### F-20 — Deletion and retention semantics are undefined — **HIGH**

§62 says "removing an item from Continuum removes derived records by default, not originals." That leaves the hard questions open: what happens to `CanonClaim`s whose only provenance was that asset? To generated artifacts that used it as a reference? To reader progress and notes?

**Fix (recommended policy, to be recorded in ADR-0003):** soft-delete the asset; cascade-delete only pure caches; **never** delete Tier B claims — mark them `provenance_status = MISSING_SOURCE` so they remain visible and inspectable but are down-ranked in retrieval and cannot be promoted to locked canon. User notes and reader progress survive independently. Silent cascade deletion of user-corrected knowledge would be the worst data-loss bug this product could have, and it is the default behavior of a naive `ON DELETE CASCADE`.

### F-21 — Optimistic concurrency is needed on mutable project state — **MEDIUM**

Two browser tabs, or a user editing while a worker writes a post-chapter state delta, will silently last-write-wins. Add `row_version` to every mutable Tier C row from the first migration that creates one. Free now; a data-integrity incident later.

---

## D. The durable Job / JobStep / JobCheckpoint model

*(Review item 4)*

§91 is the strongest section of the specification. The gaps below are all *omissions* rather than errors, but several of them are the difference between a job system that passes §110's tests and one that passes them by accident.

### D.1 What the spec gets right

Durable state in the database; the UI as a client rather than the owner; checkpointing at the smallest practical unit; graceful shutdown persisting a checkpoint; ETA learned from telemetry rather than a benchmark; `BLOCKED` for missing models rather than discarding the recipe. All correct, all kept.

### F-22 — Effect idempotency, not checkpoint frequency, is what makes resume safe — **BLOCKER**

§91.3 says checkpoint often. That is necessary and insufficient. Consider: the worker completes unit 7 (writes a thumbnail, inserts a row), then dies **before** the checkpoint commits. On restart, unit 7 re-runs. If its effect is not repeat-safe, the system now has a duplicate row or a half-written file — and no amount of checkpointing prevents it, because the window is between the effect and the record of the effect.

**The rule that actually makes at-least-once execution behave as effectively-once:**

1. Every unit's side effect is either (a) a **content-addressed file write** — temp file in the destination directory, fsync, atomic rename to its hash-named final path, so a repeat is a byte-identical no-op — or (b) a **deterministic upsert** keyed by a natural key derived from the input, never by an autoincrement.
2. The unit's completion record and its checkpoint advance commit in the **same database transaction**.
3. Ordering is always: perform effect → durably land the effect → commit the completion record. A crash anywhere re-runs a unit whose effect is a no-op.

This must be stated as a foundation invariant in ADR-0002 and exercised by a synthetic job in Phase 0 that is deliberately killed mid-unit. §110.10 ("resumes only unfinished units") is currently satisfiable by a job that simply never re-runs anything — the test must additionally assert that a *forced* re-run of a completed unit produces no duplicate and no corruption.

### F-23 — Missing `CANCELLING` state — **HIGH**

§91.1 defines `PAUSING` (acknowledging that stopping a running step is asynchronous) but jumps straight to `CANCELLED`. Cancellation of a long-running step is equally asynchronous. Without `CANCELLING`, either the UI lies ("cancelled" while a GPU job runs for another six minutes) or the implementation hard-kills the worker.

**Fix:** add `CANCELLING`. Both pause and cancel are cooperative: the worker checks the flag between units.

### F-24 — `BLOCKED` conflates four different situations — **HIGH**

§91.5 uses `BLOCKED` for a missing model. §103 implies blocking for approval. §91.2 implies blocking on job dependencies. The remediation the UI must offer is completely different in each case.

**Fix:** `BLOCKED` plus `blocked_reason ∈ {DEPENDENCY, MISSING_PROVIDER, MISSING_MODEL, MISSING_SOURCE_ASSET, AWAITING_APPROVAL, RESOURCE_UNAVAILABLE}`, plus a structured `remediation` payload (what is missing, what the user should do). This is what makes the §107 Production Queue screen actionable rather than a wall of "blocked."

### F-25 — No `run_after` field, so `FAILED_RETRYABLE` has no scheduling semantics — **HIGH**

The state exists but nothing says *when* it retries. Without `run_after`, a permanently-failing job spins at full speed against a dead provider.

**Fix:** `attempt`, `max_attempts`, `run_after` (timestamptz), exponential backoff with jitter, and an `error_history` append-only JSONB list (capped) alongside `last_error`. Errors carry a **classification** (`RETRYABLE_TRANSIENT`, `RETRYABLE_RESOURCE`, `PERMANENT_INPUT`, `PERMANENT_CONFIG`) decided by the handler, not inferred from the exception type at the call site.

### F-26 — No job-level idempotency key, so double-clicking "Scan" queues two scans — **HIGH**

Nothing in §91 prevents duplicate job creation. Two concurrent scans of the same vault is a race, not just waste.

**Fix:** `dedupe_key = hash(job_type, input_hash, recipe_version)` with a partial unique index over non-terminal statuses. Enqueue becomes get-or-create. Cheap, and it removes a whole class of "why do I have three of these" support questions.

### F-27 — No lease/heartbeat model, so a crashed worker's job is stuck forever — **BLOCKER**

§91.4 says "unexpected process termination must leave enough durable state to recover." It does not say *what recovers it*. A job left in `RUNNING` by a killed worker will sit in `RUNNING` indefinitely, because nothing distinguishes it from a job that is genuinely running.

**Fix:** `lease_owner` (worker id), `lease_expires_at`, refreshed by a heartbeat while the unit runs. A reaper (any worker, or the API on a timer) transitions expired-lease `RUNNING` jobs back to `QUEUED` with `attempt += 1`. Combined with F-22's effect idempotency, this makes crash recovery automatic rather than manual. All timestamps use the **database clock** (`now()`), never worker local time, so clock skew cannot expire a live lease.

### F-28 — Pause/cancel/retry races need request flags, not direct status writes — **HIGH**

The handoff's own audit checklist calls out "race conditions around pause/cancel/retry." The cause is always the same: the UI writes `status = 'PAUSED'` while the worker concurrently writes `status = 'SUCCEEDED'`, and one clobbers the other.

**Fix:** requests are **flags** (`pause_requested`, `cancel_requested`), never status writes. Only the worker (and the reaper) may write `status`, and only through a single guarded transition function with an explicit allowed-transition table, inside a transaction holding the row lock. Illegal transitions raise rather than silently no-op. This is testable directly: assert the transition table rejects `SUCCEEDED → PAUSED`.

### F-29 — Two checkpoint patterns are needed; the spec implies one — **MEDIUM**

§91.3's examples mix ordered streams (subtitle segments, frame batches — a **cursor** is natural) with unordered sets (per-file ingestion, per-asset generation — a **unit table** is natural). Phase 1's scanner needs the latter; Phase 4's transcription needs the former.

**Fix:** one mechanism covers both. `job_step` rows keyed `(job_id, unit_key)` unique, with an optional `ordinal` for ordered work. The cursor is then just "max completed ordinal," and unordered work ignores `ordinal`. Implementing two separate mechanisms is the thing to avoid.

### F-30 — No resource-concurrency model — **MEDIUM**

The system will eventually need "only one GPU job at a time, but eight hashing jobs." Retrofitting that requires a schema change and a scheduler rewrite.

**Fix:** add `resource_class` (a string, e.g. `cpu`, `gpu`, `network`, `disk`) to the job row **in Phase 0**, and implement the simplest possible limiter (a per-class max-concurrency config consulted at claim time). The field costs nothing now; the migration costs real work later.

### D.2 Recommended Phase 0 job contract, in one place

- **Store:** PostgreSQL only. Claim: `SELECT … WHERE status='QUEUED' AND run_after <= now() ORDER BY priority DESC, created_at FOR UPDATE SKIP LOCKED LIMIT 1`.
- **States:** `QUEUED`, `BLOCKED`, `RUNNING`, `PAUSING`, `PAUSED`, `CANCELLING`, `CANCELLED`, `SUCCEEDED`, `FAILED_RETRYABLE`, `FAILED_FINAL`. Terminal: `SUCCEEDED`, `FAILED_FINAL`, `CANCELLED`.
- **Transitions:** one guarded function; explicit table; illegal transitions raise.
- **Requests:** `pause_requested` / `cancel_requested` flags only.
- **Leases:** owner + expiry + heartbeat + reaper, on the DB clock.
- **Units:** `job_step(job_id, unit_key UNIQUE, ordinal NULL, status, attempt, last_error)`.
- **Checkpoints:** `job_checkpoint(job_id, seq, payload JSONB | locator, created_at)`; latest-wins with a small retained history.
- **Dependencies:** `job_dependency(job_id, depends_on_job_id, kind)`; cycle check at insert; a failed dependency **blocks** the dependent rather than cancelling it (the user decides).
- **Audit:** `job_event` append-only — every transition, lease event, error, and checkpoint. This is what makes the Codex audit's "incomplete error state/retry recording" checkable.
- **Progress:** `units_done` / `units_total`, `elapsed_active_ms`. ETA shows `Estimating…` until N samples; store a `hardware_signature` string column now so samples can be partitioned later without a migration (do **not** build `HardwareExecutionProfile` as an entity — see F-60).

---

## E. Can closing the UI safely stay independent from background workers?

*(Review item 5)*

**Yes — and it should be guaranteed by process topology, not by careful coding.**

### E.1 The topology

Four processes in development, three in "production":

```
[ web (Next.js) ]  →HTTP→  [ api (FastAPI) ]  →SQL→  [ postgres ]
                                                          ↑
                            [ worker (separate OS process) ]
```

The API **enqueues and reads**. It never executes job work. The worker **only** talks to the database. There is no API→worker channel at all in Phase 0 — no RPC, no socket, no shared memory. Consequently §110.8 ("closing/restarting the web UI does not cancel the worker job") is *structurally* true rather than incidentally true, which is the whole point.

Corollary rules:

- **No FastAPI `BackgroundTasks` for anything durable.** It dies with the request and the process.
- **The worker is never a child process of the API or of the dev server.** A Next.js hot-reload or a uvicorn `--reload` restart must not be able to kill it.
- **When a desktop wrapper arrives later (§91.4), it must attach to an already-running worker service, never spawn one as a child of the window.** Electron/Tauri kill child processes on window close by default — this is exactly the trap §91.4 is warning about, and it needs to be written into ADR-0002 now, before the wrapper exists and the shortcut is tempting.

The test matrix should cover all four restart directions, not just the one §110 names: UI restart, API restart, worker restart, and database restart.

### F-31 — Graceful shutdown needs a Windows-viable channel — **HIGH**

§91.4 requires graceful worker shutdown that persists a checkpoint. On POSIX this is a `SIGTERM` handler. **Windows has no real `SIGTERM`**; `CTRL_BREAK_EVENT` requires process-group setup, and a taskkill is unconditional. The primary development machine is Windows 11, so a POSIX-only design will be untested on the platform it actually runs on.

**Fix:** two channels, both supported, same code path:

1. Signal handler (`SIGINT`/`SIGTERM`) where the platform provides it.
2. A **database-visible drain flag** — a `worker` table row with `drain_requested`, polled between units. `POST /workers/{id}/drain` sets it. This works identically on every platform, is observable in the UI, survives the API being down, and makes "graceful stop" a testable state transition rather than a signal-delivery race.

The `worker` table also gives the Production Queue screen something honest to display ("2 workers alive, last heartbeat 3s ago") and makes the lease reaper's decisions auditable.

### F-32 — Docker is not installed, so "one command starts the app" is undefined — **BLOCKER (environment)**

See E-1/E-2 and **OQ-1**. §110.1 is an acceptance test; it cannot be written until the database strategy is chosen. Recommendation: Docker Desktop for PostgreSQL + pgvector only (`docker compose up db`), with API/worker/web run natively via `uv` and `pnpm`. Rationale: pgvector is genuinely annoying to install natively on Windows, while the Python and Node sides are pleasant to run natively and much easier to debug than through a container.

---

## F. Migration and recovery: different PC, missing models

*(Review item 6)*

### F.1 What must survive a machine move

`/config` (minus secrets), the database, `/projects`, `/library`, `/generated`, plus job state and checkpoints. `/cache` is disposable by definition. `/source-vault` and `/models` may be very large and may legitimately be absent on the new machine.

### F-33 — Missing source assets must degrade, not delete — **HIGH**

A user opening the project on a laptop without the multi-terabyte vault attached must still be able to browse the library, read notes, and inspect canon. A scanner that treats "file not found" as "asset deleted" would destroy the derived library on first run.

**Fix:** an asset whose file is absent transitions to `OFFLINE` (with `last_seen_at`), never to deleted. Derived records remain fully usable. Re-attaching the vault restores `ONLINE` by content hash, **not by path** — which also handles the user reorganizing their folders, a thing users do constantly.

### F-34 — Missing model/provider blocks, and the recipe survives — **MEDIUM (spec already correct; stating the mechanism)**

§91.5 is right. The mechanism: the recipe records `required_capability` + `required_model_ref` + version constraints. On claim, the scheduler checks the registry; if unsatisfiable, `BLOCKED(MISSING_MODEL)` with a remediation payload naming the model and where it was expected. Never discard, never substitute silently. A *user-approved* substitution creates a new recipe revision so lineage stays honest.

### F-35 — Migration safety needs a stated downgrade policy — **HIGH**

§110.14 requires "migration downgrade/upgrade strategy is documented and clean-database migration is tested." §46.8 says "no silent destructive migrations." Neither states what downgrade actually promises.

**Recommended policy (ADR-0003):**

- Alembic, **single head enforced in CI** (a multi-head merge conflict discovered at runtime is a very bad day).
- Every migration is reviewed for destructiveness; column drops are two-phase (deprecate, then drop in a later release).
- **Downgrade is best-effort and explicitly not a data-preservation guarantee.** The supported recovery path is restore-from-backup. Say this plainly rather than implying reversibility the migrations do not have.
- Tested in CI: clean DB → `upgrade head`; and `upgrade head` → `downgrade base` → `upgrade head`.

### F-36 — Backup consistency between database and filesystem is unspecified — **HIGH**

§108 lists *what* to back up but not *how to keep it consistent*. A database dump taken at T referencing artifacts written at T+1 restores to a database pointing at files that do not exist.

**Fix:** a documented ordering (quiesce workers → dump DB → snapshot filesystem roots → write a `backup_manifest` recording DB dump id, root hashes, schema revision, and app version) plus a restore-time verification pass that reports dangling references rather than crashing on them. Because artifacts are content-addressed (§B.4), a *missing* file is detectable and a *changed* file is impossible — which is most of the problem solved by the storage convention rather than by the backup tool.

Phase 0 deliverable is the **ADR only** (§109 explicitly says "backup/export design ADR, not full backup product").

---

## G. Provider abstraction risks; keeping FREE_LOCAL default without hardcoding a model

*(Review item 7)*

### G.1 The four failure modes

1. **Interface shaped like one vendor.** If `TextModelProvider.generate()` takes `messages` and `tools` in one vendor's exact schema, every local adapter becomes a translation layer and the "abstraction" leaks. **Fix:** define the interface around *Continuum's* needs — a prompt package, a response schema, a budget, and a privacy class — and let each adapter map inward.
2. **Capability lying.** A provider that advertises structured output but does not enforce it will return prose where a schema was promised. **Fix:** schema validation and repair live **above** the provider interface, in a shared call wrapper, so every provider gets the same guarantee regardless of native support. Validation failures are recorded on the job, not silently retried forever.
3. **Silent escalation to paid.** The most damaging possible bug in a $0-default product. **Fix:** the policy resolver returns *permitted* providers only; if none can satisfy the capability, the job becomes `BLOCKED(AWAITING_APPROVAL)` with the cost class named. There is no code path from a `FREE_LOCAL` profile to a remote provider that does not pass through an explicit user approval. Testable with a fake "expensive" provider and an assertion that it is never invoked under `FREE_LOCAL`.
4. **A model name hardcoded as a default constant.** This is how "model-agnostic" quietly dies. **Fix:** no model identifier literal may appear outside `packages/providers/registry/` and `/config`. Enforce with a CI check for known vendor/model naming patterns in application code. This makes §90's "no specific AI model hardcoded as mandatory" a *test*, not an aspiration.

### F-37 — Every provider call must declare a data class — **HIGH**

§40 requires a per-franchise `LOCAL_ONLY` flag and "provider upload must be explicit/configurable." That is unenforceable unless the call site says what it is sending.

**Fix:** every provider invocation carries a `DataClass ∈ {SOURCE_EXCERPT, DERIVED_METADATA, PROJECT_TEXT, USER_NOTE, SYNTHETIC}`. Policy rules are expressed against it — e.g. "`SOURCE_EXCERPT` may never go to a `REMOTE` provider," "a `LOCAL_ONLY` franchise's content may never leave the machine in any class." The parameter is **required**, not defaulted, so a new call site cannot forget it. Phase 0 defines the enum and the check and exercises both with fake providers.

### G.2 Phase 0 provider deliverable (concrete)

- `ProviderCapability` enum: `TEXT_GENERATE`, `TEXT_STRUCTURED`, `EMBED_TEXT`, `EMBED_IMAGE`, `TRANSCRIBE`, `IMAGE_GENERATE`, `IMAGE_EDIT`, `SPEECH_SYNTHESIZE`, `VIDEO_GENERATE`.
- `ProviderDescriptor`: `id`, `capabilities`, `locality ∈ {LOCAL, REMOTE}`, `cost_class ∈ {FREE, METERED, PAID}`, `privacy_class`, `license_note`, `model_ref`, `version`, `requirements` (VRAM/disk hints, optional).
- `ProviderRegistry` — descriptors from config, no vendor SDK imported.
- `ProviderPolicy` — resolves `(capability, data_class, active ProductionProfile) → permitted provider | BLOCKED(reason)`.
- **Fakes only:** `EchoTextProvider`, `DeterministicEmbeddingProvider` (hash-based vectors), `NullImageProvider`. Deterministic, offline, zero dependencies.

### F-38 — Phase 0 should ship zero AI SDK dependencies — **MEDIUM (recommended)**

Adding no vendor SDK at all makes §110.12 ("no paid/cloud credentials are required") verifiable by reading `docs/DEPENDENCIES.md`, rather than by auditing code paths. It also keeps the first dependency inventory honest and small. Real providers arrive in the phase that first needs one (transcription, Phase 4).

---

## H. Artifact recipes and lineage

*(Review item 8)*

§92 is correct and is the key to remasterability. Two mechanisms make it work, and both need to be decided now even though nothing is built until Phase 10+.

### F-39 — The recipe must be split into intent and execution — **HIGH**

§92 says the system "must distinguish creative decisions from render implementation," then lists both in one flat field list. Flat, the distinction is unenforceable and selective rerender degenerates into "regenerate everything whose recipe hash changed."

**Fix:** two parts with two hashes.

- **`intent`** — story/episode/scene/shot IDs, approved script revision, character-state snapshot IDs, outfit/design variant IDs, reference asset IDs, timing, approved performance direction, approval state.
- **`execution`** — provider, model ref and version, adapters/LoRAs, seed(s), sampler and settings, prompt-template package version, input artifact IDs, post-processing chain.

Then: **a remaster is a new `execution` over an unchanged `intent`.** "Is this shot still creatively valid?" compares `intent_hash` only. "Do we need to re-render?" compares `execution_hash`. Selective rerender (§92) and provider migration both fall out of this split; without it, they are bespoke logic.

### F-40 — Content-addressed artifact storage should be settled in Phase 0 — **HIGH**

`/generated/<sha256[0:2]>/<sha256><ext>` plus a database row for identity, naming, and versioning. This gives deduplication, atomic writes, crash-safety, corruption detection, and safe re-runs (F-22) from one convention. Retrofitting content addressing after thousands of artifacts exist means rewriting every path in the database.

**Phase 0 builds only:** the hashing helper, the `/generated` root resolution, and the ADR. No artifact tables.

### F-41 — Lineage must mark stale, never auto-delete or auto-regenerate — **MEDIUM**

Lineage edges `(artifact_version_id, derived_from_id, role)`. When an upstream input changes, descendants are marked `STALE` and surfaced for review. They are never deleted (the user may still want the old render) and never automatically regenerated (§2.4 human control; §101 "never spend expensive compute while an upstream cheap decision is unapproved").

### F-42 — Recipes need a schema version so old recipes stay interpretable — **MEDIUM**

`recipe_schema_version` and `template_package_version` on every recipe. A recipe written in 2026 must still be *readable* in 2028 even if it is no longer *runnable*. Reinterpreting an old recipe under new field semantics would silently change what a stored creative decision meant.

---

## I. Visual Lab data boundaries

*(Review item 9)*

§100.6 states the critical rule — do not define a character by one model checkpoint or LoRA — but the entity list in §106 does not reflect it. Modeled naively, `VisualDesign` ends up holding a LoRA path, and the character's identity becomes hostage to one provider's file format.

### F-43 — Four-way separation of visual concepts — **MEDIUM (decide now, build Phase 10)**

| Entity | Tier | Contents |
|---|---|---|
| `VisualIdentity` | C | Model-independent: canonical description, proportions, palette, silhouette notes, hard constraints, reference **artifact** IDs. Survives every provider change. |
| `VisualDesign` / `VisualDesignVariant` | C | Outfit / hair / expression / accessory variants, with `status ∈ {IDEA, EXPERIMENT, IN_REVIEW, APPROVED, LOCKED, DISCARDED, WHAT_IF}` |
| `OutfitAssignment` | C | Design → (character, branch, arc/episode/scene, project-time range, occasion, climate, in-world origin, reuse policy) |
| `ProviderAssetBinding` | infrastructure | LoRA / embedding / checkpoint files: hash, provider compatibility, **license and authorization notes**, version. Replaceable. **Never referenced by any story record.** |

Story records reference `VisualIdentity` and `VisualDesign`. Only the render layer touches `ProviderAssetBinding`. Swapping image models then changes bindings, not the character.

### F-44 — Outfit assignment scope conflicts have no resolution rule — **MEDIUM**

§100.4/§100.5 allow a design scoped to "project, arc, episode, scene, season, climate, location, or date range." Two designs will inevitably both match one scene, and the spec is silent on what happens.

**Fix:** deterministic precedence — **scene > episode > arc > season > date-range > climate/location > project** — with ties surfaced as an explicit conflict for the user rather than resolved arbitrarily. Silent arbitrary resolution in a continuity product is worse than an error.

### F-45 — Moodboard references need an intended-use flag *and* a rights flag — **MEDIUM**

§100.2 already says "do not assume the user wants literal copying." Given §2.8 and §111, that needs to be structural: each reference records `reference_use ∈ {silhouette, palette, material, pose, camera, expression, architecture, lighting, mood}` **and** an explicit `direct_input_allowed` boolean (default `false`) controlling whether the asset may ever be fed to a generator as img2img/ControlNet input rather than merely informing a description. Default-deny is the right default for third-party reference imagery.

---

## J. Source intelligence, RAG, provenance — avoiding a giant fine-tune

*(Review item 10)*

§93's architecture is right, and "retrieval over giant fine-tuning" (§93.2) is the correct call for the stated reasons: citability, correctability, branchability, removability. Three things are missing that determine whether it actually works.

### F-46 — Stable source locators are the load-bearing primitive and are undefined — **BLOCKER**

Every provenance claim, every citation, every "show me why you believe this," every reader bookmark, and every Send-to-Project reference is an address into source material. §9's `SourceSegment.locator` is one unspecified field.

If a locator is derived from a database row ID, then re-ingesting the same file — after a scanner improvement, a database restore, or a machine move — produces different IDs, and **every stored citation silently points somewhere else or nowhere.** This is a slow, quiet, catastrophic failure that will not be noticed until the corpus is large.

**Fix — the locator is derived from content, never from row identity:**

```
<medium>:sha256:<asset_hash>#<unit-address>

cbz:sha256:ab12…#page=12
epub:sha256:cd34…#para=417          (or #cfi=… once epub.js is adopted)
pdf:sha256:ef56…#page=88&span=1204-1319
video:sha256:0a1b…#t=00:12:03.400-00:12:07.100
sub:sha256:2c3d…#line=88
```

Properties required: **deterministic** (same bytes → same locator), **human-inspectable**, **stable across re-ingest**, **resolvable without a database** (given the file, you can find the passage), and **coarse-to-fine** (a page locator remains valid when panel-level locators are added later).

Decide the format **now**, in ADR-0005. Implement it in Phase 1/2. Everything downstream of Phase 3 assumes it.

### F-47 — Embeddings must not be a column on the segment — **HIGH**

The natural implementation puts `embedding vector(768)` on `SourceSegment`. Then switching or upgrading an embedding model requires destroying the old index, re-embedding the entire corpus before search works again, and there is no way to A/B two models or to keep image and text embeddings side by side.

**Fix:** `segment_embedding(segment_id, embedding_model_ref, dim, vector, created_at)` — model-versioned rows, additive, multiple coexisting indexes, and re-embedding is a normal durable job rather than a migration. pgvector supports this fine.

### F-48 — Retrieval quality needs an eval harness before any fine-tuning conversation — **MEDIUM**

§93.2 defers fine-tuning "until measured tests show a benefit," but no measurement exists. Without one, the fine-tuning question gets settled by enthusiasm.

**Fix:** the synthetic golden corpus (§45, §88) ships with labelled question→locator pairs and a recall@k / citation-accuracy harness, from Phase 3. Any future adapter or fine-tune must beat retrieval on that harness, plugged in behind the same provider interface, and may never become the sole store of canon (§93.2).

### F-49 — Corrections must key on locator + claim identity, not on extraction run — **HIGH**

§93.4 requires that corrected knowledge is preferred in future retrieval. If a correction is attached to an extraction-run row, the next re-extraction orphans it and the user's work is silently lost — the single most demoralizing possible bug in a review-loop product.

**Fix:** a correction is a first-class Tier B record keyed by `(claim_identity, locator)`, carrying higher precedence than any extraction output, surviving re-extraction, and re-applied automatically to the new snapshot with a conflict report where the underlying claim materially changed.

---

## K. Security, privacy, path traversal, symlinks, secrets

*(Review item 11)*

Path and symlink handling is covered in §B. The remaining risks:

### F-50 — The API must bind to loopback and must never take a path parameter — **BLOCKER**

Phase 0 has no authentication, which is reasonable for a local-first single-user tool — **but only if the API is bound to `127.0.0.1`**. An unauthenticated service that reads the filesystem, bound to `0.0.0.0`, is a file-disclosure service on any network the machine joins (a café Wi-Fi, a shared dorm LAN).

Two hard rules for ADR-0004:

1. Default bind `127.0.0.1`; binding to any other interface requires an explicit config change that **also** requires authentication to be configured. The config validator enforces the pairing at boot, so the insecure combination is unreachable.
2. **No endpoint accepts a filesystem path as a parameter.** All file access is by asset ID or artifact ID. A `GET /files?path=…` endpoint is a directory-traversal machine no matter how carefully it validates, and it will be proposed at some point because it is convenient.

CORS restricted to the configured web origin; no wildcard.

### F-51 — Archive and media parsing are untrusted-input surfaces — **HIGH (Phase 1/2, pre-committed now)**

CBZ/ZIP handling must pre-commit to: never write files using archive entry names (§B.4's content-addressing makes zip-slip structurally impossible), reject absolute or `..`-containing entry names, cap uncompressed size and compression ratio (zip bombs), reject symlink entries, and cap entry count.

FFmpeg, PDF, and EPUB parsers are large C/JS attack surfaces fed by arbitrary user files. **They run in the worker process, never in the API**, with timeouts and memory caps, and a parser crash is a job failure rather than an application failure. The worker boundary (§E) delivers this for free — which is another reason it is worth having in Phase 0.

### F-52 — EPUB rendering is remote-content and script execution — **HIGH (Phase 2, flagged now)**

An EPUB is a zip of XHTML+CSS+JS. Rendering it in the reader means rendering **untrusted HTML in the application's origin**. epub.js does not solve this for you.

**Fix:** render inside a sandboxed iframe (`sandbox` without `allow-same-origin`), a strict CSP that blocks all remote loads (so a malicious or merely tracking EPUB cannot phone home and cannot deanonymize a private library), and script stripping. This is worth writing down now because it is a Phase 2 decision that is very hard to add after the reader ships.

### F-53 — Secret redaction needs a value registry, not only patterns — **MEDIUM**

§40 requires key redaction from logs. Pattern-based redaction misses secrets that do not look like secrets (a short shared token, a local password). **Fix:** a `SecretStr` type whose `__repr__`/`__str__` redact; a logging filter that scrubs both by pattern **and** by exact match against the registry of loaded secret values; secrets never stored in the database; `.env` gitignored (already done) with a values-free `.env.example`. Test: dump the full effective config to the log at DEBUG and assert no secret value appears (§110.13).

### F-54 — Privacy classification is per-franchise but enforcement is per-call — **MEDIUM**

§40's `LOCAL_ONLY` franchise flag only works if it reaches the provider call. It does so via F-37's `DataClass` plus a franchise/project scope on the call context. Stated here so the two mechanisms are understood as one.

---

## L. Licensing and dependency concerns

*(Review item 12)*

The shortlist's classifications are sound. Four gaps:

### F-55 — Model weight licenses are not covered anywhere — **HIGH**

The shortlist covers **code** licenses carefully and **model weight** licenses not at all. These are independent, and the weights are what Continuum will actually ship or download: Whisper weights, Stable-Diffusion-family checkpoints, community LoRAs, and TTS voices each carry their own terms — several of which (OpenRAIL-style, non-commercial, or "no likeness" clauses) directly touch §2.8 and §111's stance on voice cloning and third-party likeness.

**Fix:** `docs/DEPENDENCIES.md` gets a **separate Model Assets section** recording, per weight file: source, license, redistribution permitted (yes/no), commercial use, and any likeness/authorization constraint. Continuum should never bundle weights it cannot redistribute — it should point at them and let the user fetch them, recording the license note in `ProviderDescriptor` (§G.2).

### F-56 — Jellyfin is GPL-2.0; the rule needs to be explicit — **MEDIUM**

"REFERENCE ONLY" is correct but too soft for an agent-driven project. State the rule as: **no code, no code fragments, and no line-by-line ports from GPL sources.** Architectural and UX inspiration only, from reading documentation and observing behavior. Komga is MIT, so reuse is permissible *with attribution* — but the shortlist's own advice (its Kotlin stack does not match Continuum) means reference-only is right there too.

### F-57 — FFmpeg licensing depends on the build, and on who ships it — **MEDIUM**

Invoking a **user-installed** binary via subprocess creates no linking relationship — that is the right choice and the shortlist says so. The line to write down: **Continuum does not distribute FFmpeg.** If a bundled build is ever considered (a plausible "make setup easier" impulse), the licensing analysis must be redone, because `--enable-gpl` and `--enable-nonfree` builds change the answer.

### F-58 — epub.js maintenance risk deserves a documented fallback — **LOW**

The shortlist already gates it behind a compatibility spike, which is right. Add the fallback to the spike's decision record: unzip the EPUB, render its XHTML directly in the sandboxed iframe (F-52) with our own pagination and locator mapping. More work, but no dependency on a library with uncertain maintenance, and it gives full control over the locator format that F-46 makes load-bearing.

### L.1 Phase 0 dependency posture

Phase 0 should add **none** of the media or AI dependencies. Only: FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, psycopg 3, pytest (+ hypothesis), ruff, mypy, import-linter; Next.js, React, TypeScript, Tailwind, TanStack Query. The pgvector **extension** may be installed by the first migration (it proves the database image is right and costs nothing), but **no vector column exists in Phase 0**.

---

## M. Over-engineered parts

*(Review item 13)*

The specification is, on the whole, admirably restrained — §56 and §111 already cut most of the usual suspects. What remains is over-engineering *inside* the parts that are being kept.

| # | Concept | Spec ref | Assessment | Recommendation |
|---|---|---|---|---|
| **F-59** | Five worker *services* (`ingest/`, `media/`, `extraction/`, `embeddings/`, `generation/`) | §3 | The **directory** split is good. Five deployable processes is a microservice architecture wearing a monorepo costume, and §111 forbids exactly this. | **One worker process, pluggable handlers, selected by `job_type`.** Keep the directory layout. Multiple worker processes later should differ by *resource class* (F-30), not by module. |
| **F-60** | `HardwareExecutionProfile` as a Phase 0 entity | §106 | Solving hardware-aware scheduling before a single real job has ever run. | A `hardware_signature` **string column** on the job row. Partition telemetry later, no migration needed. |
| **F-61** | 30+ entities in §106 | §106 | §106 says "avoid schema proliferation when a generic entity/version/state model can represent these" — good instinct, no cut list. | Most of `InstitutionState`, `FactionState`, `GovernanceState`, `InfrastructureAsset` are **one** `WorldEntity` + `WorldEntityState(entity_id, valid_from, valid_to, payload JSONB)` pattern. Same for `EpisodeFocusTag`/`EpisodeImportance` (tags, not tables). Phase 0 has **six** tables (§R). |
| **F-62** | `packages/ui` shared component library | §3 | A shared UI package for a monorepo with exactly one frontend app. | Defer until a second consumer exists. Components live in `apps/web` until then. |
| **F-63** | `packages/schemas` as hand-maintained shared types | §3 | Hand-syncing types across Python and TypeScript is how contract drift starts — and the audit checklist explicitly looks for "frontend/backend contract drift." | **Generate** the TS client from FastAPI's OpenAPI schema (`openapi-typescript`), with a CI check that regeneration produces no diff. Drift becomes a failing build. |
| **F-64** | The §23 power-system dimension matrix (13 dimensions + interaction rules) | §23, §105 | Very elaborate; §105 already defers power unification. | Defer hard. Phase 13+. Do not add extension points "just in case" — §105 asks only that nothing structurally prevents it. |
| **F-65** | Numeric relationship metrics (`trust: 0.92`) | §19 | The spec warns against them itself, then shows them first. | Narrative state and event deltas are primary; numeric summaries are optional, derived, and never load-bearing for continuity decisions. |
| **F-66** | ETA confidence modelling | §91.6 | Confidence intervals over a rolling throughput estimate is a research project. | `Estimating…` until N samples, then a naive rolling mean with a wide displayed range. Improve when it demonstrably annoys someone. |
| **F-67** | 15 Director UI screens | §107 | §107 already says not to build them all in the foundation. | Phase 0 web app: health/status page + Jobs list + job detail. **No placeholder screens for unbuilt features** — an empty "Visual Lab" nav item creates the impression of progress that does not exist, and invites premature backend stubs. |

---

## N. Under-designed parts

*(Review item 14)*

These are the gaps that cost the most to fix late.

### F-68 — Time is at least four independent axes, conflated across §11/§69/§97 — **BLOCKER**

§11 gives a franchise "canonical timeline." §97.1 gives a project "Story Calendar." §69 versions understanding over real-world time. §10's `CanonClaim` has a single `valid_from`/`valid_to` pair with no statement of which clock it uses. Flashbacks, meanwhile, break the assumption that story order equals chronological order — and a mystery/foreshadowing engine (§20, §21) lives entirely in the gap between the two.

**Four axes, never sharing a column, every temporal field explicitly typed as one of them:**

| Axis | Meaning | Example consumer |
|---|---|---|
| `source_time` | In-universe time within source canon | Canon claim validity, character version |
| `project_time` | In-universe time within a project branch | Story Calendar, travel feasibility, relationship pacing (§97) |
| `narrative_order` | Position in the telling (chapter/episode/scene sequence) | Reveal ordering, foreshadowing, spoiler boundary |
| `record_time` | Real-world time the system learned/recorded something | Snapshots, audit, job telemetry, backup consistency |

`narrative_order` is the one most likely to be forgotten, and it is the one the continuity validator needs most: "was this revealed to the audience before it was used?" is a `narrative_order` question that a chronological timeline cannot answer.

Also needed: in-universe time must tolerate **imprecision** ("some weeks later," "before the war"). A bare timestamp column cannot express that and will force implementers to invent fake precise dates. Recommend an interval-with-uncertainty representation (`earliest`, `latest`, `precision`, `label`) from the first temporal entity.

### F-69 — Approval gates are prose, not a model — **HIGH**

§103 lists nine operations requiring approval and says gates must be "configurable but never silently bypassed." There is no entity, no enforcement point, and no relationship to the job system — yet §91's `BLOCKED` state is obviously where an unapproved job must wait.

**Fix:** a generic `ApprovalRequest(subject_type, subject_id, gate_kind, requested_by, state, decided_by, decided_at, rationale)` plus a policy config mapping `gate_kind → required|auto`. The enforcement point is a single guard consulted by every high-impact operation, and a job needing approval sits in `BLOCKED(AWAITING_APPROVAL)` (F-24). Nothing built in Phase 0; the `BLOCKED` reason enum must include it so no migration is needed.

### F-70 — Error taxonomy and user-facing failure surfaces are unspecified — **MEDIUM**

§91.2 records "last error / error history" as free text. That makes the Production Queue a wall of stack traces and makes retry classification (F-25) impossible.

**Fix:** structured errors — `code`, `category`, `retryable`, `user_message`, `technical_detail`, `remediation` — raised as typed exceptions by handlers, not stringified at the boundary.

### F-71 — Observability primitives are named but not specified — **MEDIUM**

§109 requires "logging/observability primitives" in Phase 0; §39 describes a rich generation log for later.

**Fix for Phase 0:** structured JSON logging; a **correlation id** propagated request → job → step → provider call (without it, debugging a failed 6-hour job across three processes is archaeology); the `job_event` append-only table (§D.2); and the redaction filter (F-53). No metrics stack, no tracing backend.

### F-72 — Provenance for *inferred* and *user-defined* claims is under-specified — **MEDIUM**

§2.3 correctly distinguishes explicit / inferred / user-defined / generated / uncertain. But an inferred claim's provenance is not a locator — it is *the set of claims it was inferred from* plus the inference method. A user-defined claim has no source locator at all.

**Fix:** provenance is a **typed union**: `SourceLocator` | `Inference(from_claim_ids[], method, model_ref)` | `UserAssertion(user, timestamp, rationale)` | `Generated(recipe_id)`. Otherwise "show me why you believe this" (§93.3, §55) dead-ends the moment a claim was inferred rather than read — which will be most interesting claims.

### F-73 — "Locked" is used for several different guarantees — **MEDIUM**

`LOCKED` appears as a design status (§100.4), a canon status (§13 "locked canon facts"), a user override (§54 "Lock — user-approved rule that AI cannot silently change"), and a story anchor (§78). These are different promises: "do not regenerate," "do not contradict," "do not change without approval," "protect this outcome through ripple adaptation."

**Fix:** name them distinctly (`design_status=LOCKED`, `claim.user_locked`, `anchor`), or the continuity validator and the ripple engine will disagree about what a lock means at exactly the moment it matters.

### F-74 — Idempotency of the *scanner* specifically needs a stated key — **MEDIUM (Phase 1)**

§7.2 says "if file hash already exists, do not ingest twice." But a file that is moved, renamed, or duplicated has the same hash and a different path; a file edited in place has the same path and a different hash. Both are normal and mean different things.

**Fix:** asset identity is `content_hash`; path is an *observation* recorded in a `asset_path_observation` history. Moving a file updates an observation; it does not create an asset. Duplicating a file adds a second observation to one asset. This makes §110-style re-scan idempotency provable rather than approximate, and it is the reason F-08's `(root_key, relative_path, content_hash)` triple exists.

---

## O. Decisions that MUST be made before Phase 0 implementation

*(Review item 15)*

Each has a recommendation. Items marked ★ are the ones where the wrong choice is expensive to reverse.

| # | Decision | Recommendation |
|---|---|---|
| **D-01 ★** | Where do the data roots live? | **Outside the repository**, configured absolute paths. Repo holds only `fixtures/demo_vault/`. (F-03) |
| **D-02 ★** | Job store substrate | **PostgreSQL only.** No Redis, Celery, or Temporal. (F-05) |
| **D-03** | Database provisioning on a machine with no Docker | **Docker Desktop for the database only**; API/worker/web run natively. See **OQ-1**. |
| **D-04** | Python version | **Pin 3.12**, not the installed 3.14 — the Phase 3/4 ML stack will not have 3.14 wheels for a long time. (E-3) |
| **D-05** | Toolchain | `uv` (already installed) for Python; `pnpm` for Node (needs install). |
| **D-06 ★** | ORM layer | **SQLAlchemy 2.0 ORM + separate Pydantic v2 schemas.** Not SQLModel: it fuses persistence and API contracts, and the database schema is the longest-lived asset in this product — it should not be shaped by API convenience. |
| **D-07 ★** | Primary key strategy | **UUIDv7** — time-ordered (index locality), globally unique (safe for export/import/merge across machines per §108), no sequence collisions when merging two machines' data. |
| **D-08 ★** | Is `franchise.yaml` app-writable? | **No. Never.** Read-only input; app metadata lives in the database. (F-02) |
| **D-09** | Timestamps | `timestamptz`, UTC, **database clock** (`now()`) for all lease/scheduling logic. (F-27) |
| **D-10 ★** | API↔web contract | **Generate** the TypeScript client from OpenAPI; CI fails on drift. (F-63) |
| **D-11 ★** | Graceful worker stop mechanism | Signals **and** a database-visible `drain_requested` flag; the flag is the portable path. (F-31) |
| **D-12** | Does Phase 0 ship any real AI SDK? | **No.** Fakes only. (F-38) |
| **D-13 ★** | Vault write escape hatch | **None exists.** No flag, no force, no admin endpoint. (F-15) |
| **D-14 ★** | Source locator format | Content-derived, `<medium>:sha256:<hash>#<unit>`. Decide now, implement Phase 1/2. (F-46) |
| **D-15 ★** | Derived/artifact storage convention | Content-addressed `<root>/<hh>/<hash>`, temp+fsync+atomic rename. (F-40, F-22) |
| **D-16** | API bind address and auth | `127.0.0.1` only; non-loopback binding requires auth, enforced by the config validator at boot. (F-50) |
| **D-17** | GPL policy | No code, fragments, or ports from GPL sources. Architecture and UX inspiration only. (F-56) |
| **D-18** | Fixture location and content | `fixtures/demo_vault/`, wholly synthetic, no real franchise strings anywhere in the repo. (F-10) |
| **D-19** | Repo and data location | Move off OneDrive to a local non-synced path; fix the `Continnum` → `Continuum` spelling at the same time. (E-6, E-7) |
| **D-20** | Line endings | `.gitattributes` with `* text=auto eol=lf` **before** any code lands. (E-8) |

---

## P. Features that must explicitly stay deferred

*(Review item 16)*

§111's list stands in full. Adding the items this review surfaced, **none of the following may appear in Phase 0**:

**Deferred by §111 (unchanged):** franchise-specific schemas or logic; real copyrighted fixtures; source downloading or scraping; DRM bypass; a single source-trained LLM; exact third-party voice cloning; full episode generation; final power unification; graph-database migration; autonomous canon changes; hardcoded city/governance/crossover premises; microservices; any cloud requirement for core library use.

**Additionally deferred (this review):**

| Deferred | First appears | Note |
|---|---|---|
| Any media reader (CBZ, PDF, EPUB, video) | Phase 2 | Phase 0 has no file parsing at all |
| Real file scanning / hashing / classification | Phase 1 | Phase 0's only jobs are synthetic |
| Source segments, locators as **code** | Phase 1/2 | The **format** is decided now (D-14) |
| Embeddings, vector columns, retrieval | Phase 3 | pgvector extension may be installed; no vector column |
| Canon entities (Character, Event, Claim, Relationship…) | Phase 3/5 | None in Phase 0 |
| Character Brain, Craft Vault | Phase 5 | Split design decided now (F-17) |
| Project, Branch, Story Bible, Calendar | Phase 6/7 | |
| Change Graph, continuity validator | Phase 8 | Rebuildability rule decided now (F-19) |
| Canon sync, ripple, retcon | Phase 9 | |
| Visual Lab, artifacts, recipes as **tables** | Phase 10 | Storage convention + intent/execution split decided now (D-15, F-39) |
| Approval gate engine | Phase 6+ | `BLOCKED(AWAITING_APPROVAL)` reserved in the enum now |
| `HardwareExecutionProfile` entity | Phase 12+ | String column now |
| Redis, S3, object storage, Neo4j, Temporal, Kubernetes | Not planned | |
| Authentication, multi-user, collaboration | Not planned | Loopback binding instead (D-16) |
| Desktop wrapper (Electron/Tauri) | Phase 11+ | Its constraint is written into ADR-0002 now (§E.1) |
| Placeholder UI screens for unbuilt features | Never | (F-67) |

---

## Q. Proposed exact Phase 0 monorepo tree

Data roots are **not** in this tree — they are configured paths elsewhere on disk (D-01).

```text
continuum/                                  # the git repository
├── apps/
│   ├── api/                                # FastAPI application
│   │   ├── src/continuum_api/
│   │   │   ├── main.py                     # app factory, lifespan, loopback bind
│   │   │   ├── config.py                   # settings, validation, SecretStr
│   │   │   ├── deps.py
│   │   │   └── routers/
│   │   │       ├── health.py               # /health, /ready  (§110.2)
│   │   │       ├── jobs.py                 # list/get/enqueue/pause/cancel/retry
│   │   │       └── workers.py              # list, drain  (F-31)
│   │   └── tests/
│   │
│   └── web/                                # Next.js shell
│       ├── app/
│       │   ├── page.tsx                    # system status: API health, roots, workers
│       │   └── jobs/                       # job list + job detail (the only real screen)
│       ├── lib/api/generated/              # OpenAPI-generated client — never hand-edited
│       └── tests/
│
├── packages/
│   ├── core/                               # domain primitives; no I/O, no framework
│   │   ├── ids.py                          # UUIDv7  (D-07)
│   │   ├── time.py                         # tz-aware helpers; the four axes are typed here
│   │   ├── errors.py                       # structured error taxonomy  (F-70)
│   │   └── hashing.py                      # sha256 helpers, content addressing  (D-15)
│   │
│   ├── storage/                            # THE ONLY module permitted filesystem access
│   │   ├── roots.py                        # the 8 roots from §108, resolved from config
│   │   ├── paths.py                        # resolve_within(): normalize, realpath, contain, fd re-verify
│   │   ├── vault.py                        # SourceVaultReader — NO write API exists  (§B.1)
│   │   ├── derived.py                      # DerivedStore — content-addressed writes only
│   │   ├── probe.py                        # OS read-only capability probe + sync-folder detection
│   │   └── tests/                          # traversal, symlink, junction, ADS, 8.3, UNC, device names
│   │
│   ├── db/
│   │   ├── models/                         # SQLAlchemy 2.0 ORM — 6 tables (§R)
│   │   ├── session.py
│   │   ├── tiers.py                         # tier classification + the FK-direction CI test (§C.1)
│   │   └── migrations/                     # Alembic; single head enforced
│   │
│   ├── jobs/
│   │   ├── states.py                       # states + the guarded transition table  (F-28)
│   │   ├── queue.py                        # claim (FOR UPDATE SKIP LOCKED), enqueue+dedupe  (F-26)
│   │   ├── lease.py                        # heartbeat + reaper  (F-27)
│   │   ├── checkpoint.py                   # unit table + optional ordinal cursor  (F-29)
│   │   ├── registry.py                     # job_type -> handler
│   │   └── tests/
│   │
│   ├── providers/
│   │   ├── contracts.py                    # capabilities, descriptors, DataClass  (§G.2)
│   │   ├── registry.py                     # THE ONLY place a model identifier may appear
│   │   ├── policy.py                       # profile + data class -> permitted provider | BLOCKED
│   │   ├── fakes/                          # echo text, deterministic embedding, null image
│   │   └── tests/
│   │
│   └── observability/
│       ├── logging.py                      # structured JSON, correlation ids
│       └── redaction.py                    # pattern + value-registry redaction  (F-53)
│
├── workers/
│   └── runner/
│       ├── main.py                         # standalone process; signal + drain-flag shutdown
│       └── handlers/
│           └── synthetic.py                # the only handlers in Phase 0 (§R.2)
│
├── fixtures/
│   └── demo_vault/                         # tiny, wholly synthetic, read-only  (D-18)
│
├── tests/                                  # cross-cutting acceptance tests (§S)
│   ├── acceptance/                         # one test per §110 item, named for it
│   └── conftest.py
│
├── docs/
│   ├── ARCHITECTURE_REVIEW.md
│   ├── ADR/0001..0006-*.md
│   ├── DEPENDENCIES.md                     # code deps + a Model Assets section  (F-55)
│   └── PHASE_0_REPORT.md
│
├── scripts/
│   ├── dev.ps1 / dev.sh                    # start db, api, worker, web
│   └── harden_vault.ps1 / .sh              # optional OS-level read-only  (§B.5)
│
├── docker/
│   └── postgres/                           # pgvector-enabled image
│
├── .github/workflows/ci.yml                # lint, typecheck, import-linter, tests, contract drift
├── AGENTS.md
├── README.md
├── .env.example                            # no real values
├── .gitattributes                          # * text=auto eol=lf  (D-20)
├── .gitignore
├── docker-compose.yml                      # database only
├── pyproject.toml                          # uv workspace
└── package.json                            # pnpm workspace
```

**Deliberately absent, versus §3's tree:** `packages/prompts` (no prompts exist — nothing generates), `packages/schemas` (replaced by OpenAPI generation, F-63), `packages/ui` (one frontend app, F-62), and the five worker service directories (one worker, F-59). `source-vault/`, `library/`, `projects/`, `cache/` are absent by design (F-03).

---

## R. Exact database entities needed in Phase 0 — and only these

### R.1 Six tables

| Table | Purpose | Key columns |
|---|---|---|
| `job` | The durable unit of work | `id` (uuidv7), `job_type`, `status`, `blocked_reason`, `priority`, `resource_class`, `dedupe_key`, `input_hash`, `recipe_version`, `provider_ref`, `units_done`, `units_total`, `current_step`, `total_steps`, `attempt`, `max_attempts`, `run_after`, `pause_requested`, `cancel_requested`, `lease_owner`, `lease_expires_at`, `elapsed_active_ms`, `hardware_signature`, `last_error` (structured JSONB), `created_at`, `started_at`, `updated_at`, `completed_at` |
| `job_step` | One durable, idempotent unit | `id`, `job_id`, `unit_key` (**unique with `job_id`**), `ordinal` (nullable), `status`, `attempt`, `last_error`, `started_at`, `completed_at` |
| `job_checkpoint` | Resumable position/payload | `id`, `job_id`, `seq`, `payload` (JSONB) or `locator`, `created_at` |
| `job_dependency` | DAG edges | `job_id`, `depends_on_job_id`, `kind` — cycle check at insert |
| `job_event` | Append-only audit of everything | `id`, `job_id`, `event_type`, `from_status`, `to_status`, `detail` (JSONB), `worker_id`, `correlation_id`, `created_at` |
| `worker` | Liveness + the portable drain channel (F-31) | `id`, `hostname`, `pid`, `resource_classes`, `started_at`, `last_heartbeat_at`, `drain_requested`, `stopped_at` |

Plus Alembic's own `alembic_version`. Nothing else. **No** franchise, asset, segment, character, project, branch, artifact, or provider table exists in Phase 0.

The pgvector extension is created by the first migration; no column uses it yet.

### R.2 The two synthetic job handlers

Neither touches real media; both exist purely to prove the invariants:

1. **`synthetic.counted_work`** — N units, each sleeping briefly and writing a content-addressed marker file into `/cache`. Supports env-driven fault injection: `die_at_unit` (hard kill mid-unit), `fail_at_unit` (retryable error), `fail_permanently_at_unit`. This one job proves §110.6–110.11.
2. **`synthetic.blocked_capability`** — requests a provider capability nothing satisfies, to prove `BLOCKED(MISSING_PROVIDER)` and the remediation payload (§110.12, F-24, F-34).

The first handler is where F-22 gets tested for real: kill the process mid-unit, restart, and assert both that completed units did not re-run **and** that the interrupted unit's re-run produced a byte-identical result with no duplicate row.

---

## S. Acceptance-test matrix — Master Plan §110

Every item maps to an automated test unless marked otherwise. `PHASE_0_REPORT.md` must reproduce this table with PASS/FAIL and the exact command.

| §110 | Requirement | Test | Mechanism |
|---|---|---|---|
| 1 | Clean clone/install/migrations/boot | `tests/acceptance/test_110_01_clean_boot.py` + CI job on a clean runner | CI provisions from scratch; asserts the documented commands in `README.md` succeed verbatim. Blocked by **OQ-1**. |
| 2 | Web can call API health | `apps/web/tests/health.spec.ts` + `test_110_02_health.py` | API returns `/health` and `/ready`; web renders live status. |
| 3 | Vault path resolved/normalized safely | `packages/storage/tests/test_resolve.py` | Table-driven over the §B.2 Windows cases + Hypothesis fuzzing. |
| 4 | Traversal and symlink escape rejected | `test_110_04_traversal.py` | `../`, absolute, UNC, `\\?\`, 8.3, ADS, trailing dot/space, device names, junction→outside, symlink→outside, symlink swapped **after** validation (TOCTOU). |
| 5 | App cannot write/delete/rename vault files | `test_110_05_vault_readonly.py` + `test_import_boundaries.py` | (a) `SourceVaultReader` has no write member (introspection assert); (b) `DerivedStore` rejects any vault-resolving root; (c) import-linter proves no module outside `packages/storage` performs filesystem I/O; (d) OS probe result reported on `/health` (informational). |
| 6 | Synthetic durable job queued and processed | `test_110_06_job_roundtrip.py` | Enqueue → worker claims → `SUCCEEDED`; `job_event` shows the full transition chain. |
| 7 | Progress persisted independently of the web page | `test_110_07_progress_persist.py` | Progress advances with **no** API process running at all — the strongest form of the claim. |
| 8 | Closing/restarting the UI does not cancel the job | `test_110_08_ui_restart.py` | Kill and restart web **and** API mid-job; assert `RUNNING` throughout and correct completion. |
| 9 | Graceful worker stop leaves the job resumable | `test_110_09_graceful_stop.py` | Set `drain_requested`; assert last checkpoint durable, status `PAUSED`/`QUEUED`, no partial effect visible. Run on both the signal path and the flag path. |
| 10 | Restart resumes only unfinished units | `test_110_10_resume.py` | Hard-kill at unit K. Assert units < K do **not** re-execute (handler-side execution counter), and that a **forced** re-execution of a completed unit is a byte-identical no-op (F-22). |
| 11 | Failed job records structured error/retry state | `test_110_11_failure_state.py` | `fail_at_unit` → `FAILED_RETRYABLE` with `run_after` backoff, `attempt` increments, structured `last_error` + `error_history`; then `fail_permanently_at_unit` → `FAILED_FINAL` with no further retry. Plus lease-expiry recovery of a hard-killed worker (F-27). |
| 12 | Providers work with fakes; no cloud credentials | `test_110_12_providers.py` + dependency inventory | Full suite passes with **no network access** and an empty `.env`; assert `FREE_LOCAL` never resolves to a `PAID`/`REMOTE` provider; assert no AI SDK is installed (F-38). |
| 13 | Logs do not expose secrets | `test_110_13_redaction.py` | Load config with sentinel secrets, dump effective config + trigger an exception at DEBUG, assert no sentinel appears in any handler's output. |
| 14 | Migration strategy documented; clean migration tested | `test_110_14_migrations.py` + ADR-0003 | Clean DB → `upgrade head`; `upgrade head` → `downgrade base` → `upgrade head`; assert exactly one Alembic head. |
| 15 | Required documents exist before tagging | `test_110_15_docs_present.py` | Assert presence and non-emptiness of `DEPENDENCIES.md`, `ARCHITECTURE_REVIEW.md`, `ADR/0001–0006`, `PHASE_0_REPORT.md`, `AGENTS.md`. |

### S.1 Additional invariant tests this review recommends adding

Not in §110, but each is cheap and guards a BLOCKER finding:

| Test | Guards |
|---|---|
| `test_fk_tier_direction.py` — reflect metadata, assert no FK points from Tier A/B to Tier C/D | F-17, §C.1 — the single best structural guarantee that canon and project state stay separate |
| `test_no_franchise_strings.py` — grep source, fixtures, migrations for a denylist | F-10, §111 |
| `test_no_model_literals.py` — model identifiers only inside `providers/registry` and config | §90, F-37 |
| `test_openapi_client_current.py` — regenerate the TS client, assert no diff | F-63, contract drift |
| `test_transition_table.py` — assert illegal transitions raise | F-28 |
| `test_dedupe_enqueue.py` — double enqueue yields one job | F-26 |
| `test_sync_folder_warning.py` — a root under a sync provider produces a warning | F-13, E-6 |

---

## T. Open questions that genuinely block implementation

Six. Everything else in this review has a recommendation an implementer can act on unilaterally.

### OQ-1 — How is PostgreSQL + pgvector provisioned on this machine? **(blocks §110.1)**

Docker is not installed (E-1). §110.1 requires "clean clone/install/migrations/boot succeeds using documented commands," and those commands cannot be written until this is settled.

- **(a) Install Docker Desktop; Compose runs the database only** — *recommended*. pgvector is genuinely unpleasant to build natively on Windows; API/worker/web still run natively for fast iteration and easy debugging.
- (b) Native PostgreSQL + build pgvector from source on Windows — no Docker dependency, but a fragile setup step that will need repeating on every machine.
- (c) Everything in Compose — most reproducible, slowest inner loop, and awkward for debugging on Windows.
- (d) SQLite for Phase 0, PostgreSQL later — **not recommended**: `FOR UPDATE SKIP LOCKED` does not exist in SQLite, so the job queue would be built on a different concurrency model than the one it ships with, and §110.6–110.11 would be testing the wrong thing.

### OQ-2 — Confirm the repository and data roots move off OneDrive. **(blocks D-01, D-19)**

See E-6. This determines the paths that go into `.env.example`, the README, and every developer instruction. It also needs a decision on whether the `Continnum` spelling is corrected now (E-7) — cheap today, annoying once a remote and clones exist.

### OQ-3 — Where will the source vault physically live, and how large will it get?

The answer changes real decisions: whether thumbnails and proxies need a size budget, whether hashing needs incremental/partial strategies for multi-gigabyte video, and whether the vault will be on removable or network storage (which makes the `OFFLINE` asset state of F-33 a routine condition rather than an edge case).

### OQ-4 — Is the *primary* near-term goal the Library/Reader, or the Story Studio?

Both are in the plan and the order is fixed by §109. But it changes emphasis inside Phase 0: if reading a personal library is the near-term goal, Phase 1–2 want more polish and the job system can stay minimal; if the story engine is the goal, Phase 0's provenance and locator groundwork (F-46, F-72) deserves more care because Phase 3+ leans on it immediately. **Not a re-ordering question — an emphasis question.**

### OQ-5 — Confirm: no vault escape hatch, ever? **(D-13)**

This review recommends no override of any kind. Confirming it now prevents the request arriving later as "just for this one cleanup task," at which point the guarantee is negotiable. If the user *does* want vault-write capability, the design should change now — bolting it on later is how the invariant dies.

### OQ-6 — Will Codex have the same environment for the Phase 0 audit?

Handoff §4 has Codex independently re-run the Phase 0 tests. If Codex runs in a container with Linux paths, the Windows-specific path tests (§B.2) — which are the highest-value tests in Phase 0 — will be skipped rather than failed, and the audit will report PASS on the platform that matters least. Worth knowing before the tests are written, so they can be marked `xfail`-on-wrong-platform rather than silently skipped.

---

## U. Finding index

| ID | Severity | Title |
|---|---|---|
| F-01 | BLOCKER | Three incompatible phase-numbering schemes |
| F-02 | BLOCKER | `franchise.yaml` inside the vault contradicts immutability |
| F-03 | BLOCKER | Data roots shown inside the repository tree |
| F-04 | HIGH | Storage root list differs in three places |
| F-05 | HIGH | Redis offered as a job substrate |
| F-06 | HIGH | Provider config example hardcodes cloud vendors |
| F-07 | MEDIUM | Cost tiers read as a cloud escalation ladder |
| F-08 | HIGH | `SourceAsset.path` is a bare path column |
| F-09 | MEDIUM | §44's "MVP" now spans eight v0.3 phases |
| F-10 | LOW | Real franchise names as examples (hard rule attached) |
| F-11 | MEDIUM | §2.5 provider sketch predates v0.3 requirements |
| F-12 | MEDIUM | Delta-only branching cost not stated |
| F-13 | HIGH | Cloud-sync folders unsafe for vault, database, repo |
| F-14 | MEDIUM | Spoiler boundary spans phases with no stated hook |
| F-15 | BLOCKER | No vault escape hatch should exist |
| F-16 | HIGH | Vault identity cannot be a marker file |
| F-17 | BLOCKER | `CharacterBrain` must be two entities |
| F-18 | BLOCKER | `SourceCanonSnapshot` has two incompatible meanings |
| F-19 | HIGH | Change Graph must be rebuildable, never authoritative |
| F-20 | HIGH | Deletion and retention semantics undefined |
| F-21 | MEDIUM | Optimistic concurrency needed on project state |
| F-22 | BLOCKER | Effect idempotency, not checkpoint frequency |
| F-23 | HIGH | Missing `CANCELLING` state |
| F-24 | HIGH | `BLOCKED` conflates four situations |
| F-25 | HIGH | No `run_after`; retry has no scheduling semantics |
| F-26 | HIGH | No job-level idempotency key |
| F-27 | BLOCKER | No lease/heartbeat; crashed worker's job stuck forever |
| F-28 | HIGH | Pause/cancel races need request flags |
| F-29 | MEDIUM | Two checkpoint patterns needed, one mechanism |
| F-30 | MEDIUM | No resource-concurrency model |
| F-31 | HIGH | Graceful shutdown needs a Windows-viable channel |
| F-32 | BLOCKER | Docker absent; "one command starts the app" undefined |
| F-33 | HIGH | Missing source assets must degrade, not delete |
| F-34 | MEDIUM | Missing model blocks; recipe survives |
| F-35 | HIGH | Migration downgrade policy unstated |
| F-36 | HIGH | Backup consistency between DB and filesystem unspecified |
| F-37 | HIGH | Every provider call must declare a data class |
| F-38 | MEDIUM | Phase 0 should ship zero AI SDKs |
| F-39 | HIGH | Recipe must split intent from execution |
| F-40 | HIGH | Content-addressed artifact storage settled in Phase 0 |
| F-41 | MEDIUM | Lineage marks stale; never auto-delete or regenerate |
| F-42 | MEDIUM | Recipes need a schema version |
| F-43 | MEDIUM | Four-way separation of visual concepts |
| F-44 | MEDIUM | Outfit scope conflicts have no resolution rule |
| F-45 | MEDIUM | Moodboard refs need intended-use and rights flags |
| F-46 | BLOCKER | Stable source locators undefined |
| F-47 | HIGH | Embeddings must not be a column on the segment |
| F-48 | MEDIUM | Retrieval eval harness before any fine-tuning |
| F-49 | HIGH | Corrections must key on locator + claim identity |
| F-50 | BLOCKER | API must bind loopback; never take a path parameter |
| F-51 | HIGH | Archive and media parsing are untrusted-input surfaces |
| F-52 | HIGH | EPUB rendering is remote content and script execution |
| F-53 | MEDIUM | Secret redaction needs a value registry |
| F-54 | MEDIUM | Privacy classification per-franchise, enforced per-call |
| F-55 | HIGH | Model weight licenses not covered anywhere |
| F-56 | MEDIUM | Jellyfin GPL rule needs to be explicit |
| F-57 | MEDIUM | FFmpeg licensing depends on build and distributor |
| F-58 | LOW | epub.js maintenance risk needs a documented fallback |
| F-59 | MEDIUM | Five worker services should be one worker process |
| F-60 | MEDIUM | `HardwareExecutionProfile` premature as an entity |
| F-61 | MEDIUM | 30+ entities in §106 need a cut list |
| F-62 | LOW | `packages/ui` premature with one frontend |
| F-63 | HIGH | Hand-maintained shared types invite contract drift |
| F-64 | LOW | Power-system dimension matrix defer hard |
| F-65 | LOW | Numeric relationship metrics must not be load-bearing |
| F-66 | LOW | ETA confidence modelling over-engineered |
| F-67 | MEDIUM | No placeholder UI screens for unbuilt features |
| F-68 | BLOCKER | Time is four axes, conflated across §11/§69/§97 |
| F-69 | HIGH | Approval gates are prose, not a model |
| F-70 | MEDIUM | Error taxonomy unspecified |
| F-71 | MEDIUM | Observability primitives named but not specified |
| F-72 | MEDIUM | Provenance for inferred/user-defined claims under-specified |
| F-73 | MEDIUM | "Locked" means four different guarantees |
| F-74 | MEDIUM | Scanner idempotency key needs stating |

**BLOCKERs (12):** F-01, F-02, F-03, F-15, F-17, F-18, F-22, F-27, F-32, F-46, F-50, F-68.

---

## V. Recommended next step

1. Human review of this document and the six ADRs (handoff §2 and §13 gate).
2. Answer **OQ-1** through **OQ-6**.
3. Confirm or amend **D-01** through **D-20**.
4. Commit the ADRs (`docs: approve Continuum foundation architecture`).
5. Only then begin Phase 0, scoped exactly to §Q, §R, and §S.

**STOP BEFORE IMPLEMENTATION.** No implementation code has been written.
