# The Arrivals — M3 Batch Manga Orchestration Requirement

**Date:** 2026-09-14  
**Project:** The Arrivals  
**Branch:** `creative/s1-season-board-v0.1`

## Why this is required

The current M2 Roughs workspace proves that Continuum can preserve a manual attempt recipe, source plate, reference bundle, seed, attempt history, review controls, and approval state. That workspace is useful as an inspector / exception-handling surface.

It is **not** viable as the primary production workflow for the real manga.

The current Level 4 page counts through S1E12 are already approximately:

- E1: 79
- E2: 46
- E3: 58
- E4: 52
- E5: 48
- E6: 64
- E7: 66
- E8: 70
- E9: 50
- E10: 68
- E11: 72
- E12: 68

Total through E12: **~741 provisional manga pages**, before E13–E19 are panelized.

Requiring the creator to manually choose mode, source plate, references, characters, brief, and seed page by page would make production impractical.

## M3 production requirement

M3 must treat the approved episode/chapter package as the production input and automatically build the per-page/per-panel work items.

### 1. Chapter / episode batch start

From an approved panel script or chapter package, provide an explicit action such as:

- `Start chapter package`
- `Generate chapter roughs`
- `Create production batch`

The creator should not have to create hundreds of rough jobs manually.

### 2. Automatic recipe construction

For each page/panel, Continuum should derive as much as possible from the panel script and project manifests:

- episode / chapter / page / panel identity;
- scene and narrative purpose;
- who appears;
- location / environment;
- dialogue and acting intent;
- generation mode (`new generation`, `source-derived edit`, `composite`, `layout only`) based on the task;
- style/mode target;
- required character manifests;
- source plates when appropriate;
- continuity references from adjacent pages / approved prior pages;
- default brief;
- seed/settings when the model supports them.

The creator can override these, but should not have to enter them from scratch.

### 3. Multi-reference manifest resolution

Per-page generation should automatically resolve multiple useful references from character / style / scene manifests rather than using one manually clicked image as the character definition.

Example reference roles:

- identity / face;
- body proportions / pose;
- wardrobe;
- expression / acting;
- accessory;
- canonical manga source;
- anime reference;
- approved fan art / supplemental reference;
- environment / scene source;
- continuity anchor from previously approved project work.

Every attempt must persist the exact refs actually used.

### 4. Batch generation with review queue

The normal flow should be:

`panel script -> chapter package -> auto recipes/ref bundles -> batch rough generation -> review queue`

The creator reviews outputs rather than authoring every recipe manually.

Useful review surfaces:

- page contact sheet / chapter grid;
- flagged failures / low-confidence items first;
- per-page drill-down into the existing Rough workspace;
- regenerate one panel/page without regenerating the whole chapter;
- compare attempts side by side;
- bulk accept only when explicitly chosen by the creator.

### 5. Manual Rough workspace remains important

Do **not** remove the current detailed Rough workspace. It is valuable for:

- difficult hero panels;
- targeted source-derived edits;
- continuity fixes;
- manual reference overrides;
- local masking / replacement;
- regeneration with a chosen seed;
- review notes;
- inspecting provenance / exact recipe.

It should become the **advanced override / exception editor**, not the required authoring path for every page.

### 6. Approval semantics

M2 deterministic-sketch approvals are workflow test approvals only and must not count as creative manga approval.

Recommended distinction:

- `Technical Pass / Test Only`
- `Generated`
- `Needs Review`
- `Creative Approved`
- `Final Approved`

Only real creator-reviewed manga roughs may become `Creative Approved`.

### 7. Production UX target

The intended user experience for a large chapter is roughly:

1. open approved episode / chapter;
2. click `Start chapter package`;
3. inspect auto-resolved cast / reference manifests / style / page count;
4. launch rough batch;
5. review a contact sheet and flagged pages;
6. drill into individual pages only where necessary;
7. regenerate / override locally;
8. approve chapter rough when ready.

The system should optimize for **human review of generated work**, not **human data entry for hundreds of pages**.

## Decision

**Batch/chapter orchestration is a first-order M3 requirement, not a later convenience feature.**

The Arrivals already has ~741 provisional pages through E12, and the full S1 total will be larger once E13–E19 reach Level 4. Production must therefore scale from the panel script / chapter package rather than from one manually configured rough at a time.
