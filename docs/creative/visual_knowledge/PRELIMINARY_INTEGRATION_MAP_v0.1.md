# Preliminary Integration Map — Visual Knowledge / Layered Renderer v0.1

**Purpose:** reduce Claude's rediscovery work while preserving his requirement to perform a full fresh audit before code changes.

This is a preliminary map from current code inspection, not a substitute for the return audit.

## 1. Reference vocabulary — reuse, do not replace

Existing:
- `ReferenceClass` already separates CANON / TECHNIQUE / CONTINUITY / MOOD.
- `CharacterAspect` already separates face/hair/body/outfit/expression/pose/action/quiet acting.
- `TechniqueFacet` already covers composition, action readability, screentone, atmosphere, cinematography, motion, etc.
- `DescriptorFacet` already supports shot type, camera angle, action intensity, composition, panel geometry, character count and tags.
- `BundleRole` already has CANON / STYLE / TECHNIQUE / MOOD / GRAMMAR / ENVIRONMENT / WARDROBE / CONTINUITY.
- `VisualModeCategory` already includes COMEDIC_DEFORMATION for chibi.

Likely action:
- extend descriptors/facets only where clearly missing;
- do **not** create a second taxonomy that duplicates these enums.

## 2. Rights / training eligibility — already partly solved

`ReferenceManifests` already:
- snapshots provenance;
- reports rights status;
- reports training eligibility warnings;
- hashes deterministic manifests.

Likely action:
- external dataset registry should feed this system;
- dataset-level license/acceptance should not bypass per-reference training eligibility.

## 3. Masks / edit operations — useful foundation for layering

Existing rough recipe/provider request already supports:
- source plate;
- mask;
- operations;
- placements;
- strength;
- inpaint;
- control inputs;
- compositing.

Likely action:
- layered construction should reuse this vocabulary for editable/protected regions rather than invent a separate mask engine.

## 4. Derived artifact storage — already strong

`DerivedStore` already provides:
- content-addressed writes;
- atomic landing;
- Source Vault cannot be writable by construction;
- idempotent repeated writes.

`AttemptDerivative` already stores:
- derivative kind;
- content hash;
- size/mime;
- detail JSON.

Open design question:
- are stage outputs best represented by:
  1. new derivative kinds + detail metadata;
  2. a generic stage-artifact row;
  3. child attempts linked by parent_attempt_id;
  4. a combination?

Do not decide without reviewing existing review/invalidation behavior.

## 5. Attempt lineage — likely reusable

`RoughAttempt` already has:
- recipe id;
- parent attempt;
- production page;
- continuity state;
- profile;
- provenance;
- review state.

This may already be close to a layered-stage graph.

Potential approach:
- one stage = one child attempt with explicit stage in recipe/provenance;
- approved stage artifact becomes an input to the next stage.

Potential problem:
- current state constraints assume one generated output per attempt and may not express stage-specific approvals cleanly.

Claude should compare this with adding a dedicated `PanelStageAttempt` model before migrating.

## 6. Current production rendering boundary

`PageRenderProvider` still presents a **page-level** protocol externally.

However, current `ComfyPageProvider` v3 already contains panel-first logic and deterministic page composition.

This is an important distinction:

> page-level product API does not mean whole-page diffusion.

The provider can remain page-level if internally it:
- renders bounded panels separately;
- composes them deterministically;
- returns one master + sibling finishes.

Layered work therefore does not automatically require deleting `PageRenderProvider`.

Possible future refinement:
- add a lower-level `PanelStageProvider` used by `ComfyPageProvider`, while keeping page production semantics stable.

## 7. Current Comfy behavior

Already present:
- tag compiler for Animagine;
- bounded panel prompts;
- no-text negative prompting;
- deterministic identity-reference budget;
- per-character grouping/ranking;
- deterministic panel composition;
- single master with B&W/color siblings;
- checkpoint/workflow provenance.

Important gap:
- current Comfy capability reports `layout_conditioning=False`;
- layered freeze/regeneration will need explicit preserved-layout/control support.

## 8. Color pass caution

Current architecture already says no whole-page re-diffusion.

Any existing color graph or legacy page pass must be checked against that rule.

The desired direction is:
- render/modify at panel/stage scope;
- compose deterministically;
- derive finishes without allowing a late pass to mutate identity/layout.

Claude should verify actual v3 execution before changing it.

## 9. Analyzer providers

Ready-made manga detectors should fit as analyzer/provider boundaries, not domain logic.

Candidate abstract result:

```
MangaPageAnalysis:
  regions:
    - kind: PANEL | TEXT | FACE | BODY | CHARACTER | BALLOON
      box/mask
      confidence
  analyzer:
    id
    version
    model_hash
```

Then:
- order estimator consumes panel boxes;
- importer stores derived descriptors;
- renderer remains independent of detector implementation.

## 10. Dataset registry ownership

Likely ownership:
- dataset metadata / source indexing: library/catalog layer;
- training eligibility / reference use: core/reference vocabulary;
- project-specific standing: existing project reference standing;
- derivative materialization: storage/generated;
- trained models: models root + provider/model registry.

Avoid putting external dataset logic inside `continuum_production` unless it is specifically materializing a production/training manifest.

## 11. Smallest likely migration set

Potentially:
- dataset/source registry table;
- visual knowledge item or extension to existing ReferenceItem;
- optional stage metadata/model.

But the current reference system is already broad enough that `Visual Knowledge item` may simply be a ReferenceItem + descriptors + provenance + dataset source relation.

Claude should prove a new table is necessary before adding one.

## 12. Best vertical slice

CAL-01 remains the best first target because:
- no character identity;
- no wardrobe;
- no acting;
- no text;
- strong spatial authority exists;
- visual references can focus on environment/composition/material/atmosphere;
- panel detector/reading-order tools are irrelevant to generation itself, so the render path is isolated.

The first slice should prove:
1. retrieval;
2. stage artifact;
3. freeze/review;
4. next-stage input;
5. final panel/page artifact;
6. lineage.

No LoRA training required.
