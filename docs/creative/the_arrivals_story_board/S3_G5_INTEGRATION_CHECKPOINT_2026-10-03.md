# The Arrivals — S3 G5 Integration Checkpoint — 2026-10-03

**Status:** ACTIVE REBUILD CHECKPOINT  
**Branch:** `m3/critical-path`  
**Audited HEAD:** `058d584fc7b102bed662b8d044635b16f70b03b6`  
**Purpose:** preserve all post-v0.2 corrections and define the exact point from which the G5 integration pass must continue before the rest of S3 is re-expanded.

## 1. Do not roll back the post-v0.2 work

The branch contains substantial work after `aaceea571d4ea03625ce04b2b2d96a9d7d7e72e0`. That work is authoritative unless explicitly superseded.

Major completed post-v0.2 repair families include:
- V11 false-stability and first-search runway;
- V12 second-road / monster / collapse / Rem-Kaneki-Aira convergence;
- V13 field recovery / containment / early reconstruction;
- V14 staged Move / dual-home transition;
- V15-V17 partial/full scene-density upgrades;
- V18 pre-Last-Defense runway through evacuation;
- V19 Trial accumulation, post-Trial logic, ten-day clock and pre-contact interception;
- first-pass G5 mechanism repair;
- final creator-direction document for G5/cast rings/S4 handoff.

The later source:
`docs/creative/the_arrivals_story_board/sources/THE_ARRIVALS_S3_G5_CAST_RING_AND_S4_HANDOFF_v0.1.md`
was committed *after* the first-pass G5 prose edits. Therefore the source is newer than several chapter implementations and must control the next pass.

## 2. G5 authoritative purpose

G5 is not a franchise quota or showcase.

G5 must:
- form accidentally because Diablo is searching for Mau;
- happen while Mau is absent and the household is already deteriorating under the search;
- let newcomers first learn Mau through the hole his absence leaves;
- close important relationship gaps around the existing ensemble;
- widen the second relational ring without making every arrival Core;
- help the unfinished worksite / overcrowded inn in concrete ways;
- arrive in waves rather than one compressed door explosion;
- preserve the rule: **Continuum imports people, not franchise checklists.**

## 3. Current high-confidence G5 set

Treat as active unless later creator direction changes it:
- Milim Nava — enters the window by recognizing Diablo, not as a real false positive;
- Mai Zenin;
- Nijika Ijichi;
- Ryo Yamada;
- Richeh;
- Tetia;
- Vamola;
- Turbo Granny;
- Seiko Ayase;
- Jinshi;
- Nazuna Nanakusa;
- Senku Ishigami;
- Suika — preferred Dr. Stone companion.

Explicitly not G5:
- Eren — separate later voluntary arrival;
- Gojo — defer;
- Serie — defer;
- automatic Re:Zero / Tokyo Ghoul additions — do not add for symmetry;
- automatic Himouto-side expansion — not required.

Kusuri Yakuzen remains **PROVISIONAL** and must not be written into LN canon without later creator confirmation.

## 4. Concrete implementation conflicts discovered at audited HEAD

### V11 reader-order / metadata drift
- V11 index still claims **26** chapters.
- Active V11 files now total **27** because `The First Night Without Him` and `Day Two Without Mau` were added.
- The obsolete `Frieren Hits First` chapter was removed, but the V11 index still lists it.
- Result: the index is stale and the S3 production count of **249** is also stale; the active total is already **250** before any new G5-wave chapters are added.

### V11 chronology drift
Current metadata runs:
- `Eight Signatures` = Day 3 pre-dawn;
- the following witch chapters still claim Day 2 morning / midday / afternoon.

That is impossible in reader order and must be repaired when G5 is re-laid.

### G5 prose predates the final roster
`The Mega-Haul` currently uses generic unnamed newcomers and compresses several false positives into a montage.
That was a useful mechanism test, but it does not yet implement the later creator-approved/high-confidence G5 relationship set.

### Senku duplicated
- current G5 prose makes Senku the first major Diablo false positive;
- V16 Chapter 4 still introduces Senku as newly found by Searchers.

Both cannot be active continuity.
Required fix:
- Senku + Suika arrive during G5;
- early Senku only self-tests / helps with small worksite problems;
- V16 becomes the later **major civic audit**, not Senku's arrival.

### Richeh duplicated
- final G5 direction places Richeh + Tetia in G5;
- V15 Chapters 9–10 still stage Richeh's first arrival/reunion.

Required fix:
- Richeh + Tetia reunite with the Atelier group during G5;
- V15 uses them as already-present people with independent settlement choices/roles, not as new arrivals.

### Missing named G5 members
The first-pass V11 prose does not yet fully instantiate:
- Suika;
- Mai;
- Nijika;
- Ryo;
- Tetia;
- Vamola;
- Turbo Granny;
- Seiko;
- Jinshi;
- Nazuna.

They must receive lived entrances/reunions, not be inserted as a roster paragraph.

### Named persistence is not yet wired
`G5 Is Still Here` still refers to generic statuses such as "one person", "two wanted to remain", etc.
After final G5 prose, the chapter must track named people and non-identical choices/statuses.

### Post-Memory source direction is newer than some V13 prose
The newest source also requires:
- Mau's RCT to remain explicitly real but limited by unstable body-template repair targets;
- containment to reveal competing adaptation attempts rather than one clean species change;
- Frieren to ask whether the elf/longevity route was preserved;
- Rimuru/Raphael to say no, because forcing a stable new template now risks shock;
- the appearance of an elf-like route to give hope without a lifespan promise;
- the Mau/Frieren post-Memory date to include the explicit present-memory promise:
  "What if I forget again?" -> "Then I'll remind you." -> "How many times?" -> "As many as it takes."

