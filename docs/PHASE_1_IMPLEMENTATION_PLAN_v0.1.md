# Continuum — Phase 1 Implementation Plan v0.1

**Status:** PROPOSED — awaiting review before the large implementation pass
**Date:** 2026-09-13
**Baseline:** `master` = `continuum-phase-0` = `91025d7a7600ade2959422bf7f0a6d4499a8beb8`
**Branch:** `phase-1/integrated-candidate`
**Authorities:**
- `docs/CONTINUUM_PHASE_1_REFERENCE_VAULTS_v0.1.md` (approved direction)
- `docs/creative/THE_ARRIVALS_S1E1_MANGA_PANEL_SCRIPT_v0.1.md` (approved panel script)
- ADR-0001 through ADR-0005
- the Phase 1 kickoff brief

The goal is one durable path, proven small:

`Source/Reference Vault → reference catalog → character + style reference selection → project/scene/panel context → rough manga attempt → review → regenerate / approve`

---

## 1. What exists today (and is reused, not rewritten)

| Area | Current code | Phase 1 use |
|---|---|---|
| Source Vault access | `continuum_storage.vault.SourceVaultReader` (read-only, `resolve_within` containment) | the only way a reference reaches source bytes |
| Held-media ids | `continuum_storage.media` — opaque `m1_` ids resolved through the engine's `vault-index.json`; archive pages by position | *transport* ids for the reader and the "add as reference" action; **never stored as a reference identity** |
| Writable storage | `DerivedStore` — content-addressed temp → fsync → atomic rename, roots `library/ projects/ generated/ cache/ …` | user-added references (`library`), rough artifacts (`generated`), thumbnails (`cache`) |
| Projects | `continuum_storage.projects` — file manifests (`continuum.project.json`), string project ids, explicit lifecycle | project identity and panel-script documents; DB rows refer to projects by manifest id |
| Durable jobs | `continuum_jobs` — leases, heartbeat, reaper, checkpoints, locked ownership proof (H-1/H-2/H-3) | the generation job boundary |
| Providers | `continuum_providers` — `Capability.IMAGE_GENERATE`, `DataClass`, `ProviderPolicy` (FREE_LOCAL), `NullImageProvider`, no model literals | image providers plug in here; nothing couples to ComfyUI |
| Database | PostgreSQL + Alembic `0001_phase0`; **exactly six job tables**, asserted by `test_110_14_migrations.py` | Phase 1 adds its tables through a new migration and evolves that assertion deliberately (§4.1) |
| API / web | FastAPI routers (id-only, F-50 surface test), Next.js studio shell, reader, Projects workspace | new routers and surfaces follow the same rules |

---

## 2. Scope reconciliation (needs an explicit decision)

The approved Reference Vault document says Phase 1 *"does not need to understand the artistic meaning of every image"* and places generation in later phases. The Production Tooling direction assigns ComfyUI to Phases 10–12, and §109 orders the phases the same way.

This kickoff asks Phase 1 to prove a **small rough-manga vertical slice**. The plan therefore separates:

