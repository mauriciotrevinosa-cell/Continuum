# The Arrivals — Season 3 Light Novel Production Index v0.2

**Status:** ACTIVE CONTINUITY CANON — FULL-PROSE EXPANSION IN PROGRESS  
**Season:** 3  
**Branch:** `m3/critical-path`  
**Reader-order chapters:** **258**  
**Volumes:** **10–19**

## Important production correction — 2026-10-02

The v0.2 rebuild fixed major **continuity architecture**, but it was incorrectly labeled as a completed light-novel production draft.

A season-wide density audit showed that many v0.2 chapter files are still written as compressed story beats rather than lived LN scenes.

Measured proxy:
- S3 v0.2 chapter files: 227;
- S3 v0.2 median file size before the current prose pass: ~1.28 KB;
- 192 / 227 were below 2.5 KB;
- 223 / 227 were below 4 KB;
- S2 LN median for comparison: ~2.31 KB, with many major chapters in the 5–8 KB range.

File size is not a quality score. It is only a useful warning signal. The actual issue is visible in the prose: too many chapters state that something happened instead of making the reader live through the event.

Therefore:

> **v0.2 is continuity-correcting story canon, not yet a fully finished LN prose pass.**

Do not call S3 "complete" until the scene-density expansion pass finishes.


## No-compression guardrail — 2026-10-03

New continuity decisions do **not** get paid for by shrinking already-expanded scenes.

When a new locked character, consequence or scene requires space:
- add the scene or chapter;
- update reader order and counts;
- propagate the consequence forward;
- do not collapse previous lived prose back into summary/montage.

Kusuri Yakuzen is the current explicit test case: her addition raises V11 and season chapter counts rather than replacing or compressing another G5 chapter.

## Reader order / continuity architecture

| Volume | Title | Chapters | Active continuity source |
|---:|---|---:|---|
| 10 | Bare Ground | 17 | existing V10 v0.1 chapters, revalidated |
| 11 | Eight Signatures | 35 | v0.2 |
| 12 | The Second Road | 20 | v0.2 |
| 13 | Bring Him Back | 27 | v0.2 |
| 14 | The Move | 20 | v0.2 |
| 15 | People Who Heard About Us | 24 | v0.2 |
| 16 | What the Message Changes | 24 | v0.2 |
| 17 | Freedom and Walls | 24 | v0.2 |
| 18 | Last Defense | 27 | v0.2 |
| 19 | What Would You Choose? | 40 | v0.2 |

## Critical version rule

S3 v0.1 chapters from V11–V17 remain in Git only as provenance / discarded production.

They are **not** active reader continuity.

For any S3 continuity question:
1. use V10 revalidated carryover only for S3E1–S3E6;
2. use v0.2 continuity after the first disappearance;
3. never use a shorter v0.1 scene to overwrite a corrected v0.2 event chain;
4. when a v0.2 chapter receives a full-prose expansion, the expanded same-path file becomes authoritative.

## Current full-prose expansion status

### Actively expanded / corrected

The second-disappearance rescue runway now explicitly lives through:
- Rem / Kaneki / Aira finding Mau and Ori;
- immediate field triage;
- cap recovery remaining a mundane continuity object;
- Mau's intermittent recognition;
- visible body changes;
- multiple hours / overnight care;
- larger search group arriving without immediate transport;
- field stabilization after the family arrives;
- Mau sometimes recognizing Frieren and sometimes not;
- transport only after several conditions improve;
- return to the old inn while cognitive recovery remains incomplete;
- Rimuru's containment idea emerging from repeated observational questions;
- a multi-person clarity check before Mau's consent;
- Frieren's separate trust decision;
- The Noise becoming observable only after containment changes access conditions.

### Full-prose pass now cleared at critical-path level

- V11 first-search / named G5 wave / false-stability ending;
- V12 second-road / monster / collapse / field-rescue runway;
- V13 field recovery / containment / reconstruction / ordinary recovery at the earlier lock level; newest body-template / lifespan / date-dialogue locks still need integration;
- V14 The Move in full lived progression;
- V19 core Goddess Trial accumulation / post-Trial trauma / ten-day Return-Stay clock / Day-3 backdoor attempt / road interception before Goddess contact.

### Still requiring full-prose expansion

- remaining V15 Arrival House / refuge / unity consequences beyond the already-expanded opening institutional cases;
- V16 hybrid-city development;
- V17 Eren / freedom / civic-law blocks;
- V18 Last Defense / later Noise overload;
- remaining non-core V19 Return/Stay community-processing chapters.

The continuity order remains active while prose density is upgraded.

## Macro reader flow

```text
V10  bare ground / slow Memory fracture / first disappearance
V11  first search / Diablo -> G5 / eight signatures / witches / bargain / first return / three-day false stability
V12  Mau+Ori second road / multi-day escape / monster head injury / collapse / Rem-Kaneki-Aira field rescue
V13  field camp / gradual lucidity / slow return / containment questions and consent / Noise observation / reconstruction / recovery
V14  explicit staged Move / two homes at once / first nights / old inn protected as origin-home
V15  intentional migration / Arrival House / Searchers / post-G5 independent choices / second community / refuge / unity message
V16  message consequences / external partnership / Senku's delayed major civic audit / flawed infrastructure redesign / hybrid Continuum city
V17  Eren-Mikasa asymmetry / exit rights / due process / domestic convergence / Mau sacrifice expectation
V18  Last Defense / infrastructure payoff / aftermath / distinct Noise overload / Goddess intrusion
V19  bounded Trial / hundreds-scale lived consequence / 10-day Return-Stay window / Days 0–3 trauma spiral / road interception before Goddess contact / 7-day S4 handoff
```

## Reader guidance

A reader coming from the broken old S3 should not use v0.1 after V10.

However, if the goal is to read the final polished S3 LN rather than follow development, wait until the full-prose expansion status above is cleared.

The current continuity repair point remains:

> **Volume 11 v0.2, Chapter 1 — No One Waits**

but later chapters are still being expanded from compressed production beats into full scenes.
