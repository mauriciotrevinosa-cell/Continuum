# M3 — Visual Knowledge / Layered Construction: Handoff

**Branch:** `m3/critical-path` · **Session start:** `f1094aa` · read with
[M3_VISUAL_KNOWLEDGE_INTEGRATION_AUDIT.md](./M3_VISUAL_KNOWLEDGE_INTEGRATION_AUDIT.md).

## What exists now

| Piece | Where | Notes |
|---|---|---|
| External-resource registry | `continuum_library.resources`, table `external_resource` (0015), `/library/datasets` | Import the committed `docs/creative/visual_knowledge/dataset_registry_v0.1.json` (UI button or `POST /library/external-resources/import`). Import never grants training, never widens a person's decision; the DB refuses training approval without an accepted license and open/granted access. |
| VK functions as technique facets | `TechniqueFacet` (+15, migration 0016), `continuum_core.knowledge.VISUAL_FUNCTION_FACETS` | Every schema function maps to one facet. The web list is type-checked against the API. |
| VK retrieval | `continuum_library.knowledge.VisualKnowledge` | Sorted references only; never character-bound; never from a resource without RETRIEVAL; house style = project `PREFERRED_FOR_CURRENT_LOOK`. |
| Construction stages | `PanelStage`, `rough_artifact.stage`, `BundleRole.UPSTREAM_STAGE` (0017), `continuum_core.knowledge` (order, contracts, facets, `stage_plan`) | |
| Stage provider boundary | `continuum_providers.stages` + `fake.deterministic-stage` | Geometry must match the frozen upstream; artwork needs full provenance. |
| Layered construction service | `continuum_production.layered.PanelConstruction` | Panel contracts, stage packs, freeze = approval, derived invalidation, deterministic page composition. |
| Render paths | `render._render_stage`, `render._compose_page` (same durable job) | Structure drift recorded (advisory). |
| Routes | `GET /production/pages/{id}/construction`, `POST …/construction/{panel}/{stage}/attempts`, `POST /production/stage-attempts/{id}/review` (FREEZE/REJECT/REGENERATE), `POST /production/pages/{id}/compose` | |
| UI | `/production/runs/{run}/pages/{page}/construction` (link "Layered construction" on every page screen) | |
| Comfy stage backend | `ComfyPageProvider.render_stage`, `stage_workflow_manifest` | Init-latent preservation, per-stage denoise; GPU-unvalidated. |
| Analyzer boundary | `continuum_providers.analysis` (`MangaPageAnalyzer`, `local.gutter-layout`), `rtl_reading_order` | |
| Persisted page analysis | table `page_analysis` (0018), `continuum_library.analysis.PageAnalyses` | Grammar candidates read stored analyses: API restart page view 1.6 s (was 12–25 s). |
| Page-analysis job | `visual.analyze_pages` (`continuum_production.analysis_jobs`, worker `handlers/analysis.py`), `GET /library/page-analysis`, `POST /library/page-analysis/jobs`, button on `/library/datasets` | One page per unit, idempotent, resumable. Run on this machine: 594 units, 593 pages over 50 series. |

## Local state (this machine)

* App DB at `0018_vk_page_analysis`; backup before 0017:
  `C:/ContinuumData/backups/continuum-pre-0017-20260919-102446.dump` (0018 only adds a derived table).
* Registry imported (19 resources); `manga109-s-v2026` access = REQUESTED (creator submitted; not granted).
  Nothing allows more than REFERENCE_ONLY until a person decides on `/library/datasets`.
* CAL-01 of calibration run `01a0b218-29f9-76b7-aff4-24e17d358af3`: COMPOSITION frozen (test render),
  DRAWING attempt 1 in review. The page was **not** composed there on purpose: composing adds a page
  attempt, which would displace the Comfy artwork as the page's newest attempt before creator review.
* `rough-completion` no longer 500s on calibration (`7c8f7c9`); construction stages are never listed or
  counted as rough panels.
* Test isolation bug fixed (`ff9691c`): the suite used to write into the app DB. 13 fixture profiles
  created by a test run were soft-retired (`scripts/retire_m3_test_character_pollution.py --apply`);
  leftover `demo-project` production runs/artifacts remain (harmless, other project key) — ask the
  creator before any cleanup.

## W01 / CAL-01 findings (2026-09-19) and fixes

