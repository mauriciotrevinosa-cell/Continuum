# Claude Return Handoff — Visual Knowledge / Manga Renderer v0.1

## Mandatory first action

Before reading, auditing or editing:

```bash
git status
git switch m3/critical-path
git pull --ff-only origin m3/critical-path
git rev-parse HEAD
```

If the working tree is dirty, do **not** destroy local work. Report it and resolve intentionally.

Do not trust a SHA copied into an old prompt. The branch HEAD after `git pull` is the starting point.

## First assignment: understand Continuum as a whole

Do not begin by editing the manga renderer.

Perform a project-wide reconnaissance first:
- repository topology;
- ADRs / invariants;
- config roots;
- Source Vault read-only boundary;
- library/catalog/reference system;
- durable jobs/leases;
- DB models/migrations;
- API;
- web UI;
- providers;
- production recipes/manifests;
- generated artifact lineage;
- Comfy local/remote integration;
- tests;
- The Arrivals creative/production documents.

The goal is to know where the new work belongs **without creating a parallel subsystem**.

## Required reading

### Project / architecture
- `docs/FOUNDATION_APPROVAL.md`
- `docs/ARCHITECTURE_REVIEW.md`
- `docs/PHASE_1_M1_M2_IMPLEMENTATION_REPORT.md`
- `docs/M3_MANGA_PRODUCTION.md`
- `docs/M3_CHARACTER_FOUNDATION_HANDOFF.md`
- `docs/M3_WARDROBE_AND_LORA_STRATEGY.md`

### Current production code
- `packages/core/src/continuum_core/references.py`
- `packages/production/src/continuum_production/recipe.py`
- `packages/production/src/continuum_production/manifest.py`
- `packages/production/src/continuum_production/render.py`
- `packages/providers/src/continuum_providers/contracts.py`
- `packages/providers/src/continuum_providers/comfy.py`
- `packages/storage/src/continuum_storage/derived.py`
- `packages/library/src/continuum_library/`
- `packages/db/src/continuum_db/models/`
- `workers/runner/src/continuum_worker/`
- `apps/api/src/continuum_api/routers/production.py`
- `apps/web/app/production/`

### The Arrivals / recent context
- `docs/creative/the_arrivals_story_board/README.md`
- `docs/creative/the_arrivals_story_board/INDEX.md`
- `docs/creative/THE_ARRIVALS_MANGA_RENDERER_ARCHITECTURE_v0.1.md`
- `docs/creative/THE_ARRIVALS_S1_PRODUCTION_CALIBRATION_CHAPTER_v0.1.md`
- `docs/creative/THE_ARRIVALS_ABANDONED_VILLAGE_AND_INN_SPATIAL_BIBLE_v0.2.md`
- `docs/creative/THE_ARRIVALS_SCENE1_STYLE_SYNTHESIS_WORKING_NOTES_v0.1.md`

### New visual-knowledge package
- `docs/creative/visual_knowledge/README.md`
- `VISUAL_KNOWLEDGE_LAYERED_RENDERER_ARCHITECTURE_v0.1.md`
- `THE_ARRIVALS_HOUSE_STYLE_WORKING_v0.1.md`
- `VISUAL_KNOWLEDGE_ITEM_SCHEMA_v0.1.json`
- `EXTERNAL_DATASET_AUDIT_v0.1.md`
- `dataset_registry_v0.1.json`
- `IMPLEMENTATION_BACKLOG_v0.1.md`
- `MANGA_RENDERER_BENCHMARK_PLAN_v0.1.md`

## What changed while you were away

1. **The Arrivals story corpus was consolidated.**
   - Story Board now contains navigable S1/S2/arcs/decision history.
   - S1 has 19 manga-ready episodes.
   - Do not reconstruct story state from stale branch summaries.

2. **Whole-page diffusion is no longer the architecture.**
   - Continuum owns panel count/order/cast/layout/lettering.
   - Renderer receives one bounded panel problem.
   - Final page is composed deterministically.

3. **CAL-17 and CAL-18 exposed failure modes.**
   - identity drift;
   - action causality;
   - extra subjects;
   - pseudo-text;
   - wardrobe;
   - subtle acting;
   - over-compression.

4. **Visual Knowledge is now separate from House Style.**
   - Visual Knowledge = how to solve a visual problem.
   - House Style = default project language.
   - Scene Treatment = temporary deliberate override.
   - Training eligibility is separate from runtime reference usefulness.

5. **Layered construction is a desired extension.**
   - composition → drawing → line → value/material → light/shadow → FX → environment integration → finish → lettering.
   - Approved upstream structure should be frozen.
   - Avoid serial unrestricted img2img that redraws identity.

6. **House Style is evolving.**
   - Witch Hat Atelier / Call of the Night / Frieren / Dandadan are discovery references, not fixed weights.
   - new art/manga/fan-art references can improve the style.
   - special scenes may use oil-paint/watercolor/glitch/etc. treatments intentionally.

7. **Chibi is preserved but not urgent.**
   - existing `COMEDIC_DEFORMATION` concept is the correct direction;
   - chibi is a visual mode, not a new identity.

8. **External datasets were audited before building everything ourselves.**
   - Manga109-s is the first dataset to evaluate;
   - public Manga109 annotations and panel-order tool are valuable;
   - DiffSensei/MangaZero are strong research references with image-rights caveats;
   - MAGI is research-only;
   - Anime2Sketch is a lineart preprocessing candidate.

## Your first deliverable — NO CODE YET

After reconnaissance, produce a short integration audit answering:

1. Which existing types/tables/services already cover each new concept?
2. What is truly missing?
3. Which package should own each missing concept?
4. What migrations would be required?
5. What durable jobs are needed?
6. What provider boundaries are needed?
7. How should stage invalidation integrate with existing recipe/attempt lineage?
8. What is the smallest vertical slice that proves the architecture?
9. Which proposal in the new docs should be changed because existing code already solves it better?
10. Any security/storage/license risks.

Do not start a broad rewrite before this audit is reviewed.

## After approval — implementation target

Implement the smallest vertical slice:

**CAL-01 environment-only**

Goal:
calibration beat
→ visual knowledge retrieval
→ reference pack
→ one or more explicit render stages
→ artifact lineage
→ review in Continuum.

Training a LoRA is **not** required for the first slice.

## Non-negotiable invariants

- Source Vault remains read-only.
- User private photos / commercial manga / fan-art corpora never go to public Git.
- Unknown rights never silently become training-approved.
- Character identity and wardrobe remain separate.
- Chibi never contaminates normal identity.
- A model/provider is replaceable.
- Diffusion never owns page semantics or lettering.
- Every generated artifact has reproducible lineage.
- Use small auditable commits.
