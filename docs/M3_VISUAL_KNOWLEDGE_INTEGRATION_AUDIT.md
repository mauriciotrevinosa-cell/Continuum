# M3 — Visual Knowledge / Layered Renderer: Integration Audit

**Branch:** `m3/critical-path` **Audited from:** `f1094aa` (after `git pull --ff-only`)
**Scope:** how the Visual Knowledge package (`docs/creative/visual_knowledge/`) maps onto
the code that already exists, what is really missing, and the smallest vertical slice.

This audit found that most of the new vocabulary already exists in Continuum under another name.
Schema is added only where an existing structure demonstrably cannot hold the fact.

---

## 1. What already solves it (reuse, do not duplicate)

| New concept (docs) | Existing structure | Verdict |
|---|---|---|
| Visual Knowledge **item** | `reference_item`: content-hashed asset, content-derived locator (archive entry / page / video instant), normalized region, class, origin, collection, creator, rights, training eligibility, provenance, `visual_origin` | **Is** the VK item. No new item table. |
| item **functions** (HANDS, LIGHTING, ARCHITECTURE…) | `TechniqueFacet` via `reference_technique` ("a visual-language problem a reference helps solve") | Same concept; 11 buckets were missing, so **extend** the enum (§3). |
| item **descriptors** (shot, angle, cast count, location, mood, tags) | `DescriptorFacet` via `reference_descriptor` with `USER` vs `ANALYSIS` origin, analyzer ref and confidence | Already complete; analyzer output lands here. |
| review UNREVIEWED/USEFUL/PREFERRED/REJECTED | `project_reference_standing` (USEFUL / CANONICAL_FOR_PROJECT / PREFERRED_FOR_CURRENT_LOOK) + soft delete | Reuse. `PREFERRED_FOR_CURRENT_LOOK` is the **House Style exemplar** marker. |
| **House Style** version | committed project document (`THE_ARRIVALS_HOUSE_STYLE_WORKING_vX`) + preferred standings | No table. Lineage records the document id/version/hash. |
| **Scene Treatment** | `visual_mode` + `project_visual_mode_assignment` (scope PANEL/SCENE/SEQUENCE/EPISODE/EVENT, trigger DIRECTORIAL/SCENE_TONE/…) + `reference_technique.visual_mode_id` | Already the right model: scoped, never identity. |
| **Chibi** | `VisualModeCategory.COMEDIC_DEFORMATION` | Already correct. Nothing to build now. |
| allowed uses: training axis | `TrainingEligibility` per item (MANUAL_REVIEW default, APPROVED only by a person, EXCLUDED) | Reuse; the dataset-level ceiling is new (§2). |
| allowed uses: runtime retrieval | `reference_class != UNSORTED` ("a bundle only uses it once someone sorts it") | Reuse as the retrieval gate. |
| reference **roles** in a pack | `BundleRole` (CANON, STYLE, TECHNIQUE, MOOD, GRAMMAR, ENVIRONMENT, WARDROBE, CONTINUITY, SOURCE_PLATE) + `ArtworkReference.teaches/facet` | Keep coarse roles (they govern *how a backend may use* an image); the fine VK role (MATERIAL, CAMERA, ACTION…) is the facet it teaches. |
| identity vs style separation | typed aspects vs facets; comfy never conditions identity on non-CANON or CANDIDATE refs | Holds. |
| rights/provenance snapshot | `attempt_input.provenance` snapshot; `ReferenceManifests` hashes + warnings | Reuse. |
| derived bytes | `DerivedStore` (content-addressed, vault unreachable, idempotent) + `store_bytes` → `gen:sha256:` locators | Reuse for stage outputs, masks, lineart. |
| attempt lineage | `rough_artifact` → `rough_attempt` (recipe, parent, job, state, output class, artwork provenance) → `attempt_input` / `attempt_derivative` / `attempt_review` | Reuse for stages (§4). |
| masks / protected regions / control inputs | recipe intent `operations` (PRESERVE…), `protected_regions`; execution `control_inputs`, `strength`, `inpaint`, `compositing` | Reuse as the freeze vocabulary. |
| page product API | `PageRenderProvider` (Comfy v3 already renders panels one by one, composes deterministically, no whole-page re-diffusion) | Keep. Stages get a **lower-level** boundary beside it (§6). |
| durable execution | `visual.rough_attempt` job (lease, restart-safe, BLOCKED with remediation) | Reuse for stage attempts and page composition. |
| RTL panel geometry | `continuum_imaging.manga.panel_boxes/compose_manga_page` | Reuse for final page composition. |

## 2. What is truly missing

1. **Dataset / external-resource registry.** Nothing records a dataset's license, gated-access
   state, local acceptance, allowed-use ceiling, or which read-only intake root holds its bytes.
   `reference_item.collection` is only a label. → new table `external_resource` (Tier B).
2. **Missing technique facets** for VK functions: ANATOMY, HANDS, CLOTHING, POSE, PERSPECTIVE,
   ARCHITECTURE, MATERIALS, MAGIC_FX, LINEART, COLOR, PROCESS, COMPOSITION, QUIET_ACTING.
3. **Stage identity for an artifact.** `rough_artifact` is unique on
   (project, purpose, run, episode, page, panel, kind); two construction stages of one panel cannot
   coexist, and approval/`SUPERSEDED` are per artifact. → one nullable `stage` column.
4. **An input role for a frozen upstream stage.** `CONTINUITY` means "how the project drew this
   before", not "the structure you may not redraw". → `BundleRole.UPSTREAM_STAGE`.
5. **Role-based retrieval over the catalog** (facets + descriptors + standing + class, with
   rationale and rights warnings). Today: character corpus retrieval, layout-ranked grammar
   pages, and a tag-equality environment lookup.
