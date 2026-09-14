# The Arrivals — Post-Panelization Editorial Overview Rule v0.1

**Status:** AUTHORITATIVE WORKFLOW ADDENDUM  
**Date:** 2026-09-14  
**Project:** `The Arrivals`  
**Branch:** `creative/s1-season-board-v0.1`

## Purpose

After an episode receives human `GREEN LIGHT`, the assistant completes the full detailed episode and manga panelization / production QC without requiring page-by-page human review.

Once the manga panel script exists, the assistant must return a compact editorial overview before rough manga generation.

## Required overview

For every episode after Stage 4, provide:

- total provisional manga page count;
- the natural dramatic / editorial cut points, if any;
- the number of manga chapters that emerge organically from those cuts;
- a recommendation to keep the material as one chapter or divide it into multiple chapters;
- approximate page ranges per recommended chapter;
- one short pacing note explaining why that structure is preferred.

## Editorial principle

Use S1E1 `Not This Time` as the reference model.

Do **not** force chapter lengths to match a fixed quota.

The workflow is:

```text
approved story
→ manga panelization
→ total provisional page count
→ identify natural dramatic cuts
→ recommend chapter structure
```

Not:

```text
choose a target chapter length
→ force the story to fit it
```

Unequal chapter lengths are allowed when the story supports them.

If an episode has no meaningful natural cut, recommend one longer chapter rather than inserting an arbitrary break.

If the episode contains strong natural transitions, recommend multiple chapters and show the approximate page ranges.

## Human involvement

The human does **not** need to review the panel script page by page at this stage.

The human only receives the editorial summary so they can understand:

- how long the episode became;
- where it naturally divides;
- whether the proposed chapter structure feels right.

The next major human checkpoint remains Stage 5: Rough Manga Review.

## Example format

```text
S1E2 — 46 provisional pages

Natural cut 1: arrival at the settlement
Natural cut 2: night / Bocchi scream

Recommendation: 2 chapters
- Chapter A: pp. 1–24
- Chapter B: pp. 25–46

Pacing note: the settlement discovery creates a clean structural turn; the night sequence works better as the second movement rather than forcing a mid-scene page quota.
```

If no natural split exists:

```text
Recommendation: 1 long chapter
Reason: the episode plays as one continuous emotional / dramatic unit and an artificial break would weaken momentum.
```

## Status / UI implication

This editorial overview is part of the Stage 4 handoff and may be shown in the `The Arrivals` production UI alongside:

- provisional page count;
- recommended chapter count;
- chapter ranges;
- panel-script readiness;
- rough-generation status.

This addendum supplements `THE_ARRIVALS_PRODUCTION_PIPELINE_AND_GIT_RULES_v0.1.md` and should be treated as part of the standing manga-first workflow.