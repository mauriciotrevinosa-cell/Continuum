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

## Local state (this machine)

* App DB at `0018_vk_page_analysis`; backup before 0017:
  `C:/ContinuumData/backups/continuum-pre-0017-20260919-102446.dump` (0018 only adds a derived table).
* Registry imported (19 resources); `manga109-s-v2026` access = REQUESTED (creator submitted; not granted).
  Nothing allows more than REFERENCE_ONLY until a person decides on `/library/datasets`.
* CAL-01 of calibration run `01a0b218-29f9-76b7-aff4-24e17d358af3`: COMPOSITION frozen (test render),
  DRAWING attempt 1 in review. The page was **not** composed there on purpose: composing adds a page
  attempt, which would displace the Comfy artwork as the page's newest attempt before creator review.
* Test isolation bug fixed (`ff9691c`): the suite used to write into the app DB. 13 fixture profiles
  created by a test run were soft-retired (`scripts/retire_m3_test_character_pollution.py --apply`);
  leftover `demo-project` production runs/artifacts remain (harmless, other project key) — ask the
  creator before any cleanup.

## Not done / next tasks (in order)

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
4. **Analyzer indexing job** (`visual.analyze_pages`): pre-analyse a series or intake root with any
   analyzer, record `ANALYSIS` descriptors (PANEL_GEOMETRY, CHARACTER_COUNT) on references.
5. **Pretrained analyzers** behind `MangaPageAnalyzer`: `manga-panel-detector-yolo26n` (Apache-2.0,
   Manga109-s terms apply) first, then compare RT-DETR; record `resource_key` so the registry's
   allowed uses gate them (VALIDATOR).
6. **Scene treatment in retrieval**: pass the scope's visual-mode ids (existing
   `project_visual_mode_assignment`) to `VisualKnowledge.retrieve(visual_mode_ids=…)`.
7. **Process sequences** (linked stages of one artwork) - only when process material is imported.
8. Training manifests / LoRA - after benchmarks B01-B05 exist.

## Invariants kept

Source Vault untouched · no bytes of any dataset or library in Git · no paid service · no training
approval without an accepted license · character identity never from style/technique references ·
diffusion never owns panel count, cast, lettering or page composition · every stage and page has
reproducible lineage (recipe hashes, inputs by role, upstream attempt, provider, seed).
