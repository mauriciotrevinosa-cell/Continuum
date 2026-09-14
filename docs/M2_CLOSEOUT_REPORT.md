# M2 Closeout Report

**Date:** 2026-09-14
**Branch:** `m2/closeout` (on top of `phase-1.5/full-vault-integration`)
**Scope:** close M2 (workflow validation only). M3 has not started.

M2 proves the rough workflow - panel script and recipe, reference bundle,
attempt, regenerate, review, persistence. It does not produce manga. The
deterministic sketch renderer draws labelled diagrams of a recipe.

---

## 1. Project ingestion: Git is read directly

**Root cause.** The studio read project documents from whatever working tree
was checked out (a code branch), and every committed document needed a
hand-edited manifest entry. New episode artifacts on the creative branch were
invisible or unfiled.

**Fix.**

* A project source can be a Git ref: `git:<repository>@<ref>[:<directory>]`.
  The project is read from the tree at the ref's current commit, with no
  checkout. The UI shows the ref and commit. **Resync from Git** fetches that
  remote-tracking ref and nothing else (`POST /projects/{id}/resync`). Local
  branches and the working tree are never touched.
* Manifest **conventions** register documents by file name. Drafts, panel
  scripts, Level 4 editorial overviews, GREEN LIGHT files, voice-check
  iterations, production notes, audits and visual packs are indexed the
  moment they are committed.
* `status_lifecycle` transcribes each author's own Status line into a
  lifecycle, using rules the manifest declares. Without a declared rule,
  prose still decides nothing.
* The **episode board** is computed from the committed documents on every
  read, using the levels the manifest declares. Level 4 = approved draft +
  approved panel script. It reports pages, what the next level is missing,
  and the last commit. Nothing about readiness is stored.
* Voice-check iterations still marked in review are shown as resolved once
  the episode's GREEN LIGHT exists. Their own lifecycle is left as recorded.

The manifest change was committed to the creative branch as metadata only;
no creative document was edited. While this work was in progress the
creative branch advanced through S1E19. The board picked that up with no
manifest change: **S1E1-S1E19 at Level 4, 1,227 provisional pages**, per
episode identical to the status overview. The project has 122 documents and
none are unfiled.

## 2. Review semantics: a technical pass is not a creative approval

| State | Meaning | Counts as manga |
|---|---|---|
| `GENERATED` | rendered, needs review | no |
| `TECHNICAL_PASS` | the workflow did its job (workflow verified) | never |
| `CREATIVE_APPROVED` | a person accepted the image as rough manga | yes, production only |
| `FINAL_APPROVED` | accepted as final art (after creative approval) | yes, production only |
| `REJECTED`, `SUPERSEDED` | history; bytes kept | no |

* Every rough artifact has a **purpose**: `PRODUCTION`, `WORKFLOW_TEST` or
  `NON_CANON_SAMPLE`. Tests and samples never occupy a production page's
  slot and are never counted.
* Every rendered attempt has an **output class**: `TEST_RENDER` (a test
  renderer's diagram) or `ARTWORK_CANDIDATE` (a real model's image). A
  provider must declare that it draws artwork; the default is test render.
* Creative and final approval require a production artifact and an artwork
  candidate. The service enforces this, and a database check enforces it too.
  Continuity promotion requires creative approval.
* `GET /projects/{id}/rough-completion` counts production work only and
  lists tests and samples separately.
* The UI offers only the decisions the API accepts. It shows TEST ONLY /
  TEST RENDER wherever a test could be mistaken for manga.

**Existing M2 data** was reclassified by migration `0004_m2_closeout`, not
deleted. Every rendered attempt became `TEST_RENDER`, and `APPROVED` became
`TECHNICAL_PASS`. Each `APPROVE` review became `TECHNICAL_PASS` with
`reclassified_from = APPROVE`. Artifacts whose attempts are all test renders
became `WORKFLOW_TEST`. On the real database, the S1E1 p35 Scene 7 slice is
now a workflow test with a technical pass on attempt 1. All 3 attempts,
seeds, hashes, bundle, derivatives and notes are intact.

