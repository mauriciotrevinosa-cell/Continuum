# Manga Renderer Benchmark Plan v0.1

**Purpose:** prevent model/dataset changes from being judged only by vibes.

The first suite should stay small enough to rerun frequently.


## Creator-locked rendering semantics

All benchmarks follow
[`THE_ARRIVALS_VISUAL_RENDERING_LANGUAGE_LOCK_v0.1.md`](../THE_ARRIVALS_VISUAL_RENDERING_LANGUAGE_LOCK_v0.1.md).

- `B&W` means native manga construction: ink hierarchy, spot blacks, clean whites, screentone and selective hatching. A grayscale, desaturated, photographic, charcoal or engraving result is a **style failure**.
- `Color` means colored manga: preserve the authoritative ink drawing and apply restrained flat/cel-shaded color beneath it. A painterly replacement of the line-art hierarchy is a **style failure**.
- Approved manga/anime references are selected by visual function. They never supply character identity, wardrobe, canon geometry or invented content.
- Spatial locks outrank style references and generated candidates.

For CAL-02 / CAL-03, also apply
[`THE_ARRIVALS_INN_GROUND_FLOOR_SPATIAL_CORRECTION_v0.1.md`](../THE_ARRIVALS_INN_GROUND_FLOOR_SPATIAL_CORRECTION_v0.1.md):
the fireplace/chimney and stair read as a directly adjacent cluster, with no window or full wall bay between them.

## B01 — Environment / CAL-01

Target:
abandoned settlement, no characters.

Tests:
- canonical geography;
- forest enclosure;
- inn dominance;
- well/cultivation placement;
- hill/tree;
- old routes;
- material detail;
- no invented population/text.

Why first:
isolates environment, perspective, composition and House Style without identity problems.

## B02 — Simple single character

A quiet, non-action medium shot with one core character.

Tests:
- identity;
- face;
- hands;
- wardrobe;
- no pseudo-text;
- stable proportions.

## B03 — Two-person quiet acting

Use a restrained Mau/Frieren interaction that is **not** the full revival climax.

Tests:
- two identities;
- shared eyeline;
- touch/contact;
- subtle expression;
- no identity blending.

## B04 — Household / CAL-04

G1 calm-home baseline.

Tests:
- multiple identities at different depths;
- perspective scale;
- ordinary body language;
- environment continuity;
- no hero-lineup composition.

## B05 — G2 group reaction / CAL-05

Tests:
- four faces;
- distinct silhouettes;
- shared eyeline;
- group staging;
- no duplicated identity.

## B06 — Nine-person table / CAL-07

Tests:
- exact cast count;
- no extras;
- room continuity;
- character separation;
- readable ensemble composition.

This can be deferred until B01–B05 pass.

## B07 — Action anatomy

A two-character combat beat before Hollow Purple.

Tests:
- limbs;
- contact;
- foreshortening;
- action causality;
- readable attacker/defender.

## B08 — Magic / FX

Single or two-person magic panel.

Tests:
- effect attached to correct source;
- hands remain valid;
- FX does not replace anatomy;
- environment illumination coherent.

## B09 — CAL-18 revival/intimacy

Tests:
- Mau/Frieren identity;
- Frieren just waking;
- Mau already looking at her / gentle head contact;
- hoodie continuity if used;
- restrained acting before emotional release;
- no speech balloons / pseudo-text.

Run only after B03 passes.

## B10 — CAL-17 Hollow Purple stress test

Last, expensive stress test.

Tests:
- cast exactness;
- Sukuna arm/hand physically through Mau;
- Red/Blue causality;
- barrier geography;
- Mahoraga;
- extraction roles;
- no severed-hand misconception;
- no random extra character;
- action readability.

CAL-17 remains a calibration compression; eventual canon can use multiple pages.

## Metrics

### Human creator verdict
For every benchmark:
- PASS
- PROMISING / revise
- FAIL

Reasons tagged:
- identity;
- anatomy;
- hands;
- cast;
- acting;
- camera;
- environment;
- wardrobe;
- composition;
- action readability;
- FX;
- style;
- pseudo-text;
- continuity.

### Automated checks where feasible
- output dimensions;
- number of detected subjects;
- face count;
- text-region detection;
- pose plausibility;
- panel bounds;
- expected artifact lineage;
- deterministic seed/config persistence.

Automated validators do not override creator judgment; they catch obvious regressions.

## Promotion gate

A new checkpoint / LoRA / retrieval strategy / layered workflow does not become production default because of one beautiful image.

Promote only when:
- B01–B05 are no worse than current baseline;
- target problem improves;
- provenance is complete;
- failure modes are understood.

B09/B10 are higher-difficulty gates later.
