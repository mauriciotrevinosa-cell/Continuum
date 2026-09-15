# M3 — Page-by-page manga production (critical path)

Status: **web production loop, character corpus and ComfyUI backend implemented and tested; no GPU artwork endpoint connected yet.**
Branch: `m3/critical-path` (on top of `m2/closeout`). Migrations `0005_m3_manga`, `0006_m3_corpus`.

The goal of M3 is a non-canon test chapter drawn page by page, reviewed by the
creator, iterated, and — when it passes — a frozen production profile that
canonical Episode 1 production starts from. Canonical production never starts
automatically.

## 1. The loop

```
committed sources (Git) ──► materialized chapter (deterministic, hashed)
                                  │
profile (DRAFT) ──► run (NON_CANON_SAMPLE) ──► page 1 READY, pages 2..n WAITING
                                  │
            assemble bundle: grounded characters + continuity (approved pages)
                             + manga grammar (Vault layout) + environment
                                  │
            attempt = durable render job ──► composition master
                                              ├─ black-and-white finish (same geometry)
                                              └─ color finish (same geometry)
                                  │
            review: REJECT / REGENERATE (append-only) / approve
                                  │
            approve ──► continuity version + 1 ──► next page READY
                                  │
            sample decision: FAIL closes · PASS promotes the PROFILE (never images)
                                  │
            START CANONICAL E1 — only with a PROMOTED profile and no creative blocker
```

## 2. Modules

| Concern | Module |
|---|---|
| Chapter materialization (pure) | `packages/production/src/continuum_production/materialize.py` |
| Runs, pages, bundles, review, continuity, invalidation, promotion | `packages/production/src/continuum_production/manga.py` |
| Page render execution (worker) | `packages/production/src/continuum_production/render.py` (`_render_page`) |
| Artwork backend boundary | `packages/providers/src/continuum_providers/artwork.py` |
| B&W finish, test color tint, layout analysis | `packages/imaging/src/continuum_imaging/manga.py` |
| Tables | `packages/db/src/continuum_db/models/manga.py`, migration `20260914_0005_m3_manga_production.py` |
| Character reference corpus | `packages/production/src/continuum_production/corpus.py`, `packages/db/src/continuum_db/models/corpus.py`, migration `20260915_0006_m3_character_corpus.py` |
| ComfyUI backend | `packages/providers/src/continuum_providers/comfy.py` |
| HTTP routes | `apps/api/src/continuum_api/routers/manga.py`, `apps/api/src/continuum_api/routers/corpus.py` |
| Web | `apps/web/app/projects/[projectId]/manga/production`, `apps/web/app/production/runs`, `apps/web/app/library/characters/[id]` |
| Character pack import (dry-run by default) | `scripts/import_character_pack.py` |
| Acceptance tests | `tests/acceptance/test_m3_page_production.py`, `test_m3_character_corpus.py`, `test_m3_comfy_backend.py` |

## 3. Materialized chapter

`materialize_chapter()` reads the base panel script, the season production
overlay and the revision beats (all committed, all with commit + content hash)
and returns pages in reading order. Each page carries: base page number, label,
scene, directions, dialogue (speaker / internal noise), explicit "No …"
constraints, detected characters, page intents (close-up, back shot, magic
effect, quiet acting, chapter end, …), origin (`base` | `overlay`), integrated
page number (provisional), lineage and a page hash.

Overlay insertions are **never placed by guesswork**. A `PlacementDecision`
(item, chapter, after base page, `PROPOSED` | `CONFIRMED`, author) places one.
Without decisions the chapter has only base pages and a warning when the
overlay's allocation says otherwise. A sample may use `PROPOSED` placements;
canonical production requires `CONFIRMED` ones.

Same inputs + same decisions ⇒ same body hash ⇒ same row.

## 4. Invariants

* **Page by page.** A page is `WAITING` until the page before it is approved.
* **No silent substitution.** A character without grounded identity and body
  blocks its pages: `BLOCKED` / `MISSING_REQUIRED_REFERENCE`, naming the missing
  facet. An original character is grounded only by the creator's own
  references; a reference marked `STYLE` is stylization, never grounding.