## 3. Round trip and persistence

`tests/acceptance/test_m2_closeout.py` runs this sequence:

1. recipe and multi-reference bundle;
2. attempt 1;
3. regenerate with a chosen seed, producing attempt 2;
4. creative approval is refused;
5. technical pass;
6. restart: every database connection dropped, a new API app, a new worker.

After the restart it verifies artifact identity and purpose, panel script,
intent and execution hashes, exact reference ids with their provenance
snapshots, source plate crop, mask and output, seeds, ancestry, review notes,
states and completion counts. The restarted worker then regenerates again
from the persisted bundle.

On the real stack, the API, worker and web were stopped and started again,
and the p35 artifact and the episode board were read back unchanged.

## 4. Reference bundle foundation

* `attempt_input.provenance` snapshots each chosen reference at request time:
  origin, class, collection, creator, rights, training eligibility, asset hash
  and the catalog's provenance record. Attempts made before this revision have
  no snapshot, and none was invented for them.
* **Character manifests**
  (`GET /projects/{id}/characters/{character_id}/manifest`) resolve every
  linked reference by facet: identity, body, wardrobe, expression, pose and
  accessories. They also record each reference's lane: canonical manga,
  anime, official art, supplemental, project-created.
  * "Preferred" only ranks references within a facet.
  * Fan art grounds a character only with an explicit project standing.
  * Unsorted material never grounds a character.
  * Reference manifests now include the whole complementary set
    (`continuum.reference-manifest/2`).
* **Original project characters** (`origin = PROJECT_ORIGINAL`) belong to a
  project and name its design documents, such as a visual reference pack read
  from the committed project.
  * Source pages, anime frames, official art and fan art can never ground
    their identity or body.
  * Missing facets are reported and nothing is substituted.
  * On the real Vault today only two characters exist, with no original
    character profile yet. One of the two has identity, body, wardrobe and
    expression; the other has identity only.

## 5. Family coverage

The acquisition engine (`continuum-acquisition`, separate repository) reported
a sequel arc as MISSING. Its chapters were held inside the parent work's
download parts, numbered after the parent's final chapter. Coverage now
reports such a continuation as UNKNOWN (present, count unverified) with flag
`CONTAINED_CANDIDATE`, naming the chapters and files.

* The rule applies only when the parent is complete.
* An ongoing parent's later chapters stay its own.
* The structure audit no longer plans an empty folder for it.
* A regression test with invented works was added.

Regenerating the real reports without re-reading the Vault changed exactly one
of 331 verdicts, the reported case. The catalog, sources and index were
unchanged.

## 6. Series view

Manga and anime sections open to their works, seasons and groups, each
collapsed with its count. Any list longer than 50 folds into numbered ranges.
The group and range holding "where you left off" open automatically. Every
chapter and episode remains directly reachable.

## 7. The manual rough workspace

Roughs and the rough workspace are labelled **advanced / override**. They
remain the tool for masks, source-derived edits, chosen references and seeds,
composites and one-page corrections. They are not the way to produce whole
chapters; that is the batch workflow from chapter packages (M3).

## Schema

Migration `0004_m2_closeout` is additive, and reclassification rewrites no
history without recording it:

* `rough_artifact.purpose`, with purpose added to its unique key;
* `rough_attempt.output_class`, with checks `output_class_iff_rendered` and
  `creative_approval_needs_artwork`;
* split state and decision vocabularies;
* `attempt_review.reclassified_from`;
* `attempt_input.provenance`;
* `character_profile.origin`, `project_key` and `design_documents`.

Downgrade refuses when data exists that revision 0003 cannot represent.

## Open items for M3

* No image model is connected; every render is still a test render.
* Character manifests exist as a capability, but most of the cast has no
  references yet.
* No original character profile has been created. The creator photo
  references have not been imported.
* Attempts do not yet consume character manifests automatically (M3 B1).
