# The Arrivals — Incremental Manga-to-Anime Production Pipeline v0.1

Status: PROVISIONAL ARCHITECTURE SEED — creator-approved direction, not an M3 blocker.

## Purpose

Continuum should eventually operate as a production studio with two overlapping pipelines:

1. The official manga continues generating and entering creator review.
2. Each manga episode that becomes approved/locked becomes eligible to start anime adaptation automatically.

The anime pipeline must reuse Continuum's existing source of truth rather than reconstructing characters, wardrobe, environments, continuity, or story semantics from scratch.

## Core production rule

Anime production is episode-driven, but change propagation is section/shot-driven.

Approving or upgrading part of an already-adapted manga episode MUST NOT force a complete anime episode regeneration by default. Continuum should determine which anime scenes/shots depend on the changed manga source and invalidate or rebuild only the affected region.

Example:

Manga E1 approved v1 -> Anime E1 source snapshot v1 -> scenes/shots -> Anime E1 candidate v1.

Later:

Manga E1 approved v2 changes only pages 42-45.

Continuum performs dependency/impact analysis, identifies the anime scene and shots derived from pages 42-45, creates replacement candidates only for those affected shots, and preserves all unaffected approved shots.

The previous anime version remains immutable and inspectable in lineage/history.

## Manga-to-anime source snapshot

When a complete manga episode is creator-approved/locked, Continuum should create an immutable anime source snapshot containing at minimum:

- episode/script version and source locators;
- approved manga page/version IDs;
- character Production Models used;
- wardrobe stage/set per character;
- environment anchors;
- continuity references;
- acting/staging/page semantics where applicable;
- render/reference provenance;
- creator approval state.

This snapshot is the reproducible source for that anime adaptation version.

## Parallel pipeline

Continuum should not wait for the full manga season to finish before beginning anime work.

While Manga E2/E3/E4 continue generating, Anime E1 can be in preproduction or shot generation once Manga E1 is locked.

Conceptually:

Manga E1 APPROVED -> Anime E1 production
Manga E2 final review -> Anime E2 preproduction may prepare
Manga E3 generating
Manga E4 generating

The two pipelines should be able to progress independently while sharing the same project truth.

## Preproduction vs expensive rendering

Page approvals may progressively prepare low-cost anime preproduction artifacts such as:

- adaptation breakdown;
- scene grouping;
- shot list;
- storyboard plan;
- animatic timing;
- dialogue timing;
- camera/motion intent;
- asset requirements;
- continuity dependencies.

Final/expensive video generation should normally wait until the complete source episode is approved/locked, avoiding unnecessary GPU spend caused by late manga changes.

## Dependency graph / impact analysis

Anime artifacts should record explicit dependencies back to manga/story sources.

A shot may depend on:

- source episode/scene/page/panel IDs;
- script beat IDs;
- character Production Model versions;
- wardrobe set/stage;
- environment version;
- approved manga appearance/acting/grammar refs;
- prior anime shot continuity;
- audio/dialogue source.

When one dependency changes, Continuum should mark only downstream affected artifacts stale or needing review.

A manga update must therefore produce an impact report before regeneration, for example:

- unchanged shots: preserve;
- visually dependent shots: candidate upgrade/regenerate;
- continuity-adjacent shots: review required;
- unrelated scenes: untouched.

## Immutable lineage

The anime pipeline follows the same core philosophy as manga Upgrade Quality / Regenerate:

approved v1 -> new affected candidate(s) -> approved v2

Previously approved shots/episodes are never overwritten or deleted. They remain available as previously-approved/superseded history with complete provenance.

## Upgrade Quality vs Regenerate

Upgrade Quality:
- story semantics and blocking remain correct;
- preserve acting, cast, wardrobe, staging, camera intent, timing, and continuity as far as possible;
- improve fidelity, temporal consistency, cleanup, resolution, motion, audio, or final quality;
- create child versions rather than overwriting parents.

Regenerate:
- semantic or visual result is wrong;
- wrong character, wardrobe, staging, motion, expression, prop, environment, camera interpretation, timing, continuity, or artifact;
- create a new candidate while retaining previous history.

## Human authority

Creator approval remains authoritative.

Continuum may prepare, render, compare, detect impact, and recommend which artifacts require review, but it must not silently approve canon manga or anime output on behalf of the creator.

## Relationship to current M3 work

This architecture is intentionally future-facing and MUST NOT interrupt the current M3 critical path, S1 Production Calibration Chapter, reader UX, or official manga startup.

The current production architecture should remain provider-neutral and should expose clean source/version/provenance boundaries so anime work can consume it later.

## AIComicBuilder / future builder work

The existing pinned AIComicBuilder upstream remains read-only reference material. Future Continuum adaptations should selectively reuse useful concepts rather than replacing Continuum's source-of-truth, production models, approval system, lineage, or provenance.

Builder integration should begin only after the calibration workflow is stable and official manga production has started, so implementation can target real production data rather than speculative interfaces.

## Long-term objective

Continuum becomes a production studio where:

- official manga generation continues continuously;
- approved manga episodes automatically become eligible for anime adaptation;
- anime preproduction and rendering run in parallel with later manga episodes;
- later source changes trigger precise dependency-aware updates instead of full-episode regeneration;
- every version remains reproducible, reviewable, and reversible through immutable lineage.
