# Continuum — Phase 1.5 Full Vault Integration Report

**Status:** READY FOR REVIEW — not merged. Phase 1 M1+M2 is on `master` (merge `3fcbcb7`, tag `phase1-m1-m2`); the two creative branches were merged separately (#9, #10). M3 has not started.
**Date:** 2026-09-14
**Branch:** `phase-1.5/full-vault-integration` (from `master` after #10)

The question this phase answers: *can Continuum account for the whole configured Vault, retrieve from it, remember where a person is in it, and hand real Vault inputs to production - without changing a byte of it?* On this machine, against the real Vault (about 320 GB, 2,545 files) and the real fan-art intake folder (821 files), the answer is yes, with the limits listed in §8.

This report is public: it gives counts, never titles, handles or file names. The coverage and import reports that name files stay under `ContinuumData/generated/reports/` on the local machine.

---

## 1. What was built

| Req. | Delivered | Where |
|---|---|---|
| **A** full catalog | Every file under every configured root is scanned - the Source Vault and any `CONTINUUM_INTAKE_ROOTS` folder - with no sample limit. Each ends `CATALOGUED`, `UNSUPPORTED` (with a reason), `FAILED` (with the error, retried next scan) or `MISSING`; every entry the walk skips is recorded with why. ZIP/CBZ central directories are read: page folders in the reader's own order, each video member with size, CRC-32 and compression. | `continuum_storage.survey`, `continuum_library.vault_catalog`, migration `0003_phase15`, job `library.catalog_scan` |
| **B** retrieval | Series, units (chapter, page group, episode, video, image, document) and a unified search across Vault units, references, Inbox candidates, project documents and music notes. Filters: series, season, episode, chapter, material, collection, creator, confidence, root, media id. Provenance chains: series → archive → chapter → page (`zip:sha256:…#entry=`) and series → archive → member → instant (`zip:sha256:…#entry=…&t=`). Works inside one series folder (spin-offs, if-stories, differently named programs) are kept apart, from the acquisition engine's work mapping or the folder, never merged into the main work's chapters or seasons. | `continuum_library.identify`, `vault_views`; `/catalog/*`; Studio → Vault |
| **C** progress | Per-unit reading page and playback position, opened and completed times, keyed by a location-derived unit key so rescans and re-identification never detach it. "Continue" offers resume, the next chapter or episode, or finished; the reader and the player save and restore automatically. | `continuum_library.progress`, `media_progress`; Reader, Player, Studio home |
| **D** incremental | Size + mtime + quick fingerprint per file; unchanged files are not reopened; engine hashes are reused while size and mtime hold, the rest are hashed once by a resumable per-file job (`library.catalog_hash`); a scanner version re-examines files once when identification rules change; failed files are retried; exact duplicates are linked to their first copy and never deleted; a catalog is bound to the folder it scanned (a digest, not a path). | same, plus `CatalogRecordSupplement` |
| **E** coverage | Machine-readable JSON and a Markdown report after every scan, and the same data live in the Studio: files by root, catalogued / unsupported / failed / missing / skipped with reasons, archives by view, members indexed, units by kind and confidence, uncertain identifications with their flags, duplicates, hash state, references by origin, collection, rights and training, project documents. | `continuum_library.coverage`; `/catalog/coverage`; Studio → Coverage |
| **F** production bridge | Deterministic reference manifests: characters and their preferred references, chosen references (optionally every project-canonical one), manga pages and anime moments resolved to content locators, project documents with lifecycle / maturity / authority and content hash, music notes, a chapter package version and generation settings. The same request resolves to the same canonical manifest hash and is stored once. Unknown rights, material not approved for training and low-confidence identification are listed as warnings. Nothing names a project, series or episode in code. | `continuum_production.manifest`; `/projects/{id}/reference-manifests` |
| **G** chapter package | A generic Pydantic schema (project, season, episode, chapter, characters, scenes, pages, panels with description, dialogue, required source references, optional visual references, generation notes, generated outputs, provenance, approval state), cross-reference validation, versioned saves (identical content is not a new version) and approval changes with optimistic concurrency. The JSON Schema is published and checked for drift; the template holds placeholders only. | `continuum_production.chapter_package`; `docs/schemas/chapter-package.v1.schema.json`; `docs/templates/chapter-package.template.json` |
| **H** creative project | Project documents gain `maturity` (ROUGH / DETAILED / PRODUCTION_READY), `authority` (RULE / CORRECTION / INDEX / CONTENT) and the partial `overrides` a document states in its own text; the API reports `overridden_by`. All 28 project documents are registered in the manifest, transcribing their authors' status lines (§5). | `continuum_storage.projects`; `docs/creative/continuum.project.json`; project document pages |
| **I** music | Project music notes: track, artist, reference (a link is stored, never fetched), episode, scene, mood, intended use, notes. | `continuum_production.chapter_package.MusicReferences`; `/projects/{id}/music` |
| anime archives | Videos inside DEFLATE archives are prepared on demand by a durable job (`library.member_extract`) that copies one member, size- and CRC-verified, into a bounded, content-addressed cache (`cache/archive-members`, LRU eviction of Continuum's own copies, default 20 GB); the player streams it with byte ranges and saves progress; frame capture records the archive/member/instant locator. A changed archive is refused, never served. | `continuum_storage.member_cache`, `continuum_library.members`; `/watch/{member}` |
| FanArt import | `library.intake_import` after a fresh scan and hash: images become references (class `UNSORTED`, origin `FAN_ART`, collection, creator and posting date from the download-style name, `rights_status = UNKNOWN`, `training_eligibility = MANUAL_REVIEW`), clips become Inbox candidates, exact duplicates link to the first copy, installers are rejected with the catalog's reason; JSON + Markdown import report; a second import changes nothing. Originals are stored byte for byte; the folder is only read. | `continuum_library.collection_import`; Studio → Collection |
| root page | `/` is the Studio (search, Continue, folders, projects, series); the Phase 0 status page moved to `/status`. | `apps/web/app/page.tsx`, `app/status` |

Supporting changes: the reader's page order compares folder by folder (chapter 71 before 71.5); the worker releases dependent jobs as soon as a prerequisite finishes; ZIP locators may carry an instant (ADR-0005 amendment); the reference class vocabulary gains `UNSORTED`.

## 2. Decisions

1. **Observation and interpretation are separate tables.** Files and archive members are Tier A observations; chapters and episodes are Tier B interpretations with confidence, evidence and flags. Identification never renames, moves or regroups a file.
2. **Nothing is guessed silently.** A name that does not match its series folder or a known title, an episode number without a season, a program that extends the series title, a page folder that does not name a chapter - each lowers confidence and is flagged. Known titles from the acquisition engine's works catalog and its file-to-work mapping are used as evidence.
3. **Hashing is a background pass, not a startup cost.** A scan records size, mtime and a quick fingerprint; the full SHA-256 is computed once per file by a resumable job, reusing the engine's hashes.
4. **Playback of archived videos uses a managed cache, not the Vault.** DEFLATE members cannot be seeked in place; one member at a time is copied into `ContinuumData/cache` on request and evicted least-recently-used first.
5. **Paths are observations.** `catalog_entry` and `media_progress` hold root-relative paths (checked by constraints and the schema invariant); unit views sent to the browser carry ids and names, not paths. Only the coverage screen shows root-relative names, so a person can find an excluded file.
6. **Migration `0003_phase15` was amended in place while unreleased** (a `subseries` column and a wider schema-version column). The local application database was backed up, migrated and re-scanned.
7. **Creative precedence is transcribed, not resolved** (§5).

## 3. Real-Vault acceptance (this machine)

All checks ran through the running API, worker and web app against the configured Vault and intake folder.

| # | Check | Result |
|---|---|---|
| 1 | Open Studio | `/` renders the Studio (200); `/status` renders system status (200). |
| 2 | Browse / search the real Vault | 51 series; 3,366 files found, 3,363 catalogued, 3 unsupported, 0 failed, 0 missing, 0 unaccounted; 12,445 searchable units; unified search returns results. |
| 3 | Real manga | A chapter unit resolved to a page served from its archive (WebP bytes); the reader opens at that page. |
| 4 | FanArt collection | 821 files: 724 image references + 74 clip candidates imported (798), 21 exact duplicates linked, 2 installers rejected, 0 failed, 0 with unknown creator or date. Every reference: `FAN_ART`, `UNSORTED`, rights `UNKNOWN`, training `MANUAL_REVIEW`. |
| 5 | Episode inside an anime ZIP | A 325 MB DEFLATE member prepared by the worker, streamed with a 206 byte range (Matroska signature), and played in the in-app Chromium (1920 px, duration read, position resumed). |
| 6 | Provenance | Episode: series → archive → member → unit → archive hash. Chapter: series → archive → unit → archive hash. |
| 7 | Progress | Reading page and playback position saved from the API and the UI. |
| 8 | Production manifest | Built from a real chapter page, a real archived-episode moment, a FanArt reference and the production-ready project document; the same request twice gave the same id and hash; three warnings (rights, training, unsorted). |
| 9 | Restart | After restarting API and worker: reading page, playback position, Continue items, catalog totals, the manifest and the prepared member were all still there. |
| 10 | Incremental rescan | Both roots, 3,366 files: 35 s, every file `unchanged`, the hash passes had nothing to hash (one duplicates unit each). |

Also verified on real data:

- **Interrupted scan:** the worker was killed at unit 33 of 103; a new worker reclaimed the expired lease and resumed - 104 unit starts for 103 units (only the in-flight unit ran twice).
- **Full hash pass:** 321 files / 143 GB not hashed by the engine were hashed in about 3.5 minutes; 2,223 engine hashes were reused.
- **Scanner-rules change:** raising the scanner version re-examined all 3,366 files in about 2.5 minutes with no re-hashing, and kept the import record of every intake file.
- **Read-only:** a metadata snapshot (size, mtime, ctime) of all 3,663 files and folders of the Vault and the intake folder was identical before and after everything above.

## 4. The anime archives added after the engine's last scan

19 video archives (split download parts) held 96 videos that the acquisition engine had never listed. Evidence came only from member names and folders, plus the engine's known titles:

- 80 identified with HIGH confidence (72 regular episodes, 5 OVAs, 2 specials, 1 recap), seasons 1-3;
- 15 MEDIUM: episodes of differently named programs inside the same series folder, grouped apart and flagged "a separate program within the series?";
- 1 LOW: a special with no episode number in its name.

No title is hard-coded; the series is whatever folder the archives are in.

## 5. Creative project registration

The manifest registers all 28 documents; `discover` still shows any future unregistered file as UNFILED. Transcription:

| Author's status (verbatim form) | lifecycle | maturity | authority |
|---|---|---|---|
| AUTHORITATIVE WORKFLOW / PROJECT RULE | APPROVED | – | RULE |
| AUTHORITATIVE ROUGH ORDERING DECISION | APPROVED | ROUGH | RULE |
| AUTHORITATIVE ROUGH CORRECTION | APPROVED | ROUGH | CORRECTION (+ `overrides` the placement assumption only) |
| CURRENT WORKING OVERVIEW / SOURCE-OF-TRUTH INDEX | APPROVED | – | INDEX |
| APPROVED ROUGH … (roadmaps, addenda, handoff, audit, episode concept) | APPROVED | ROUGH | CONTENT |
| APPROVED ORDERING DECISION / FINALE DIRECTION | APPROVED | – | CONTENT |
| ROUGH PLANNING — not locked canon | DRAFT | ROUGH | CONTENT |
| ROUGH / HIGH-CONFIDENCE — not locked canon | REVIEW | ROUGH | CONTENT |
| candidate character / high-priority visual anchor | REVIEW | ROUGH | CONTENT |
| S1E1 structure and Draft 1 (approved) | APPROVED | DETAILED | CONTENT |
| S1E1 panel script (approved, next gate rough manga) | APPROVED | PRODUCTION_READY | CONTENT |

Partial overrides recorded because the documents state them: the placement correction over the day-in-the-life concept; the S1→S2 G3 handoff over older G3 timing language; Opening Groups and Opening Group 2 over the creative direction where more specific.

**For a human decision:** the late-S1 order and finale document (approved ordering) places the day-in-the-life episode and fixes a 20-episode count, while the placement correction says placement is open and the G3 / road-days rule says final numbering remains open. None of the three states that it supersedes the others, so Continuum shows each with its own status and records no precedence between them. The two source-of-truth transcriptions (INDEX as APPROVED; the candidate character as REVIEW) are also worth confirming.

## 6. Tests and gates

| Gate | Result |
|---|---|
| `ruff check`, `ruff format --check` | pass |
| `mypy packages apps workers` (strict) | pass (97 source files) |
| `lint-imports` | 4 contracts kept |
| `pytest` with PostgreSQL (isolated `continuum_test`) | 541 passed, 1 skipped (Windows, local); CI on the pushed commit |
| web: `lint`, `typecheck`, `vitest`, `next build` | pass (15 vitest tests) |
| OpenAPI client regenerated | committed |

New acceptance suites (all content invented): `test_phase15_vault_catalog.py` (accounting, archives, identification, works, hashing, incremental rescans, interruption, supplement, coverage, intake), `test_phase15_retrieval_and_progress.py` (series/search by ids, progress across rescans and restarts, archived episodes, eviction, changed archives, frame provenance, FanArt import), `test_phase15_production_inputs.py` (manifests, no hard-coding, chapter packages, schema drift, template, music, document standing). Updated: API surface, migrations, schema invariants, locators.

## 7. Operating it

- `CONTINUUM_INTAKE_ROOTS=Collection:material=path` adds a read-only intake folder (for example `FanArt:fan_art=D:/Intake/FanArt`); `CONTINUUM_MEMBER_CACHE_BYTES` bounds the archive-member cache.
- Studio → Coverage → **Scan now** queues a scan and a hash pass per root. Studio → Collection → **Import collection** rescans, hashes and imports.
- Reports: `ContinuumData/generated/reports/catalog/coverage-latest.{json,md}` and `reports/imports/<collection>-latest.{json,md}`.
- Apply migration `0003_phase15` before starting the new API and worker (`uv run alembic upgrade head`).

## 8. Limits and open items

- **No FFmpeg.** Archived and standalone videos play only where the browser decodes the codec (the in-app Chromium decoded this Vault's HEVC Matroska; other browsers may not). Frames are captured by the browser; there is no server-side frame extraction or thumbnailing yet.
- **Identification is heuristic.** 137 units in the Vault are LOW confidence (111 page groups without chapter folders, 26 episodes with poor names); they are flagged, searchable and listed in coverage, not corrected.
- **Duplicates are exact bytes only.** No perceptual matching; re-encoded copies stay separate.
- **Search is substring matching** over prepared text, not ranked full-text search.
- **FanArt references are UNSORTED** until a person sorts them; nothing is approved for training.
- **Single local profile.** Progress is per project key or global; there are no user accounts.
- **Manifests, chapter packages and music notes have APIs, not screens yet.** The rough-attempt builder does not yet consume a manifest.
- **The creative branch may keep receiving story commits** after #10; they need their own merge.
- **HEIC support still depends on `pi-heif` (LGPL-3.0)**, unchanged from Phase 1 and documented in `docs/DEPENDENCIES.md`.

## 9. Recommendation for M3

Start M3 from this branch once reviewed and merged, with this order:

1. Let the rough-attempt builder take a reference manifest (by id) as its bundle, so every attempt cites real Vault pages and moments through locators already proven here.
2. Resolve the §5 precedence question and create the first chapter package for the production-ready episode from its approved panel script - authored by a person, validated by the schema.
3. Decide FFmpeg (a local, offline tool) for server-side frame extraction and thumbnails before any work that needs frames without a browser.
4. Sort the FanArt references that are meant for the project (class, characters, standing) before they are allowed into manifests without warnings.

Do not begin broad manga generation until 1 and 2 are done.