Run `01a0bb60-ee83-758f-915c-e7ac9d251254`, page `01a0bb60-ee9d-75a8-88df-83e85476545c`, attempt
`01a0bb61-3c76-7588-afb7-5d1a8eea0344` (seed 17012026). No GPU pixels were generated.

* The job is BLOCKED because the configured `comfy.remote` tunnel no longer resolves.
* Coarse remote policy (fixed `5675e80`, `14c318e`): one source page in the pack refused the whole
  remote stage. The rule is now per reference (`policy.transmission_refusal`): source excerpts are
  withheld (bytes never read or uploaded), recorded with a reason, and the safe references are used.
* Environment references did not condition (fixed `5675e80`): stages now have a scene lane
  (`stages.scene_references`, Comfy IP-Adapter weight type composition / style and composition /
  style transfer) apart from the per-character identity lanes.
* Applied to the recorded W01 inputs, the new policy gives: send the approved inn image
  `01a0bb5f-8de8-77b6-a7c3-6b21aab59eda` (scene lane, COMPOSITION, weight 0.8); withhold the three
  SOURCE pages.
* To rerun: point `CONTINUUM_COMFY_REMOTE_URL` at a live GPU session, restart API and worker, then
  press Retry on the blocked stage. That re-queues the same attempt.


1. **Comfy stage provider - built, GPU-unvalidated.** `ComfyPageProvider.render_stage`: COMPOSITION
   is the bounded text-to-image panel graph; later stages start from the frozen upstream as the
   initial latent at a per-stage denoise (`STAGE_DENOISE`, 0.22-0.42), forbidden content goes to the
   negative prompt, candidates never condition identity, remote refuses source excerpts, a VAE /8
   rounding is restored and anything larger is refused. Proven only against the fake ComfyUI server.
   Enable per profile with `backend.stage_provider_id = "comfy.remote"` (or `comfy.local`). Next:
   an optional Canny/lineart ControlNet so structure is held by control, not only the init latent.
2. **W01 / CAL-01 on a GPU**: build all six stages with the Comfy stage provider, compose in a
   *separate* run or after the creator has reviewed the whole-page artwork; creator verdict per
   benchmark B01 (`MANGA_RENDERER_BENCHMARK_PLAN_v0.1.md`).
3. **Tag Visual Knowledge**: the real catalog has almost no technique tags (4 TECHNIQUE refs). Stage
   packs are only as good as the tags - tag architecture/materials/lighting/lineart exemplars; mark
   house-style exemplars as "preferred for current look".
4. **Analyzer descriptors on references** - the page-analysis job exists; next, record `ANALYSIS`
   descriptors (PANEL_GEOMETRY, CHARACTER_COUNT) on sorted references so retrieval can use them.
5. **Pretrained analyzers** behind `MangaPageAnalyzer`: `manga-panel-detector-yolo26n` (Apache-2.0,
   Manga109-s terms apply) first, then compare RT-DETR; record `resource_key` so the registry's
   allowed uses gate them (VALIDATOR).
6. **Scene treatment in retrieval**: pass the scope's visual-mode ids (existing
   `project_visual_mode_assignment`) to `VisualKnowledge.retrieve(visual_mode_ids=…)`.
7. **Process sequences** (linked stages of one artwork) - only when process material is imported.
8. Training manifests / LoRA - after benchmarks B01-B05 exist.

## Creator rendering-language locks (2026-09-19)

Production rendering now has two explicit creator-approved interpretation documents:

- `docs/creative/THE_ARRIVALS_VISUAL_RENDERING_LANGUAGE_LOCK_v0.1.md`: B&W always means native manga; color always means colored manga; approved manga/anime references are used only by declared visual function.
- `docs/creative/THE_ARRIVALS_INN_GROUND_FLOOR_SPATIAL_CORRECTION_v0.1.md`: for CAL-02/CAL-03, the fireplace/chimney is directly adjacent to the stair assembly from the entry/common-room view, with no intervening window or full wall bay.

These locks are evaluation requirements. Spatial authority remains the latest measured Spatial Bible/plan, and restricted source excerpts remain subject to the existing transmission policy.

## Invariants kept

Source Vault untouched · no bytes of any dataset or library in Git · no paid service · no training
approval without an accepted license · character identity never from style/technique references ·
diffusion never owns panel count, cast, lettering or page composition · every stage and page has
reproducible lineage (recipe hashes, inputs by role, upstream attempt, provider, seed).
