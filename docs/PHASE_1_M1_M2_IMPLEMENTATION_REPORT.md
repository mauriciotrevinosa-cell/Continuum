# Continuum — Phase 1 M1 + M2 Implementation Report

**Status:** READY FOR INDEPENDENT AUDIT — not merged; `master` and the `continuum-phase-0` tag are untouched
**Date:** 2026-09-13
**Branch:** `phase-1/integrated-candidate` (from `master` = `continuum-phase-0` = `91025d7`)
**Plan:** `docs/PHASE_1_IMPLEMENTATION_PLAN_v0.1.md` plus the kickoff expansion (§15–31) and the
Reference Inbox / multistyle expansion
**Companion:** `docs/PHASE_1_REUSE_AUDIT.md`

The chain proven end to end:

`held manga page → region → reference (character / style / scene source) → reference bundle by role
→ recipe (intent + execution) → durable worker job → rough attempt (new artifact) → review →
regenerate / approve → continuity reference`

---

## 1. Commits on the branch

| Commit | What |
|---|---|
| `b58ad76`, `3e39c5c`, `6d3dec8` | approved panel script, reference-vault direction, plan (before this pass) |
| `0a42dd2` | the database suite runs against an isolated `*_test` database (the suite drops tables; the app database now holds the user's catalog) |
| `0ec223d` | content locators (`continuum_core.locators`), reference vocabulary, Tier A–D schema, migration `0002_phase1`, table registry + FK-direction invariant |
| `e5da717` | `continuum_imaging`: bytes-in/bytes-out decode (allowlist, 120 MP budget), crop, preview, mask, pixel digest, deterministic sketch |
| `448b5ae` | schema expansion: Reference Inbox, reference uses, subject kinds (monsters), multistyle visual modes with project-scoped assignments |
| `697963b` | M1 backend: read-only manga source access, reference catalog, inbox, Character/Style Vault views, id-only API |
| `2e17729` | M2 backend: `ROUGH_RENDER` provider contract + deterministic sketch fake, `continuum_production`, `visual.rough_attempt` worker handler, production API |
| `5b5624e` | M1b + M2 web: reader "Add reference", frame capture, References, Character Vault, Styles & modes, Inbox, Roughs and rough workspace |
| `062a15e` | two defects found during manual validation (review state refresh, link paste parsing) |
| this commit | reuse audit, this report, project-hardcoding invariant, dependency record |

## 2. Decisions taken during implementation

1. **Scope pull-forward recorded.** The kickoff explicitly commissions M2 (rough attempts) before the Phase 10–12 generation work. It is implemented behind the provider contract with a deterministic fake only; no model, ComfyUI or Remotion is installed. This is the plan's open question 1, decided by the kickoff.
2. **Archive locator unit = entry name** (`zip:sha256:<archive>#entry=Ch0001/008.webp`), not position. A page index is kept beside it only as the display position it was chosen at; navigation back re-resolves the entry in the archive's current reading order.
3. **Engine hashes reused, never trusted blindly.** The acquisition engine's recorded SHA-256 names the file only while size *and* mtime still match; otherwise the file is re-hashed through the read-only reader. A file that changed after cataloguing is refused (`SourceChangedError`, HTTP 409 / BLOCKED `MISSING_SOURCE_ASSET`), never served.
4. **Pillow adopted** (plan question 5) inside `continuum_imaging` only, which never receives a path.
5. **Separate `ROUGH_RENDER` capability** rather than reusing `IMAGE_GENERATE`: the Phase 0 acceptance test that proves "selectable but refuses to run" keeps its meaning, and a future ComfyUI adapter can declare both.
6. **Bundles are snapshotted.** Attempt inputs copy locator, region, role, character, outfit and aspect, so removing a catalog record breaks neither provenance nor regeneration.
7. **The API records and enqueues; the worker renders.** Attempt rows (derivatives, output hash, GENERATED) are written in the job's session and commit only with the step completion under the Phase 0 ownership lock. Worker BLOCKED handling now covers any `ContinuumError` carrying `blocked_reason` (missing provider, unreachable source), not only the synthetic one.
8. **Links are never fetched.** Inbox URL candidates are stored and shown; a link becomes a reference only when the user attaches the image they saved.
9. **Visual modes never belong to a character.** A mode reaches a character only through a Tier C project assignment (episode / scene / page run / panel / event; directorial, scene-tone or character-controlled). The invariant test forbids any other table linking the two.
10. **Migration `0002_phase1` was amended in place** while unreleased on this branch (never on `master`). The local application database was migrated once, at its final form.

## 3. Definition of done (kickoff §31)

| | Requirement | Where it is met | Proof |
|---|---|---|---|
| **A** | Character Vault: identity, wardrobe (outfits: source/default, project, era, season, condition, preferred), acting, sources by origin, project standing, provenance, add while reading | `continuum_library.catalog` / `views.character_vault`; `/library/characters/[id]`; reader "Add reference" | `test_phase1_reference_vault.py::TestCharacterVault`, `test_phase1_library_api.py`; manual §6 |
| **B** | Style Vault accepts real pages/panels; technique facets; identity and technique separate; multistyle modes | `views.style_vault`; `/library/styles`; `ProjectVisualModeAssignment` | `TestStyleVaultAndVisualModes`; `tests/invariants/test_schema_tiers.py` |
| **C** | Source access: CBZ/ZIP pages, standalone images, PDF pages (whole page), video instants; page → crop → add to Character / Style / scene source; provenance, hash, entry locator, display index, normalized crop | `continuum_storage.sources`, `catalog.add_from_source` / `add_from_frame` | `test_phase1_source_access.py` (20), `TestReferencesFromHeldPages` |
| **D** | Rough pipeline: NEW_GENERATION, SOURCE_DERIVED_EDIT, COMPOSITE (and LAYOUT_ONLY) with bundle by role and recipe | `continuum_production`, worker `RoughAttemptHandler` | `test_phase1_rough_production.py::TestFourModes`, `test_phase1_production_api.py` |
| **E** | Artifact history append-only | numbered attempts, review history, supersede on approval | `TestAppendOnlyHistory` |
| **F** | Editing foundation: plate, protected / removed / replaced regions, masks and crops as derived artifacts, execution fields ready for inpainting (mask, strength, control inputs, crop, compositing) | `recipe.py` (intent/execution, contradiction check), `render.py` (SOURCE_CROP, MASK, OUTPUT) | `test_source_derived_edit_makes_a_new_artifact_and_keeps_the_source`, `TestIntentValidation` |
| **G** | No source destruction | read-only reader; derived bytes only under `ContinuumData/{library,generated}`; soft delete | Vault snapshots in every catalog/production test; manual SHA-256 check §6 |

## 4. Acceptance list (kickoff §30 and the original test list)

| Requirement | Test(s) |
|---|---|
| real held manga browsable read-only | Phase 0 viewer tests; manual §6 |
| page → reference round trip; region maps to the exact page | `test_region_of_a_page_roundtrips_to_the_exact_page`, `test_page_region_to_character_vault_roundtrip` (HTTP) |
| same page, several roles, one observed asset | `test_the_same_page_serves_many_roles_over_one_asset` |
| Character and Style Vault accept source references | `TestCharacterVault`, `TestStyleVaultAndVisualModes` |
| source plate attachable to a recipe; preserve/remove/replace intent recorded | `TestFourModes`, provenance assertions on operations |
| deterministic SOURCE_DERIVED_EDIT creates a NEW artifact; source bytes byte-identical; source never overwritten | `test_source_derived_edit_makes_a_new_artifact_and_keeps_the_source` |
| deleting a reference does not delete the source | `test_removing_references_never_touches_the_source`, `test_removing_a_reference_keeps_provenance_and_regeneration` |
| several artifacts from one source page | `test_one_source_page_feeds_several_artifacts` |
| provenance reconstructs the chain | `provenance_view` assertions (unit and HTTP) |
| reference records: no traversal; artifacts cannot escape the root | locator parser tests (35), hostile project/episode/URL tests, `/vault-api` allowlist unit tests, F-50 surface test, AST filesystem guard now covering `library` and `production` |
| character / outfit / style separate | schema invariants, outfit-ownership tests |
| attempts append-only; reproducible pixels; crash re-render is a no-op | `TestAppendOnlyHistory`, `test_rendering_twice_is_a_no_op` |
| durable generation job recoverable; missing provider or source → BLOCKED with remediation, then completes | `TestBlockedAndRecovery` (real worker loop) |
| no The Arrivals hardcode; no personal title/path/hash in Git fixtures | `test_no_project_hardcoding.py` (new), `test_no_franchise_strings.py`; all fixtures invented |
| links never fetched | `no_network` fixture in inbox tests |
| user tags vs analysis output labelled | `test_user_and_analysis_descriptors_are_labelled` |

## 5. Expansion coverage

| Expansion item | Implementation |
|---|---|
| Reference / Inspiration Inbox: batch URLs, bulk images, clips, screenshots; source link or local provenance, creator handle, notes, tags, class, intended use | `continuum_library.inbox`; `/library/inbox` (paste links with `@handle #tags`, drop files, bulk triage, accept / dismiss / restore) |
| Reference classes IDENTITY … CONTINUITY | `ReferenceUse` (12 values) alongside the Tier B class (CANON / TECHNIQUE / CONTINUITY / MOOD) |
| Multistyle visual modes across panel / scene / sequence / episode / event; chibi as a mode decision, involuntary or character-controlled | `VisualModeCategory`, `ModeScope`, `ModeTrigger`; `modes_in_effect`; recorded into every recipe; per-character "drawn in mode" in the attempt builder; identity row untouched (tested) |
| Monster designs | `SubjectKind` MONSTER / CREATURE; `MONSTER_DESIGN` use |
| Source reuse modes | the four `RoughMode`s |
| Manga / anime source access for character, style, scene source, source plate | reader and image viewer "Add reference"; player "Capture frame to inbox" (the episode is observed, not copied) |
| Fan art first-class and distinguishable | explicit `ReferenceOrigin`, creator handle and link; origin chip everywhere; production origins cannot be declared by a person |
| Production workflow: browse manga, browse fan art, classify by role, select plate, identity bundle, style bundle, rough derived panel/page, review / regenerate / approve | Library → Roughs → rough workspace |

## 6. Local manual validation (§28) — not in Git

Run on this machine against the real Source Vault,
the application database (migrated to `0002_phase1`) and `ContinuumData`, with the API, the
standalone worker and the production web build. Titles are deliberately not named here (public
repository); the catalog rows exist only in the local database.

- Two project characters created; an outfit added through the Character Vault page.
- In the reader, a face region drawn on page 8 of a held manga archive (CBZ/ZIP, ~200 MB) and added as *Identity · Face*, preferred. The record carries `zip:sha256:<archive>#entry=Ch0001/008.webp`, display index 7 and the normalized region; its preview is the crop and "Open page 8 in the viewer" returns to the page.
- Further references through the API: an outfit region linked to the outfit, a full figure marked canonical for the project, an expression page with a mood tag, a second character's page, a technique page tied to a comedic-deformation mode, and a page registered as the source plate for S1E1 page 35. Held-file hashes were taken from the engine index (six references in under two seconds).
- The Character Vault page grouped them into Preferred, Identity (Face, Full body), Wardrobe (the outfit with its reference), Acting (Expression) and In projects (canonical: 1).
- In the rough workspace for S1E1 page 35 (panel script version read from the manifest): the scene source was added as the plate and the face reference as CANON; a REMOVE region and a REPLACE region naming the character were drawn on the plate; the attempt was requested. The worker rendered it (SOURCE_CROP, MASK, OUTPUT under `generated/`); provenance led back to both archive entries with their page indices. The attempt was approved, then regenerated: attempt 2 has the same intent hash, a new seed and execution hash; attempt 1 stayed approved.
- On a held episode (MKV, ~635 MB), a frame at 1:35 was captured into the inbox and accepted; the reference records `video:sha256:<episode>#t=00:01:35.000` and opens the episode at that moment.
- Two links pasted into the inbox were stored without any request being made (one was dismissed after the paste-parsing defect below).
- **Vault after the run:** metadata snapshot (size, mtime, ctime for every file and folder) identical to before — added 0, removed 0, changed 0 — and the two held files used were re-hashed end to end; both SHA-256 values equal the locators recorded in the catalog.

Defects found and fixed during the run (`062a15e`): the rough workspace kept showing an attempt's pre-review state until reselected; links pasted without line breaks merged into one candidate.

## 7. Gates

| Gate | Result |
|---|---|
| `ruff check .` / `ruff format --check .` | pass |
| `mypy packages apps workers` (strict) | pass (77 source files) |
| `lint-imports` (filesystem boundary, core independence, layering incl. `continuum_production` above `continuum_library`, worker ≠ API) | 4 kept |
| `pytest` with PostgreSQL (isolated `continuum_test`) | pass — see the final push's CI run |
| web: `lint`, `typecheck`, `vitest`, `next build` | pass |
| OpenAPI client drift | regenerated (`apps/web/lib/api/generated/schema.d.ts`) |
| GitHub Actions on every pushed commit of this pass | green (M1 `34784320932`, M2 `34785383446`; later runs listed in the handoff) |

## 8. Known limitations (honest)

- **The renderer is a diagram, not art.** `fake.deterministic-sketch` draws the plate, edit regions, placements and the bundle strip. It proves plumbing, provenance and reproducibility, not identity consistency or quality (plan risk 7). The UI says so on every rough screen.
- **PDF pages** can be referenced whole, but not cropped, previewed or used as a plate (no rasterizer).
- **Video is never decoded server-side.** Frames are captured by the browser; whether a container plays (e.g. MKV) is the browser's decision.
- **Unhashed Vault files** are hashed on first use, read-only; a large file not yet indexed by the engine can take time on its first reference.
- **Inbox clips** are served whole (no byte ranges) and uploads are buffered by the web passage; the 256 MB clip cap bounds both.
- **No UI to remove characters, outfits or visual modes** (the API supports soft removal).
- **Web flows have no browser end-to-end tests in CI**; they are covered by API tests plus the manual run above.
- **No authentication** (Phase 0 loopback-only rule still applies).
- **Source Intelligence** is prepared (ANALYSIS descriptors require an analyzer name; UI labels them ANALYSIS DERIVED) but not implemented; nothing is inferred automatically.

## 9. Not done, by instruction

No merge to `master`; no tag change; no ComfyUI, Remotion, model or voice/video work; no whole-chapter generation; nothing downloaded or fetched; nothing written into the Source Vault; no personal catalog data, titles, paths or hashes committed.