Current V13 prose does not yet fully implement all of those later locks.

## 5. Prose-density state after post-v0.2 work

Do not mistake "many commits" for a finished LN pass.

Measured from the current tree:
- V12 median chapter size is now ~4.2 KB;
- V13 ~3.8 KB;
- V14 ~3.3 KB;
- V15 ~2.9 KB;
- V16 ~3.2 KB;
- V17 ~3.0 KB.

But:
- V18 median is only ~1.05 KB because Chapters 10–27 remain largely compressed beats;
- V19 median is ~2.28 KB and still contains many sub-1.5 KB community/transition chapters.

So the correct sequence is:

```text
finish G5 as lived continuity
-> reconcile all downstream G5 consequences
-> repair remaining late V13 locks
-> then resume season-wide full-prose expansion
-> V15/V16/V17 consistency pass
-> V18 full Last Defense + later Noise/Goddess prose pass
-> V19 non-core community/decision prose pass
-> final season-wide continuity + density audit
```

## 6. G5 implementation order for the next pass

The next pass should not patch `The Mega-Haul` with a name list.

Use lived waves:

1. **Diablo at the door**
   - preserve the corrected Frieren/Diablo confrontation after ~2 days of searching;
   - Rimuru stops it;
   - Diablo learns who Mau is and accepts the search.

2. **First major false positive**
   - Senku + Suika;
   - Senku asks who Mau is;
   - self-test and cognitive-throughput problem begin;
   - only small worksite help.

3. **Relationship wave**
   - Mai / Maki;
   - Nijika + Ryo / Bocchi + Kita;
   - Richeh + Tetia / Coco + Agott + Qifrey.
   - Each reunion must remain primarily about the existing relationship, not Mau.

4. **Supernatural mismatch wave**
   - Nazuna / Anko;
   - Vamola + Turbo Granny + Seiko / Momo-Okarun-Aira orbit;
   - establish Continuum rule mismatch without prematurely resolving the later Anko/Nazuna medical consequence.

5. **Political/social texture**
   - Jinshi / Maomao;
   - Milim joins via Diablo encounter and Rimuru connection.

6. **The empty place**
   - G5 first shared meal / chores / worksite contribution;
   - repeated "Who is Mau?" questions change from gag to emotional weight;
   - no universal adoration;
   - Agott's resource-cost challenge remains legitimate.

7. **Eight signatures**
   - only after G5 mechanism is established;
   - distinct from the false-positive haul;
   - leads back into the Mau/witch search.

8. **After Mau returns**
   - named G5 statuses;
   - no "permanent family" intake category;
   - some remain, some travel, some defer decisions;
   - relationships continue without routing everyone through Mau.

## 7. Hard guardrail before rebuilding the rest of S3

Do **not** perform the final season-wide rewrite until:
- the G5 roster is materially present in V11;
- Senku and Richeh downstream duplicate-arrival contradictions are removed;
- V11 reader order and dates are internally consistent;
- the latest Memory/body/date locks are integrated;
- the production index is reconciled to the actual chapter set.

This checkpoint exists specifically so a future chat cannot accidentally resume from the older v0.2 architecture and erase the post-v0.2 repair work.


---

## 8. Completion update — 2026-10-03

The immediate G5 integration pass has now been carried through the active LN continuity.

Completed:
- V11 expanded from 27 active chapter files to **34** reader-order chapters;
- first-disappearance runway now includes the two missing search days before Diablo;
- Frieren/Diablo confrontation remains inside **A Demon at the Door**;
- Senku + Suika are the first major false-positive arrival;
- Mai gets a Maki-centered reunion;
- Nijika + Ryo complete the immediate Kessoku relationship ring;
- Richeh + Tetia reunite with the Atelier group before the later city arcs;
- Nazuna reunites with Anko without triggering the later bite/conversion consequence prematurely;
- Vamola + Turbo Granny + Seiko enter through the Dandadan-side wave;
- Jinshi reunites with Maomao without inheriting source-world authority;
- Milim joins by finding Diablo / Rimuru rather than as a true false positive;
- first shared G5 meal is now named/lived rather than generic montage;
- post-return Mau dinner is now a named ensemble scene;
- G5 status divergence is now named instead of anonymous;
- obsolete **Frieren Hits First** index entry is removed;
- V11 reader order is reconciled to **34** chapters;
- Senku's later V16 material has been converted from a duplicate arrival into the delayed major civic audit;
- Richeh/Tetia's later V15 material now treats them as already present and making independent housing/status choices;
- latest Memory source locks were also integrated where they directly affected this handoff:
  - RCT remains real but limited;
  - competing body-template adaptation is explicit;
  - arrival-state stabilization does not define Mau's true species;
  - Frieren receives lifespan hope without a promise;
  - the post-Memory date now includes the required "I'll remind you / as many as it takes" promise.

Current total reader-order count:
- **257 chapters** including V10's 17 revalidated v0.1 carryover chapters.

The next safe phase is no longer "finish G5."

It is:

```text
G5 continuity now established
-> propagate named G5 presence through later ordinary-life / Move / civic / defense scenes
-> finish the remaining late-S3 full-prose blocks
-> run season-wide continuity and density audit
```

Do not revert to the pre-G5 assumption that Senku or Richeh first arrive later in S3.
