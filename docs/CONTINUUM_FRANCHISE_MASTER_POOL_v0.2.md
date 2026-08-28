# Continuum — Franchise Master Pool v0.2

**Status:** Active creative-curation reference
**Date:** 2026-08-28
**Scope:** Human-facing franchise inventory only. This file is **not** application seed data and must never become hardcoded franchise logic.

## Purpose

This document is the canonical documentation-level inventory of franchises currently considered part of the Continuum creative pool.

It exists so the curated franchise list cannot silently disappear between selector exports, planning documents, and implementation phases.

Character-level selection remains separate from franchise inclusion. A franchise being listed here does **not** mean every character is approved, nor that every approved character must be main cast.

### Character curation states

- `APPROVED` — user selected **Sí**; available for story use, with narrative weight assigned separately.
- `OPTIONAL` — user selected **En el aire**; available when useful, not required early.
- `UNREVIEWED_RESERVE` — skipped/unanswered; not excluded and may be introduced later.
- `EXCLUDED` — explicit **No**; do not prioritize unless the user later changes the decision.

Narrative role is a separate axis: `CORE / MAIN`, `ACTIVE SUPPORT`, `RECURRING`, `OCCASIONAL`, `CAMEO / BACKGROUND`, `RESERVE`.

> The selector represents the available narrative population of Continuum, not a fixed protagonist cast.

---

## Verified pool

The original selector pool contained **42 franchises**. They have been re-checked against the final character-selection export and are all accounted for below. **My Dress-Up Darling** was not in that export and is added here as franchise **#43**.

| # | Franchise | Status |
|---:|---|---|
| 1 | Bocchi the Rock! | CURATED_SELECTOR |
| 2 | Sakamoto Days | CURATED_SELECTOR |
| 3 | Dandadan | CURATED_SELECTOR |
| 4 | SPY×FAMILY | CURATED_SELECTOR |
| 5 | Witch Hat Atelier | CURATED_SELECTOR |
| 6 | Solo Leveling | CURATED_SELECTOR |
| 7 | Jujutsu Kaisen | CURATED_SELECTOR |
| 8 | Jujutsu Kaisen Modulo | CURATED_SELECTOR |
| 9 | Frieren: Beyond Journey's End | CURATED_SELECTOR |
| 10 | The Apothecary Diaries | CURATED_SELECTOR |
| 11 | That Time I Got Reincarnated as a Slime | CURATED_SELECTOR |
| 12 | Gachiakuta | CURATED_SELECTOR |
| 13 | Miss Kobayashi's Dragon Maid | CURATED_SELECTOR |
| 14 | Call of the Night | CURATED_SELECTOR |
| 15 | Tokyo Ghoul | CURATED_SELECTOR |
| 16 | Rich Girl Caretaker | CURATED_SELECTOR |
| 17 | KonoSuba | CURATED_SELECTOR |
| 18 | Oh Boy, Was I Wrong About Her | CURATED_SELECTOR |
| 19 | Horimiya | CURATED_SELECTOR |
| 20 | The 100 Girlfriends Who Really, Really, Really, Really, Really Love You | CURATED_SELECTOR |
| 21 | Kaguya-sama: Love Is War | CURATED_SELECTOR |
| 22 | Attack on Titan | CURATED_SELECTOR |
| 23 | With You and the Rain | CURATED_SELECTOR |
| 24 | Chainsaw Man | CURATED_SELECTOR |
| 25 | Dealing with Mikadono Sisters Is a Breeze | CURATED_SELECTOR |
| 26 | The Quintessential Quintuplets | CURATED_SELECTOR |
| 27 | You and I Are Polar Opposites | CURATED_SELECTOR |
| 28 | I Made Friends with the Second Prettiest Girl in My Class | CURATED_SELECTOR |
| 29 | The Brilliant Healer's New Life in the Shadows | CURATED_SELECTOR |
| 30 | MarriageToxin | CURATED_SELECTOR |
| 31 | Food for the Soul | CURATED_SELECTOR |
| 32 | The Angel Next Door Spoils Me Rotten | CURATED_SELECTOR |
| 33 | Alya Sometimes Hides Her Feelings in Russian | CURATED_SELECTOR |
| 34 | Smoking Behind the Supermarket with You | CURATED_SELECTOR |
| 35 | The Healer Who Was Banished from His Party, Is, in Fact, the Strongest | CURATED_SELECTOR |
| 36 | Welcome to the Outcast's Restaurant! | CURATED_SELECTOR |
| 37 | Dr. STONE | CURATED_SELECTOR |
| 38 | MASHLE: Magic and Muscles | CURATED_SELECTOR |
| 39 | My Status as an Assassin Obviously Exceeds the Hero's | CURATED_SELECTOR |
| 40 | Am I Actually the Strongest? | CURATED_SELECTOR |
| 41 | My Ribdiculous Reincarnation | CURATED_SELECTOR |
| 42 | The Unaware Atelier Master | CURATED_SELECTOR |
| 43 | My Dress-Up Darling | ADDED_POST_SELECTOR |

---

## #43 — My Dress-Up Darling

**Inclusion status:** added to the franchise pool after the original selector was completed.

**Why it fits Continuum:** relationship-focused storytelling, fashion/cosplay craftsmanship, everyday life, creative collaboration, and direct synergy with the future Continuum Visual Lab.

### Initial seed cast

These are an initial **review set**, not a final character roster and not automatic `CORE` characters:

- Marin Kitagawa
- Wakana Gojo
- Sajuna Inui
- Shinju Inui
- Akira Ogata
- Amane Himeno

Additional characters can be added during the next character-curation pass without changing franchise inclusion.

---

## Preservation rules

1. Adding a franchise does not require selecting its full cast immediately.
2. Removing a character from active use does not remove the franchise from this inventory.
3. New franchises are appended and explicitly marked as post-selector additions until they receive a dedicated curation pass.
4. This document is creative documentation only. Tests, migrations, fixtures, application seed data, and runtime code must remain franchise-agnostic.
5. The engine must support a future pool of arbitrary size; **43 is the current creative inventory, not a technical limit.**

---

## Current count

- Original selector franchises verified: **42 / 42**
- Post-selector additions: **1**
- Current Continuum franchise pool: **43**
- Character expansion for My Dress-Up Darling: **pending future review**