* **Reference roles are kept apart.** Every attempt input has a role: `CANON`
  (identity), `CONTINUITY` (approved pages of this run), `GRAMMAR` (page
  structure only — never identity), `ENVIRONMENT` (never overrides the
  project's setting canon).
* **One composition, two finishes.** The black-and-white and color finishes
  must share the master's geometry and name the master's hash; otherwise the
  result is refused.
* **Reproducible art.** An `ARTWORK_CANDIDATE` must record backend, model
  (name, version, sha256, license, source), workflow (id, version, sha256) and
  settings. Enforced in `check_result()` and by a database check.
* **A sample of test renders cannot pass.** `SAMPLE PASS` requires every
  approved page to be an `ARTWORK_CANDIDATE`, and promotes a new profile
  version (`proven_by` the run). Sample images stay `NON_CANON_SAMPLE`.
* **Canonical production starts deliberately.** Refused unless the profile is
  `PROMOTED` and `creative_readiness` is empty: required sources present,
  season review checklists approved, every overlay insertion placed and
  confirmed.
* **Selective invalidation.** Every page records what it was built from
  (`page_dependency`: materialized page, source documents, character
  references, profile, continuity from earlier approved masters). A refresh
  marks only affected pages `STALE`, with kind, key, old and new version.
  Approved art is kept and never regenerated silently. Pages nothing was drawn
  for simply follow their sources.
* **Restart-safe.** Everything above is in PostgreSQL; attempts are durable
  jobs; images are content-addressed in `generated/`.

## 5. Artwork backends

`PageRenderProvider` is the only thing production calls. Kinds:

* `TEST` — `fake.deterministic-page`: diagrams, always `TEST_RENDER`.
* `COMFY_LOCAL` — a ComfyUI server on this machine (development / fallback).
* `COMFY_REMOTE` — a ComfyUI server elsewhere, e.g. an opportunistic free GPU
  session. It receives **only the page bundle** (the references listed in the
  attempt), never the Vault. Not a guaranteed production dependency.

A backend declares `ArtworkCapabilities`; a page it cannot serve (identity
conditioning, reference count, sibling finishes, layout conditioning, edge
size) blocks the attempt with the exact gap. No paid service is reachable; a
paid backend needs explicit creator approval.

**This machine:** no discrete GPU (15 W mobile CPU, integrated graphics, 15 GB
RAM). Final-quality generation locally is not realistic. The ComfyUI adapter
is implemented (§10) but no GPU endpoint is configured.

## 6. HTTP routes (M3)

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/projects/{id}/production-profiles` | list / create a DRAFT profile version |
| POST | `/projects/{id}/episodes/{ep}/materialize` | materialize a chapter with decisions |
| POST | `/projects/{id}/episodes/{ep}/canonical-readiness` | why canonical start is (not) available |
| GET/POST | `/projects/{id}/production-runs` | list / start a run |
| GET | `/production/runs/{run}` | run, continuity, next page, contact sheet |
| POST | `/production/runs/{run}/refresh` | selective invalidation |
| POST | `/production/runs/{run}/sample-decision` | SAMPLE PASS / FAIL |
| GET | `/production/pages/{page}` | page script, bundle, dependencies, attempts |
| POST | `/production/pages/{page}/attempts` | queue an attempt |
| POST | `/production/page-attempts/{attempt}/review` | review an attempt |
| GET | `/production/backends` | artwork backends and their truthful state |
| POST | `/projects/{id}/episodes/{ep}/sample-runs` | START NON-CANON SAMPLE with a draft profile |
| GET | `/library/characters/{id}/overview` | character overview and readiness |
| GET | `/library/characters/{id}/observations` | browse or rank the corpus |
| POST | `/library/characters/{id}/corpus/refresh` | sync curated references, sweep the catalog |
| POST | `/library/character-observations/{id}/review` | confirm, reject, describe an observation |
| POST | `/library/character-observations/{id}/environment` | use an observed page as an environment reference |
| GET | `/library/character-observations/{id}/image` | observation preview |

Finishes are served by the existing `/production/attempts/{id}/image?kind=`
`COMPOSITION_MASTER | BW_FINISH | COLOR_FINISH`.

## 7. Profile body (convention)

```json
{
  "backend": {"provider_id": "…", "width": 1024, "height": 1456, "settings": {}},
  "reference_policy": {"per_facet": 2},
  "character_rules": {"<name>": {"forbidden_accessories": ["glasses"]}},
  "grammar": {"series": ["<series key>", "…"], "pool": 40, "limit": 6},
  "setting": {"environment_tags": ["forest", "village"]}
}
```

Profiles live in the database (they name library series); they are never
committed.

## 8. Web production loop

| Route | What it is |
|---|---|
| `/projects/{id}/manga/production` | Artwork backends, runs per episode, START NON-CANON SAMPLE (chapter preview, proposed insertion placements, backend), canonical start gated by readiness |
| `/production/runs/{run}` | NON-CANON SAMPLE badge, profile, continuity version, current and next page, contact sheet, refresh sources, SAMPLE PASS / FAIL |
| `/production/runs/{run}/pages/{page}` | Script, dialogue, constraints, lineage, master / B&W / color, attempts with seed and provenance, references by role and authority, grammar, environment, gaps, Generate / Regenerate / Reject / Approve |
| `/library/characters/{id}` | Character overview first: origin, readiness per facet, invariants, forbidden traits, anchors, stylization |
| `/library/characters/{id}/corpus` | Browse or rank observations; confirm, reject, mark atypical, anchor, tag as environment |
| `/settings/diagnostics` | Artwork backends: configured, reachable, checkpoint, identity conditioning, workflow |

The Roughs workspace remains, labelled ADVANCED / OVERRIDE.

## 9. Character reference corpus

A character profile says what a character should look like; the **corpus**
(`character_observation`, Tier B) is the evidence. One observation per
character and locator (`ref:<reference>` or `unit:<catalog unit key>:<page>`),
each with facets (face, hair, body, wardrobe, expression, pose, accessory,
scale), angle, framing, expression, pose, **authority** and **status**:

| Authority | Examples | Grounds production |
|---|---|---|
| PRIMARY_SOURCE | the original manga | yes, once confirmed |
| CREATOR_PRIMARY | the creator's photos of an original character | yes |
| OFFICIAL | anime, official sheets and art | yes, once confirmed |
| PROJECT_CREATED | approved project pages, directional concepts | evidence / stylization only |
| SUPPLEMENTAL | fan art, exploratory derivative work | evidence only, when allowed |
| UNSORTED | not sorted | never |

* **Sources.** Curated references are mirrored as confirmed observations. The
  catalogued source manga is swept for candidate pages (from the chapter of the
  character's first curated appearance). Fan art whose labels name the character
  becomes a supplemental candidate. Creatively approved canonical pages become
  project-created observations; samples, technical passes and rejected attempts
  never do.
* **Candidates never count.** Readiness per facet counts only confirmed,
  high-authority, non-atypical observations: READY needs 3 observations from 2
  independent sources; PARTIAL at least one. An atypical drawing stays evidence.
* **Stylization is not identity.** A reference used as STYLE is project-created
  stylization; it is never an anchor and never grounds identity or body. An
  original character is never grounded in franchise material.
* **Retrieval.** Each page builds a need per character from its script (framing
  and facets from intents, angle/expression/pose words from directions, other
  characters present) and retrieves a small ranked subset (default 6) by
  authority, status, anchor, facet/angle/expression match and co-occurrence,
  preferring diverse sources. Samples may use candidates, flagged as such;
  canonical production does not unless the profile allows it.
* **Invariants.** Declared statements (distinguishing marks, scale, posture)
  shown with their independent support; forbidden traits come from the
  character's notes and become negative prompts.
* **Reviews survive refreshes.** Nothing a person set is overwritten.

No pixels are read to recognise a character; layout hints are labelled hints.

## 10. ComfyUI backend

`comfy.local` / `comfy.remote` are registered only when
`CONTINUUM_COMFY_LOCAL_URL` / `CONTINUUM_COMFY_REMOTE_URL` are set, with the
checkpoint record `CONTINUUM_COMFY_CHECKPOINT`, `_VERSION`, `_SHA256`,
`_LICENSE`, `_SOURCE`. The adapter probes `/object_info` (core nodes, the
checkpoint, IP-Adapter nodes for identity conditioning), uploads only the page's
identity and continuity references, draws the master, draws the color finish
image-to-image over the master at the same size, derives the black-and-white
finish from the master, and records model, workflow and settings. A remote
server refuses source manga excerpts unless
`CONTINUUM_COMFY_REMOTE_ALLOW_SOURCE_EXCERPTS=true`. Proven against a fake
ComfyUI server; no real GPU endpoint has been connected.

## 11. Not done in this pass

* Remote bundle export/import for offline GPU sessions (handoff §T2).
* Grammar layout analysis is cached per API process, not persisted (§T5,
  Priority B); the first page view after a restart is slow.
* Episode package / music / opening-ending skeleton (§T6, Priority C).
* Environment references: the tagging surface exists; nothing is tagged yet.
* Corpus candidates need a person to confirm them (§T7 for later hints).
