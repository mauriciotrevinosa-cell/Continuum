# The Arrivals — Light Novel Parallel Path v0.1

**Status:** PROVISIONAL / DEFERRED DECISION — DO NOT START YET  
**Date:** 2026-09-26  
**Project:** `The Arrivals`  
**Decision checkpoint:** after the next manga-generation attempts (planned for 2026-09-27)

## 1. Current decision

**Manga remains the primary desired format for The Arrivals.**

The Light Novel path is **not** a replacement for manga and is not evidence that the manga effort has been abandoned.

After the next manga-generation attempts, decide whether to activate a parallel Light Novel production path so the already-developed story can be read and enjoyed while manga production continues to mature.

Intended relationship:

```text
shared Story Canon
├── Light Novel adaptation / reading manuscript
└── Manga adaptation / visual production
    └── future anime / animation adaptation
```

The manga is not required to reproduce Light Novel prose literally. Both adaptations preserve the same approved story, while each medium may communicate the same beat differently.

## 2. Why this path may be useful

The story is already large and valuable independently of the current visual-generation bottleneck.

A Light Novel adaptation can preserve and expose material that is especially natural in prose:

- internal POV;
- micro-conversations;
- quiet relationship development;
- ordinary cohabitation and routines;
- transitions between major beats;
- atmosphere and setting;
- thoughts that manga may later communicate visually instead of as text.

Length is **not** a quota. Hundreds or thousands of manuscript pages are acceptable if the story naturally requires them.

## 3. What should happen if the path is activated

### First target: Season 1

Use the current authoritative Season 1 corpus as the source:

- approved story/scene material;
- integrated cinematic revision overlay;
- Level-4 manga scripts;
- applicable later corrections and addenda.

Create a versioned manuscript such as:

```text
The Arrivals — Light Novel
  Season / Volume 1
    Episode 01 / natural chapter divisions
    Episode 02
    ...
    Episode 19
```

Initial manuscript status should be something like:

`S1 LN Manuscript v0.1 — based on current Level-4 corpus`

It must **not** be called final before the planned Season 1 story/pacing audit.

When the S1 audit later adds, expands, removes, or revises material, update the affected LN sections rather than regenerating or discarding the entire manuscript.

## 4. S1 audit relationship

The Light Novel path must remain compatible with the planned S1 audit.

The audit should specifically inspect:

- macro pacing;
- "life between the beats";
- micro-conversations and callbacks;
- Frieren/Mau intimacy accumulation;
- ordinary routines and cohabitation;
- relationships between characters when the main plot is not advancing;
- whether scenes feel like people living in a world rather than characters waiting for plot beats;
- whether any currently compressed material needs more room.

A pre-audit LN may be useful as a readable version of the current story, but it remains revisionable.

## 5. Continuum implementation direction

Continuum does **not** currently have an explicit Light Novel production route.

The existing The Arrivals pipeline already contains a useful conceptual precursor:

`Stage 3 — Full Episode Construction`

which expands approved structure into continuous story/scene prose.

If the LN path is activated, Continuum should generalize this into a durable, versioned text-artifact workflow rather than creating a one-off exporter.

Minimum desired behavior:

1. Select an approved project story revision / episode as input.
2. Resolve the authoritative source layers and applicable corrections.
3. Generate prose using a versioned LN style/adapter recipe.
4. Record provenance:
   - project/story revision;
   - input documents;
   - model/provider;
   - prompt/recipe version;
   - parent manuscript version;
   - generation timestamp.
5. Preserve character voice and continuity.
6. Never silently invent a consequential missing story decision.
7. If a required story decision is genuinely unresolved, surface a blocker such as `STORY_DECISION_REQUIRED` rather than filling it invisibly.
8. Allow human approval/edit/revision.
9. Support statuses such as:
   - `draft`
   - `review`
   - `approved`
   - `superseded`
10. Allow compilation/export of approved chapters into a readable manuscript.

The implementation should reuse Continuum's existing project-continuity, provider, versioning, provenance and durable-job principles rather than creating a separate ad-hoc subsystem.

## 6. Recommended development sequence if activated

Do **not** begin by building a large generic novel generator.

Recommended order:

1. Produce a small number of The Arrivals LN chapters manually/assistant-led from approved material.
2. Use them to establish the desired prose voice, density, POV rules and chapter structure.
3. Treat those approved chapters as the gold-standard adaptation reference.
4. Encode that standard into Continuum's LN adapter / recipe.
5. Let Continuum perform the repeatable mechanical conversion for later approved material.
6. Keep manga production active in parallel.

This follows the project principle:

> first establish the desired creative product, then automate the repeatable production of that product.

## 7. Explicit non-decisions

As of this document:

- do **not** begin S1 Light Novel generation yet;
- do **not** deprioritize manga;
- do **not** change S1 canon because prose makes a different choice convenient;
- do **not** treat LN prose as automatically more authoritative than shared Story Canon;
- do **not** implement the Continuum LN pipeline before the post-manga-attempt checkpoint unless separately requested.

## 8. Next checkpoint

After the 2026-09-27 manga-generation attempts, decide one of:

### A. Manga pipeline is sufficiently promising
Continue manga-first production. LN can remain deferred or begin later as a parallel reading edition.

### B. Manga remains materially blocked
Activate the Light Novel parallel path while continuing root-cause work on manga. Begin by novelizing the current approved S1 corpus, then use the approved prose output to define Continuum's reusable LN production route.

In both cases:

> **The Arrivals remains manga-first in creative intent. The LN path exists so the story itself is never blocked by visual-production infrastructure.**
