# The Arrivals — M2 Smoke Test Findings

**Date:** 2026-09-14  
**Project:** The Arrivals  
**Branch:** `creative/s1-season-board-v0.1`  
**Purpose:** Record what the current Continuum M2 UI actually exposes before M3 manga generation work begins.

## PASS — working foundations observed

- Studio opens correctly and Vault is visible.
- Source Vault is populated and scanned.
- FanArt collection is visible.
- Series catalog is populated across manga/anime/fan-art material.
- Manga reader works from archived chapter ZIPs.
- Anime playback works from archived video material in at least tested cases.
- Library jobs shown in the Jobs view complete successfully (`library.catalog_scan`, `library.catalog_hash`, `library.member_extract`).
- The Arrivals project is present and project history/versioning is visible.
- S1E1 manga panel script is visible as approved / production-ready with 79 provisional pages.
- Rough workflow exists and explicitly identifies itself as M2 deterministic sketch rendering rather than finished art.
- Reference Vault exists with filters for class/origin/use and preserves provenance links.

## BLOCKER 1 — project ingestion/index is stale versus Git

Current UI still exposes only S1E1 as an individual story/draft/panel-script episode artifact, while Git currently contains Level 4 draft + manga panel script + editorial overview artifacts for S1E2 through S1E12.

Observed UI symptoms:
- Project overview still groups S1E2–S1E8 as a rough roadmap.
- S1E9–S1E15 still appear as a rough roadmap.
- Production summary reports only 1 panel script.
- Manga tab reports 1 artifact.
- Roughs panel-script selector offers S1E1 only.

Therefore M3 must not infer readiness from this stale project index. Before M3 production, Continuum must resync/reindex project documents from the latest Git state so S1E1–S1E12 appear as individual Level 4 manga-ready episodes.

## BLOCKER 2 — character/reference manifests are too sparse

Current Character Vault visibly contains only Frieren and Fern. Frieren currently exposes 4 source references and one preferred identity face reference.

For production use, Continuum needs character manifests for the actual S1 cast and should allow multiple complementary references per character rather than relying on a single source plate. At minimum production manifests should distinguish/reference:
- identity / face;
- outfit / wardrobe;
- expression / acting;
- pose / body proportions;
- accessories;
- canonical manga reference;
- anime reference where useful;
- approved fan-art / supplemental style reference where explicitly selected.

Mau is an original/project character and should use the approved `THE_ARRIVALS_MAU_VISUAL_REFERENCE_PACK_v0.1.md` plus creator-supplied photo references rather than being treated as a franchise import.

## BLOCKER 3 — reference manifest consumption must precede real generation

M2 demonstrates reference browsing/capture and rough attempt bookkeeping, but M3 attempts must explicitly consume a resolved reference manifest/bundle. Generation must be reproducible from:
- panel/page recipe;
- exact reference IDs / provenance;
- character identity manifests;
- style/mode manifest;
- generation model/settings;
- seed when supported;
- output and review status.

Do not connect a local image model first and then add reference-manifest grounding afterward. Reference-manifest use is the first M3 requirement.

## ISSUE — sequel/arc family detection

In Library > Families, `Call of the Night -Paradise-` is shown as Missing even though the user reports that this material is already included in the acquired source set. The family/coverage resolver should be checked so included sequel/arc material is not reported as absent when it is actually present under an existing archive/folder naming scheme.

This is a catalog/coverage correctness issue, not a blocker for E1 itself, but should be fixed because future source selection depends on trustworthy family coverage.

## UX ISSUE — long manga/anime lists should be collapsible

Vault > Series > individual series currently expands very long chapter and episode lists on the same page. For series with hundreds of chapters plus anime episodes, manga/anime sections should be collapsible (or use compact ranges/pagination) so the series overview remains navigable.

Library > Families already behaves more like the desired compact overview.

## UX/PRODUCTION NOTE — generation entry point

The user did not find a `Generate manga` action in the Manga tab. This is expected for current M2: the Roughs page states that the deterministic sketch renderer produces labelled diagrams and that no image model is installed.

Current M2 entry point is therefore `Roughs -> Open rough workspace`, which validates recipe/attempt/review/approval persistence only.

M3 should add an unambiguous production entry point from an approved panel script/chapter package, e.g. a `Generate rough` / `Start chapter package` action, rather than requiring the user to infer that Roughs is the generation surface.

## Recommended M3 order

1. Fix/resync The Arrivals project ingestion so current Git Level 4 artifacts appear individually (E1–E12 at present).
2. Resolve character/reference manifests and make generation attempts consume those manifests.
3. Build the S1E1 chapter package directly from the approved S1E1 manga panel script and approved chapter cuts.
4. Add/verify clear production entry point for real rough generation.
5. Connect local image model.
6. Run non-canon visual sample first (color + B&W manga) using real reference bundles.
7. Verify persistence by closing/reopening Continuum and confirming job, recipe, exact refs, settings, attempts, approvals and outputs survive.
8. PASS -> begin real S1E1 manga production.

## Current decision

M2 workflow foundation: **PASS with actionable findings**.  
Ready for M3 implementation: **YES, after project-index resync and reference-manifest consumption are treated as first-order requirements.**  
Ready for real manga quality evaluation today: **NO — no real image model is connected yet.**