6. **Stage provider boundary** and a deterministic test implementation.
7. **Analyzer boundary** (`analyze_manga_page → regions`) and a persisted page analysis (this also
   replaces the in-memory grammar layout cache that costs 15–25 s after every API restart).
8. **Process sequences** (linked stages of one artwork). Not needed for CAL-01; deferred.

## 3. Ownership

| Piece | Package |
|---|---|
| `PanelStage`, stage order/contracts, `KnowledgeUse`, VK-function→facet map | `continuum_core.references` / `continuum_core.knowledge` |
| `external_resource` model + migration | `continuum_db` |
| registry import/decisions, role retrieval over references | `continuum_library` (catalog layer) |
| panel contract, stage orchestration, freeze/invalidation, page composition | `continuum_production` |
| `PanelStageProvider`, `MangaPageAnalyzer` protocols + fakes | `continuum_providers` |
| stage/analysis image math (structure-preserving test transforms, RTL order) | `continuum_imaging` |
| rendering | worker `visual.rough_attempt` handler (dispatch by recipe schema) |
| routes / UI | `continuum_api`, `apps/web` |

## 4. Migrations truly required

* `0015` `external_resource` table.
* `0016` technique-facet check constraint extended.
* `0017` `rough_artifact.stage` (+ unique key includes it) and `attempt_input` role `UPSTREAM_STAGE`.
* later: `page_analysis` (persisted analyzer output) — with the analyzer job.

## 5. Durable jobs

* Stage attempts and page composition reuse `visual.rough_attempt` (dispatch on
  `intent.schema`). No new job type is needed for the slice.
* Later: `visual.analyze_pages` (resumable, per-unit, idempotent by content hash + analyzer version).

## 6. Provider boundaries

* `PageRenderProvider` stays the product API for one-shot pages (Comfy v3 panel-first).
* New `PanelStageProvider.render_stage(PanelStageRequest)`: one panel, one declared stage,
  the frozen upstream image, references by role, the stage contract (editable/protected).
  Declares the stages it supports and whether it preserves upstream structure.
* New `MangaPageAnalyzer.analyze_page(bytes) → regions(kind, box, confidence) + analyzer lineage`.
  First implementations: the existing local gutter-cut `analyze_layout` and a synthetic fake.
  YOLO/RT-DETR/segmentation models plug in later without touching production code.

## 7. Stage / freeze / invalidation design

* A panel of a production page has one `rough_artifact` **per stage** (kind `PANEL`, `stage` set).
  Attempts, reviews, derivatives and `SUPERSEDED` stay per artifact, so regenerating LIGHT never
  touches COMPOSITION rows.
* **Freeze = approval** of a stage attempt (`TECHNICAL_PASS` for test renders, `CREATIVE_APPROVE`
  for artwork). A newer approval supersedes the older one.
* A downstream attempt records its frozen upstream as an `UPSTREAM_STAGE` input
  (`gen:sha256:` locator + `{attempt_id, stage}` provenance) and the stage contract in its intent.
* **Invalidation is derived, not stored:** a stage is STALE when its approved attempt's upstream
  input is not the upstream stage's current frozen attempt, or when the panel contract hash
  changed. Changing COMPOSITION stales everything below it; changing LIGHT stales only FINISH.
* Continuum checks every stage result: same geometry as the upstream (hard), plus a recorded
  structure-drift measure (advisory; thresholds need real outputs).
* An artwork stage may not build on a test diagram.
* The final page is a normal **page attempt** composed deterministically from the frozen FINISH
  outputs (no diffusion), so page review, continuity and staleness work unchanged.

## 8. Fit with Attempt / Recipe / Derivative lineage

Stage recipe intent `continuum.panel-stage-recipe/1` = panel contract (+hash), stage contract,
upstream reference, reference pack by role, house-style document, scene treatment. Execution =
provider, seed, size, `control_inputs` (the upstream). The attempt's `parent_attempt_id` keeps
its meaning (previous attempt of the same stage). Output bytes are `OUTPUT` derivatives.

## 9. Smallest vertical slice (CAL-01)

calibration page CAL-01 → panel contract (empty cast, forbidden, required anchors, spatial
authority) → role retrieval (environment / composition / technique / mood / house style) →
COMPOSITION → DRAWING → LINE → VALUE_MATERIAL → LIGHT_SHADOW → FINISH stage attempts
(test backend; each frozen by review) → deterministic page composition → page review, with the
full lineage in the UI. No LoRA, no GPU, no Work.

## 10. Risks

* **Remote providers:** stage packs obey the existing rule; source-excerpt references are refused
  for `COMFY_REMOTE` unless explicitly allowed.
* **Licenses:** registry import never grants `TRAINING_APPROVED`; research-only and non-commercial
  resources are imported without training uses; gated resources start `NOT_REQUESTED`.
* **Git:** registry rows carry URLs and summaries only; an intake root binding is a key
  (`intake:…`), never a path.
* **Serial img2img drift:** mitigated by geometry checks, drift measurement and freeze approvals;
  real protection needs control-net/masked backends (GPU work).

## 11. Where the new docs should change

* `VISUAL_KNOWLEDGE_ITEM_SCHEMA` → map onto `reference_item` + facets + descriptors +
  standing rather than a new item store; `review.status` is project standing.
* "HOUSE_STYLE" / "SCENE_TREATMENT" are not new bundle roles: House Style = preferred
  standing + a versioned document; Scene Treatment = the existing visual-mode assignment.
* `allowed_uses` splits into the per-item training eligibility (exists) and a per-resource
  ceiling (new); `reference_only` = unsorted class.
* The integration map's "one stage = child attempt of the same artifact" option loses:
  approvals and supersession are per artifact, so stages need their own artifacts.
