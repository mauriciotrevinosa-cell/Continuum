# The Arrivals — Manga Test Readiness Checkpoint

**Status:** READY TO BEGIN NON-CANON MANGA PIPELINE TESTS  
**Date:** 2026-09-14  
**Project:** `The Arrivals`  
**Branch:** `creative/s1-season-board-v0.1`

## 1. Creative readiness at this checkpoint

The manga-first production pass has advanced far enough that visual pipeline testing can begin without waiting for all of Season 1 to reach Level 4.

Current state:

- S1E1 — Level 4 / manga-ready — 79 provisional pages.
- S1E2 — Level 4 / manga-ready — 46 provisional pages.
- S1E3 — Level 4 / manga-ready — 58 provisional pages; title still pending.
- S1E4 — Level 4 / manga-ready — 52 provisional pages; title still pending.
- S1E5 — Level 4 / manga-ready — 48 provisional pages.
- S1E6 — Level 4 / manga-ready — 64 provisional pages.
- S1E7 — Level 4 / manga-ready — 66 provisional pages.
- S1E8 — Level 4 / manga-ready — 70 provisional pages.
- S1E9 — Level 4 / manga-ready — 50 provisional pages.
- S1E10 — Level 4 / manga-ready — 68 provisional pages.
- S1E11 — Level 4 / manga-ready — 72 provisional pages.
- S1E12 — Level 4 / manga-ready — 68 provisional pages.
- S1E13 — Stage 3 full episode construction complete; Stage 4 panelization/QC still pending at this checkpoint.
- S1E14–E19 — Stage 2 GREEN LIGHT; Stage 3–4 completion still pending.

## 2. Emerging page-count pattern — reference only, never a quota

The completed E2–E12 episodes currently range from **46 to 72 provisional manga pages**, averaging about **60 pages**. Including E1, the current completed range is **46 to 79 pages**, averaging about **62 pages**.

This is useful production information, but it is **not a target length**.

Standing rule remains:

> story need -> scene scope -> page count

Not:

> observed average -> force every episode toward that number

Future episodes may naturally require materially fewer or more pages. A 30–40 page episode or an 80–100+ page episode is valid if that is what the approved story requires.

The observed cluster around roughly 60 pages is useful for rough capacity planning only: generation jobs, review batches, storage estimates, and likely chapter grouping.

## 3. Authorization to begin manga tests

The project is now ready to begin **non-canon Continuum manga pipeline tests**.

This does **not** mean the entire production stack is declared fully proven. It means enough creative material is manga-ready, and the Continuum Reference Vault / rough manga foundation exists, to test the real workflow now.

The first visual test should remain deliberately non-canon so technical or visual failures do not create story debt.

## 4. First Continuum sample test

Use the real Continuum pipeline, real Vault references, and persistent production records. Do not substitute a one-off external image generator.

### Test cast

- Frieren
- Fern
- Mau
- Bocchi
- Yuta
- Rimuru
- Maomao
- Momo
- Anko

Mau must remain human and on-model; never mascot/cat-coded.

### Test content

A simple random non-canon action near the inn. The purpose is quality/consistency validation, not canon storytelling and not final inn architecture.

### Required outputs

1. **Color test** — slightly painterly/colored treatment grounded primarily in original manga/anime references, with fan art only as supplemental reference.
2. **B&W manga test** — manga-first treatment grounded especially in manga references.

### Required validation targets

- character identity consistency;
- character-to-character scale consistency;
- environment readability;
- group/action composition;
- correct reference grounding;
- no accidental replacement of characters or visual identities;
- usable B&W manga rendering, screentone/line hierarchy and readable silhouettes;
- reproducibility and persistence.

## 5. Vault / Continuum smoke test before judging image quality

Before rendering the sample:

1. open Continuum Studio;
2. confirm the Vault/Library is accessible;
3. run the required incremental/rescan so recently added anime/video archives become indexed;
4. verify real manga/anime references can be selected for the sample cast;
5. verify FanArt intake/reference records needed for supplemental use are visible/usable;
6. load/construct the non-canon sample job;
7. generate both color and B&W outputs;
8. inspect the saved job/manifest/reference set/settings/output records;
9. close and reopen Continuum;
10. confirm the job, exact references, outputs, approvals/review state and reproducibility metadata persist.

A successful image alone is not a PASS if the job cannot be reproduced or recovered after reopening.

## 6. Known infrastructure caveats to verify during the test

The implementation report previously noted that a set of recently added video archives required a Library rescan before becoming visible, and that media inside video archives had limitations. The smoke test must therefore verify the actual current indexed state instead of assuming it from code completion.

FanArt should be treated as supplemental and provenance-aware. Do not assume the entire intake folder is already curated/accepted simply because FanArt support exists.

The playlist/music-reference layer is not required to judge the first static manga sample, but it remains a production-system item to close before calling the wider manga/anime pipeline fully complete.

## 7. PASS / FAIL decision

### PASS

If both sample outputs are visually usable, reference-grounded, consistent and persistent after restart:

- begin real rough manga generation from S1E1;
- preserve all job manifests and review states;
- continue completing S1E13–E19 to Level 4 in parallel;
- human returns at Stage 5 for actual rough manga review.

### FAIL

If the sample reveals identity drift, bad composition, missing references, broken persistence, unusable manga rendering or Vault indexing problems:

- diagnose the specific failure;
- fix the root cause rather than patching one image;
- rerun the same sample or a tightly controlled variant;
- do not begin canon rough pages until the relevant failure is resolved.

## 8. Source-of-truth rule

This checkpoint is committed because Git remains the source of truth for creative and production readiness. Chat alone is not sufficient evidence that manga testing is authorized or that a given episode is manga-ready.
