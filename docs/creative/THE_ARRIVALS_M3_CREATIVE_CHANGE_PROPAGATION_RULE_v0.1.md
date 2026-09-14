# The Arrivals — M3 Creative Change Propagation Rule v0.1

**Status:** APPROVED WORKFLOW REQUIREMENT  
**Date:** 2026-09-14  
**Project:** The Arrivals  
**Branch:** `creative/s1-season-board-v0.1`

## Principle

A local manga edit must not automatically invalidate or regenerate an entire chapter, episode, or arc. Continuum should classify the semantic scope of the change, preserve unaffected approved work, and propagate only when the edit materially changes later continuity, relationship state, plot information, or canon.

## Example

Original panel/script beat:

> Character A: `I hate you.`

Creator revision:

> Remove the spoken line. Show Character A visibly angry instead.

This may be only a local visual/storytelling refinement if the intended emotional state and downstream relationship meaning are unchanged. In that case, Continuum should update the page/panel recipe and the canonical script representation for that beat, keep downstream pages intact, and mark only nearby dependent assets stale if necessary.

If removing the line changes what Character B knows, whether a relationship rupture occurred, or how later scenes refer back to the confrontation, then the system should raise a propagation warning and identify the affected later scenes/chapters rather than silently rewriting them.

## Required change-scope classes

### 1. Visual-only / presentation change
Examples: expression instead of dialogue, pose, framing, panel composition, camera distance, balloon placement, silence beat.

Default propagation: current panel/page only. No automatic story rewrite.

### 2. Local dialogue / acting refinement
Meaning, intent, and downstream facts remain the same.

Default propagation: current scene/page plus any direct lettering/script artifact. Preserve later chapter/episode work.

### 3. Scene-level semantic change
A fact, intention, emotional outcome, promise, reveal, misunderstanding, or relationship state changes inside the scene.

Default propagation: mark dependent later scenes as `needs continuity review`; do not auto-regenerate the whole episode.

### 4. Episode-level canon change
Changes episode outcome, arrival order, relationship progression, power/canon rule, or setup/payoff chain.

Default propagation: flag affected scenes through the episode and any explicit downstream references in later episodes. Human/assistant review required before regeneration.

### 5. Arc-level / global canon change
Changes a durable story rule, identity, motivation, chronology, worldbuilding fact, or long-running relationship state.

Default propagation: dependency scan across project; generate an impact report before changing approved downstream artifacts.

## Non-destructive versioning

Every accepted change should create a new revision rather than overwrite history. Store:
- previous text/recipe;
- revised text/recipe;
- creator note/reason when available;
- semantic scope classification;
- affected dependency IDs;
- stale/needs-review flags;
- regenerated outputs linked to the revision.

## Human control

Continuum may recommend propagation, but should not silently rewrite approved chapters/arcs from a local creator note. For material semantic changes, show a concise impact summary such as:

`This change affects: current page only`  
`This change may affect: S1E6 scene 8, S1E7 scene 3`  
`No downstream canon dependencies detected`

The creator should be able to choose:
- Apply locally;
- Apply + update direct dependents;
- Open impact review;
- Cancel.

## Relationship to batch manga generation

Batch generation must support selective invalidation. If one page changes, do not discard a whole generated chapter. Re-render only the changed page/panels and any outputs explicitly dependent on them, unless a semantic change requires broader continuity review.

## Production goal

The workflow should allow the creator to make natural manga-direction choices during rough review — including replacing exposition/dialogue with visual acting — without making iteration prohibitively expensive or destabilizing already approved story work.
