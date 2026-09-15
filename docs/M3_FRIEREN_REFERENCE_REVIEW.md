# M3 — Frieren reference review before Production Model v1

Status: **review recommendation prepared; creator confirmation still required in UI before identity state changes**.

Source of findings: `docs/M3_CODEX_VISUAL_QA.md` plus the current M3 corpus rules. This document converts that audit into a concise action list for the Character Production Model sprint.

## 1. Immediate rejects / corrections

### Invalid confirmed body anchor

Observation/reference:

- `01a0a2c1-916a-7427-80f1-c548b1fdea00`
- label: `Frieren full figure, opening chapter`

Finding: the served material is a table-of-contents/index page with only a tiny decorative silhouette. It does not establish Frieren's body proportions, outfit construction or scale.

Action: **remove/reject it as Frieren BODY/FULL_BODY grounding/anchor**. The underlying source asset may remain in the library if useful for some other reason.

### Wrong Frieren candidate — Chapter 91 p14

Observation:

- `01a0a2c1-91c7-72b9-9561-dc7647139aaa`

Finding: inspected page shows other figures, including a horned figure; it does not visually verify Frieren.

Action: **reject the Frieren character association**. Do not delete the source page. It may remain usable for non-identity roles if relevant.

### Wrong Frieren candidate — Chapter 123 p13

Observation:

- `01a0a2c1-91c7-72f9-8980-85537c1ba025`

Finding: inspected page shows a dark-haired human girl with a young man and does not verify Frieren.

Action: **reject the Frieren association**. It may be reviewed separately as a Fern candidate, but must not be auto-confirmed as Fern.

## 2. Strong recommended review pack

These are not automatically confirmed by this document. They are the small set the creator should inspect/confirm for Production Model v1.

| Observation | Source | Recommended use | Limit |
|---|---|---|---|
| `01a0a2c1-916a-7425-9a40-2037f8a4d714` | existing verified crop | FACE identity anchor | crop does not solve full body |
| `01a0a2c1-91c6-769e-a10d-745cbed87805` | Ch1 p14 | PROFILE / side face, back hair/robe, conversational acting | identify only the elf; other people on page are not Frieren |
| `01a0a2c1-91c6-76a0-9c8d-1f828efe6fb2` | Ch2 p13 | FRONT/3-4, quiet warmth, travel outfit/staff, outdoor staging | short dark-haired girl shown is young Fern |
| `01a0a2c1-91c6-76a3-860a-8e36aa4d466d` | Ch3 p24 | FULL BODY / proportions, boots, staff, frontal face, wardrobe | strongest known replacement for invalid body anchor |
| `01a0a2c1-91c6-76a7-a19c-d491c57d50fa` | Ch5 p14 | PROFILE, robe silhouette, staff context | combat lighting/danger must not transfer to quiet scene |
| `01a0a2c1-91c6-76a8-9fc3-f0e12d0b748d` | Ch6 p7 | standing full figure / staff | lower close-up is Fern, not Frieren |

Additional craft evidence:

- Frieren manga Ch1 p20, source unit `77ea902aa2989c594b7e2890f2d0179acfabba88`, offset `19`: useful for half-lidded/deadpan conversational acting and restrained annoyance. Treat as acting/technique evidence until explicitly reviewed for character grounding.

## 3. Suggested Production Model v1 coverage

After creator confirmation, Frieren should have a small preferred pack covering:

- face/front or near-front: existing verified face crop + Ch3 p24/Ch2 p13 as support
- 3/4: Ch2 p13
- profile: Ch1 p14 or Ch5 p14
- full body/proportions: Ch3 p24, optionally Ch6 p7 as supporting evidence
- default/travel wardrobe: Ch2 p13 + Ch3 p24
- hair/back silhouette: Ch1 p14
- quiet/deadpan acting: Ch1 p20 as acting/craft support

A generated HEAD/FULL BODY turnaround derived from this evidence remains `PROJECT_CREATED / CANDIDATE` until creator approval.

## 4. Acting rule for early Chapter 2

The page-level retrieval currently risks applying a `confused` intent to both characters. For the early Frieren/Mau exchange:

- Mau: disoriented / memory-searching / confused innocence
- Frieren: attentive, calm, restrained, deadpan/quietly curious

Production retrieval must not turn Frieren into a second confused face just because the page's global intent mentions confusion.

This is a retrieval/acting constraint, not a story rewrite.

## 5. Role mismatches to avoid

The following pages are valid source/craft material but poor early-scene acting teachers:

- Kagurabachi Ch0 p94: violent action / heavy blacks; not a restrained-expression exemplar
- Jujutsu Kaisen Ch0 p94: impact/combat layout; not quiet interpersonal silence

They may remain grammar/technique candidates for other needs. Do not delete them just because they are wrong for Page 3 acting.

## 6. Environment/layout traps

Do not mistake wide panels/layout hints for semantic environment proof:

- Frieren Ch72 p10 and Ch84 p10 are interiors/architecture, not forest/trail/flower-field evidence
- Witch Hat Atelier Ch0 p11 is a partial colored strip, not strong full-page/flower proof
- Solo Leveling Ch0 p37 is essentially a black field with `BEEP`, not useful environment/content proof

## 7. Creator actions after the new UI exists

In the actual corpus/Production Model flow:

1. reject the invalid index/body anchor
2. reject Ch91 p14 as Frieren
3. reject Ch123 p13 as Frieren
4. inspect and, if correct, confirm Ch3 p24 for BODY/WARDROBE
5. inspect and, if correct, confirm Ch2 p13 for FACE/3-4/WARDROBE/QUIET_ACTING
6. inspect profile candidates Ch1 p14 and Ch5 p14
7. build Frieren Production Model candidate
8. review the generated HEAD and FULL BODY sheets
9. approve only if identity/proportions/outfit remain faithful

## 8. Do not do yet

- do not mark every early-chapter page as Frieren because the source series contains her
- do not use candidate observations for identity conditioning
- do not train a LoRA on this mixed set before training eligibility/rights and visual consistency are reviewed
- do not treat the generated turnaround as source canon
- do not begin a real-art chapter run until the early cast's Production Model/wardrobe state is ready enough for the page

This review replaces the old assumption that the inherited full-body anchor was valid; it does not impersonate creator approval.