- **Phase 1 core:** the reference catalog, provenance, character/outfit/style organization, and the artifact/attempt/review foundation. This is durable infrastructure that later phases need anyway.
- **Pull-forward slice (explicitly authorized, recorded like gate #7):** a thin generation path behind the provider contract, proven on three panels, not a production pipeline.

---

## 3. Data model

### 3.1 Concepts kept separate

| Concept | Is | Is not |
|---|---|---|
| **Library asset** | bytes Continuum can address: held source media or a user-added image | a catalog decision |
| **Reference item** | a catalogued use of a specific asset *unit* (an archive page, an image, later a video frame) | the asset itself |
| **Character** | a user-level identity (generic id + display name) | an outfit, a style, a project |
| **Outfit** | wardrobe variant belonging to a character | identity |
| **Visual mode** | a named style/technique language | tied to any character |
| **Project selection** | a project's standing for a reference (canonical-for-project / useful) | a change to the library |
| **Artifact / version** | a generated rough output and its immutable attempts | source |

"Character X implies style Y" is not representable: character↔reference and visual-mode↔reference are separate link tables, and nothing links a character to a visual mode.

### 3.2 Tables (migration `0002_phase1_reference_vault`), by ADR-0003 tier (FKs point only downward, D → C → B → A)

**Tier A — observed**
- `library_asset`:
  - `id` (UUIDv7), `content_hash` (unique), `medium` (image | archive | video | pdf), `byte_size`;
  - `origin` (SOURCE_VAULT | USER_ADDED | GENERATED_APPROVED);
  - `created_at`, `removed_at` (soft delete).
- `library_asset_observation`:
  - `asset_id`, `root_key` (`source_vault` | `library`), `relative_path` (validated relative, never absolute), `observed_at`;
  - the path is an observation, never identity (ADR-0001).

**Tier B — the user's catalog (interpretation of held material)**
- `reference_item`:
  - `id`, `asset_id`, `locator` (ADR-0005 string, §3.3);
  - `reference_class` (CANON | TECHNIQUE | CONTINUITY | MOOD);
  - `provenance_kind` (SOURCE | OFFICIAL_ART | FAN_ART | USER_CREATED | GENERATED | PROJECT_APPROVED), `provenance` (typed union, JSONB);
  - `notes`, `favorite`, `row_version`, timestamps, `removed_at`.
- `character`: `id`, `display_name`, `source_label` (free text; no franchise enum), `notes`, `row_version`.
- `outfit`: `id`, `character_id`, `name`, `era`, `notes`.
- `visual_mode`: `id`, `name`, `description`.
- `reference_character`:
  - `reference_id`, `character_id`, `outfit_id?`;
  - `aspect` (IDENTITY | FACE | HAIR | BODY | EXPRESSION | POSE | OUTFIT | ACCESSORY | MARK), `preferred`.
- `reference_visual_mode`: `reference_id`, `visual_mode_id`.
- `reference_facet`:
  - `reference_id`, `facet`, `value`, `origin` (USER | ANALYSIS), `confidence?`;
  - facets: era, season_weather, condition, expression, pose, shot_type, camera_angle, scene_type, action_intensity, dialogue_density, background_complexity, composition, page_turn_function.
  - Manual first. Later Source Intelligence writes rows with `origin = ANALYSIS` into the same table; nothing pretends analysis exists before it does.

**Tier C — project continuity**
- `project_reference_selection`:
  - `project_key` (manifest id), `reference_id`, `character_id?`;
  - `standing` (CANONICAL_FOR_PROJECT | USEFUL), `notes`, `row_version`.

**Tier D — generated** (M2)
- `generation_recipe`:
  - `intent` (JSONB: project/episode/scene/page/panel address, panel-script document id and version, reference locators by role, visual mode);
  - `execution` (JSONB: provider id and version, workflow id and version, model refs, seed, settings);
  - `intent_hash`, `execution_hash`, `recipe_schema_version`, `template_package_version` (ADR-0005 §3, §6).
- `artifact`: `id`, `project_key`, `kind` (ROUGH_PANEL | ROUGH_PAGE), `subject` (panel/page address).
- `artifact_version`:
  - `id`, `artifact_id`, `attempt` (unique per artifact, append-only);
  - `content_hash` (under `generated/`), `recipe_id`, `job_id?`;
  - `state` (PENDING | GENERATED | APPROVED | REJECTED | FAILED), `created_at`.
- `artifact_review`: `artifact_version_id`, `decision` (APPROVE | REJECT | REGENERATE), `notes`, `decided_at`.
- `artifact_lineage`: `artifact_version_id`, `input` (locator or version ref), `role`.

A **continuity reference** to an approved artifact is a `reference_item` whose locator is `gen:sha256:<hash>`, with provenance `Generated(recipe_id)`. It is **not** an FK from Tier B/C up to Tier D, so the tier rule holds.

### 3.3 Locators (ADR-0005 §1, first implementation)

`continuum_core.locators`: pure `render` / `parse`, one grammar per medium:

```
image:sha256:<hash>
zip:sha256:<hash>#entry=<archive-entry-path>
pdf:sha256:<hash>#page=<n>
video:sha256:<hash>#t=<hh:mm:ss.mmm>
gen:sha256:<hash>
```

- Archive units use the **entry path**, not the page index: the index is a display order that can change with sorting rules; the entry name is a property of the bytes.
- A locator is content-derived, so re-scans, restores and folder moves never repoint a reference.
- Hashing source files is read-only. Files the engine has not hashed are hashed on demand, or by a durable job for bulk.

### 3.4 Storage boundary

- Source Vault: read only, through `SourceVaultReader`; references to held media store **no copy**.
- User-added references: content-addressed under `library/`.
- Rough attempts: content-addressed under `generated/` (ADR-0005 §4); the database holds identity, attempt number and state.
- Thumbnails: `cache/`, disposable.
- Git: panel scripts, manifests, workflow/recipe *templates*, and approved direction only. **Not** the reference catalog, not recipes naming personal media, not artifacts (open question 2).

---

## 4. Changes by layer

### 4.1 Schema and invariants
- Alembic `0002`, with upgrade/downgrade round trip.
- Replace "exactly six tables" with a **phase-declared table registry**: each table carries its phase and tier. Tests assert:
  - the metadata matches the registry;
  - no forbidden Phase 2+ tables exist (canon, branch, segment, embedding);
  - **FK direction D → C → B → A** (ADR-0003 §2).

### 4.2 Storage
- `continuum_storage.references`: create a reference from a media id plus unit, or from an uploaded image. It resolves to `library_asset` + locator, hashes read-only, and validates archive entry names against the archive listing, never against client strings.
- Upload intake: size and type limits and magic-byte checks; bytes land in `library/` through `DerivedStore`. Image **decoding** waits for the image-library decision (open question 5).

### 4.3 API (id-only; the F-50 surface test extends automatically)
- `GET/POST /library/references`, `GET/PATCH/DELETE /library/references/{id}` (delete = soft; never touches the asset).
- `GET/POST /library/characters`, `…/{id}`, `…/{id}/outfits`; `GET/POST /library/visual-modes`.
- `GET/PUT /projects/{project_id}/reference-selections`.
- M2:
  - `GET /projects/{project_id}/artifacts`, `GET /artifacts/{id}`;
  - `POST /artifacts/{id}/attempts` (enqueues a job), `POST /artifact-versions/{id}/review`;
  - `GET /artifact-versions/{id}/content`.

### 4.4 Web
- Library → **Characters** (Character Vault): references grouped by aspect, outfit, expression, pose and era; preferred identity; provenance; project standing.
- Library → **Styles** (Style / Technique Vault): named visual modes and their references.
- Reader → **Add as reference**: pick character/aspect/outfit or visual mode, class, facets, notes.
- Project → Manga (M2): per page/panel attempts, side-by-side versions, provenance (references, recipe, seed, workflow), Approve / Reject / Regenerate.

### 4.5 Jobs (M2)
- Job type `visual.rough_attempt`. Units are the requested panels.
- `execute_unit` resolves references read-only, calls the image provider with `DataClass.SOURCE_EXCERPT` (policy: local only), and lands bytes content-addressed.
- `artifact_version` and the recipe are written **inside the ownership-guarded completion transaction**.
- A missing provider or model → `BLOCKED(MISSING_PROVIDER | MISSING_MODEL)` with remediation; the recipe survives (ADR-0004 §7).

### 4.6 Providers
- Extend the image request with typed fields: prompt package, reference inputs by role (resolved handles, not paths), seed, size, workflow ref and version. Keep `GenerationRequest` backward compatible.
- `DeterministicSketchProvider` (fake): renders a deterministic placeholder image from the request. It serves tests and offline mode, and lets M2 run end to end with no GPU.
- M3: `ComfyUIImageProvider`, a `LOCAL` adapter over HTTP to a user-run ComfyUI on loopback.
  - Versioned workflow templates live in the repo; model refs live only in `/config`; nothing in Continuum imports ComfyUI.
  - Model-weight licenses go into `docs/DEPENDENCIES.md` **before** any download.
  - No installation happens until the contract and slice requirements are approved.

---

## 5. Acceptance tests

### 5.1 Phase 1 safety (required by the kickoff)

| Requirement | Test |
|---|---|
| Source Vault stays read-only | reference create/browse/delete over a demo-vault copy leaves it byte-identical; a storage AST invariant stays green |
| Reference records cannot cause traversal | hostile media ids, entry names, upload names and locators (`..`, absolute, UNC, drive, `file:`, symlink/junction) refused; nothing stored |
| Artifacts cannot escape their root | artifact content resolves only under `generated/` via content hash; forged hashes refused |
| Character / outfit / style are separate | schema test: no FK or column links character↔visual_mode; outfit requires a character; a reference can carry identity and technique roles independently |
| Provenance roundtrip | create → read → export → re-import preserves locator, provenance union, facets, links; `parse(render(x)) == x` per medium; re-hash stability |
| Attempts append-only | regenerate creates attempt n+1; prior bytes, recipe and review unchanged; unique `(artifact_id, attempt)` |
| No project hardcode | franchise-string invariant extended to new modules; tests use invented projects and characters |
| Offline boot | API + worker boot with empty env and no provider; reference browsing works with no credentials |
| Recoverable generation job | worker killed mid-attempt → reaped → second worker completes; exactly one `artifact_version` per completed unit; ownership-guard tests stay green |

### 5.2 Vertical-slice acceptance (fixtures in CI; the live project run is manual)
1. Create a character, an outfit and a visual mode (invented names).
2. Add three references from a synthetic demo archive: CANON identity (face), TECHNIQUE (composition), MOOD (night).
3. Select them for a project and a panel address.
4. Enqueue a rough attempt for a panel from a fixture panel script; the worker produces attempt 1 through the deterministic provider.
5. The recipe records the panel-script document and version, reference locators by role, seed, provider, workflow version and both hashes.
6. Review → REGENERATE → attempt 2 exists and attempt 1 is intact.
7. Approve attempt 2. Its state is APPROVED; attempt 1 is not deleted and not approved.
8. Rerunning attempt 2's recipe with the deterministic provider reproduces identical bytes (the reproducibility contract).
9. Provider unavailable → the job is BLOCKED with remediation; the recipe survives.

The live manual slice (M3) targets three panels of the approved panel script:
- Scene 1, Page 1 — action;
- Scene 7, Page 35 — `I'm sorry, Fern.`;
- Scene 8, Page 40 — the reveal.

---

## 6. Milestones

| Milestone | Delivers | Heavy dependencies |
|---|---|---|
| **M1 — Reference Vault foundation** | locators; migration `0002` (Tier A/B/C catalog tables); phase-declared table registry + FK-direction invariant; storage + API for references, characters, outfits, visual modes, project selections; reader "Add as reference"; Character and Style Vault pages; §5.1 safety tests | none |
| **M2 — Artifact / attempt / review foundation** | Tier D tables; `visual.rough_attempt` job; deterministic sketch provider; review loop UI; §5.2 slice in CI | possibly an image library (open question 5) |
| **M3 — First real local provider** | ComfyUI adapter behind the contract; one versioned workflow; license records; manual three-panel slice | user-run ComfyUI + chosen model weights |
| **M4 — Chapter 1 rough expansion** | only after M3 review | — |

**Recommended first milestone: M1**, split into **M1a** (locators, schema, table registry and tier invariant, storage, API, tests) and **M1b** (web surfaces). It is dependency-free, and nothing downstream can be correct without it.

---

## 7. Risks and open questions

1. **Phase order.** Rough-manga generation is a pull-forward from Phases 10–12 against the approved Reference Vault document. Record an explicit decision (like gate #7) before M2.
2. **Public repository privacy.** Reference records and recipes name personal commercial media (hashes, notes, titles). Default: database and `ContinuumData` only, never Git. Decide what, if anything, a Git-committed project manifest may carry.
3. **Archive locator unit:** `#entry=<path>` (recommended) vs ADR-0005's example `#page=<n>`.
4. **Hashing unhashed source files** (currently 291) for content locators: read-only, but it costs time and I/O; on demand vs a bulk job.
5. **Image library** for thumbnails, page composition and upload validation (e.g. Pillow). Needs a dependency and an untrusted-input review (F-51).
6. **ComfyUI and models.** Separate user-managed install vs managed; which models; weight licenses (anime-style checkpoints often carry non-commercial or likeness terms); this machine's GPU/VRAM. Nothing is installed until decided.
7. **Rough quality.** Character identity consistency from references is uncertain with local models. The slice proves plumbing and provenance, not art quality.
8. **Project identity in the database.** Projects are file manifests; database rows use the manifest id as a string key (no FK). A project table later would be a migration.
9. **ADR-0003 and ADR-0005 are marked "Proposed".** Implementing locators, tiers and recipes adopts them; confirm or amend first.
10. **Per-panel vs per-page generation.** Recommend per panel, with deterministic page layout composed from the panel script; page composition quality is itself a review question.
