# The Arrivals — M2/M3 Generation Handoff Correction

**Date:** 2026-09-14  
**Branch:** `creative/s1-season-board-v0.1`  
**Status:** AUTHORITATIVE TECHNICAL / PRODUCTION CORRECTION

## Purpose

This note clarifies what can actually be tested before real manga generation and corrects an outdated episode-order blocker.

## M2 scope

The currently available M2 generator is a **rough test / workflow generator** only.

It is appropriate for validating the end-to-end production flow:

- recipe creation;
- reference selection and attachment;
- attempt creation;
- review;
- approval;
- persistence / reopen behavior;
- job and manifest bookkeeping.

It is **not** evidence of final manga image quality and should not be evaluated as if it were a real manga-generation model.

A M2 smoke test may still use The Arrivals references and a non-canon sample, but the objective is workflow integrity, not aesthetic quality.

## M3 scope

Real manga generation begins in M3 when a local image model / generation backend is connected.

Recommended implementation order:

1. Make generation attempts consume the **reference manifest** as the authoritative source for character / style / environment grounding.
2. Build the **S1E1 chapter package** directly from the approved E1 manga panel script and its approved chapter cuts.
3. Connect the local generation model / backend and create actual grounded attempts from that package.
4. Run visual QC for character identity, proportions, composition, environment readability, style grounding, and consistency across pages.
5. Preserve full reproducibility metadata: job id, package / recipe version, exact references, model/settings, seeds where available, attempts, approvals, outputs and date.

## Mau reference preparation

Before meaningful M3 visual testing, prepare a dedicated Mau reference pack from user-supplied photos and an approved stylized character sheet / visual bible. The goal is a manga/anime-consistent version of Mau that remains recognizable and stable across pages, not photorealistic copying.

## Episode order blocker — resolved

An earlier technical report noted that episode ordering needed to be resolved before the E1 chapter package.

That blocker is no longer open.

Authoritative creative Git state already locks Season 1 to **19 episodes** in commit:

`1301650e52d998bd37c5b5dc85c77f5c1585dfcb` — `story: lock 19-episode S1 finale structure`

Late-S1 order:

- S1E17 — Guild Jobs / Working Days
- S1E18 — Day in the Life / Maomao Chocolate
- S1E19 — G3 / Road Days / Season Finale, intercut with G1+G2 and ending on Sukuna

The former separate G3 First Days and Road Days / Campfire units are merged into E19. There is no separate E20.

Therefore **episode order is not a blocker for M3**.

## Next operational sequence

0. Receive Mau photos and prepare Mau reference pack / visual bible.
1. Run Vault incremental rescan and verify intended references are visible / address any indexing gaps.
2. Run M2 workflow smoke test to verify manifest, attempts, review, approval and persistence. Do not treat M2 output as manga-quality evidence.
3. Implement / verify M3 attempts consume the reference manifest.
4. Build E1 chapter package from the approved panel script.
5. Connect local generation backend and run first real manga visual tests.
6. If visual tests pass, begin E1 production while creative Stage 3–4 work continues for remaining S1 episodes.

## Source-of-truth rule

Git remains authoritative. If an older report or memory note says the Season 1 episode order is still open, that statement is stale and is superseded by the later 19-episode structure lock.
