# The Arrivals — Next Manga Test Sequence v0.1

**Status:** AUTHORITATIVE NEXT OPERATING SEQUENCE  
**Date:** 2026-09-14  
**Project:** `The Arrivals`  
**Branch:** `creative/s1-season-board-v0.1`

## Decision

Do not request more speculative implementation work from Claude before running the current Continuum stack through a real manga-production smoke test.

The next useful information should come from actual use of Continuum. Additional Claude work should be driven by concrete failures, missing capabilities, or production blockers discovered during the test rather than by adding features blindly.

## Locked next sequence

0. User sends personal photo references for Mau so a consistent Mau visual reference pack / character bible can be established before the sample.
1. Open Continuum and run the incremental Vault rescan.
2. Verify real character references are accessible and correctly grounded in the Vault.
3. Create a **NON-CANON** sample scene using Frieren, Fern, Mau, Bocchi, Yuta, Rimuru, Maomao, Momo, and Anko.
4. Generate two versions from Continuum:
   - color;
   - black-and-white manga.
5. Review character identity, proportions, composition, environment readability, and reference grounding.
6. Close Continuum and reopen it; verify that job, exact references, settings, outputs, and production state persist correctly.
7. If the smoke test passes, begin real S1E1 manga production.
8. In parallel with E1 production, continue Stage 3 / Stage 4 completion of S1E13–E19 until the entire season reaches Level 4 / manga-ready.

## Mau reference rule

Mau is human and should be visually derived from the user's approved personal references while being adapted coherently into the manga/anime visual language of the project.

Do not use a mascot, cat, generic stand-in, or unrelated generated face for Mau.

The Mau reference pack should establish stable identity signals such as facial structure, hair, body proportions, apparent age, recurring expressions, and the intended degree of stylization before the first Continuum sample is judged.

## Claude rule

Do not ask Claude for more work now by default.

Return to Claude only if the real smoke test reveals a concrete engineering issue, such as:
- incremental rescan failure;
- missing or inaccessible Vault references;
- broken reference grounding;
- failed persistence / resume behavior;
- generation workflow bug;
- missing production metadata needed for reproducibility;
- another specific blocker that cannot be solved within the current workflow.

This keeps engineering driven by observed production needs rather than speculative expansion.
