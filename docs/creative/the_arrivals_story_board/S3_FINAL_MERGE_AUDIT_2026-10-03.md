# The Arrivals — Season 3 Final Merge Audit — 2026-10-03

**Status:** FINAL S3 AUDIT — PASSED  
**Branch:** `m3/critical-path`  
**Pre-audit content HEAD:** `748a2a9eb805e146a08e75a720962a5676a641dc`  
**Reader-order chapters:** **258**  
**Volumes:** **10–19**

## 1. What this audit protects

This audit exists because the original `v0.2` rebuild was **not** the final Season 3 text.

The correct lineage is:

```text
original compressed v0.2 architecture
-> large post-v0.2 repair pass from the prior chat
-> G5 completion / later Memory locks / Move / civic / Trial repairs
-> final merge + prose expansion pass
-> this audit
```

The earlier handoff point:

`aaceea571d4ea03625ce04b2b2d96a9d7d7e72e0`

was **not** used as the final baseline.

The prior chat continued substantially after that point. The branch state used as the pre-finalization baseline was:

`f93e68af4602cb1e5395057ba522be8ade0a0d40`

That state was **260 commits ahead** of `aaceea...`.

Therefore:

> **Do not reconstruct S3 from the old v0.2 files by label. The authoritative season is the latest merged branch state.**

File suffixes are provenance, not authority.

## 2. Preservation check against the prior chat

Comparison from `f93e68...` to the final pre-audit content state found:

- **75 later commits** in the finalization pass;
- **104 files changed** relative to the prior-chat baseline;
- **103 files modified**;
- **1 file intentionally added**:
  - `THE_ARRIVALS_S3E8_LN_CHAPTER_02H_KUSURI_ASKS_WHERE_THE_LAB_IS_v0.2.md`;
- **0 files from the prior-chat baseline deleted**.

This matters because the final pass was required to **merge onto** the prior chat's work, not replace it.

The only temporary duplicate files created during the final pass were accidental V10 `_v0.2.md` copies. They were removed after their useful prose additions were merged back into the active legacy-path V10 files. Those temporary duplicates did not exist in the prior-chat baseline and did not replace any prior-chat chapter.

## 3. Active chapter set

Final active reader-order count:

| Volume | Title | Chapters |
|---:|---|---:|
| 10 | Bare Ground | 17 |
| 11 | Eight Signatures | 35 |
| 12 | The Second Road | 20 |
| 13 | Bring Him Back | 27 |
| 14 | The Move | 20 |
| 15 | People Who Heard About Us | 24 |
| 16 | What the Message Changes | 24 |
| 17 | Freedom and Walls | 24 |
| 18 | Last Defense | 27 |
| 19 | What Would You Choose? | 40 |

Total: **258**.

All ten volume indexes now report:

`ACTIVE MERGED READER ORDER — PROSE PASS COMPLETE`

## 4. V10 lineage rule

V10 is intentionally unusual.

Its 17 active chapter files retain legacy `_v0.1.md` filenames, but the **contents were expanded and merged in place** during the final pass.

Final checks:
- 17 active V10 chapters;
- 0 accidental parallel V10 `_v0.2.md` chapter files remain;
- Volume 10 index explicitly lists all 17 chapters;
- the old filename suffix must never be interpreted as meaning "older prose wins."

## 5. Mechanical metadata audit

Every active chapter was checked for:
- chapter number;
- reading-order number;
- volume number;
- expected volume from episode position;
- production placeholders;
- stale expansion markers;
- compression-warning size.

Results:
- **258 / 258** active chapters have chapter number = reading-order number;
- **258 / 258** active chapters point to the expected volume;
- no active chapter is below the 2.5 KB compression-warning threshold;
- no active chapter contains a real `TODO`, `TBD`, `FIXME`, or placeholder instruction;
- no active chapter contains a real "expand later" / "to be expanded" production instruction.

A handful of literal words matched the automated marker scan but were manually reviewed and are **story text, not production debt**:

- V10 C3: "three provisional zones" — construction planning;
- V11 C1: "provisional worksite" — correct continuity state;
- V11 C11: "provisional outside shelter" — correct in-scene shelter status;
- V15 C5: "provisional institution" — Arrival House becoming an institution;
- V15 C9: "Arrival House provisional" / "provisional Arrival House" — correct institutional state;
- V15 C21: "real crimes still require evidence" — ordinary prose, not an expansion note;
- V18 C19: "final structure remained provisional" — governance remains intentionally provisional.

No production cleanup is required for those uses.

## 6. Density audit

File size is not a quality score, but it remains useful as a compression alarm.

Final active medians:

| Volume | Minimum | Median | Maximum |
|---:|---:|---:|---:|
| 10 | 2.51 KB | 3.07 KB | 4.22 KB |
| 11 | 2.66 KB | 3.46 KB | 9.00 KB |
| 12 | 2.60 KB | 4.23 KB | 5.99 KB |
| 13 | 2.67 KB | 3.90 KB | 7.70 KB |
| 14 | 2.57 KB | 3.40 KB | 5.29 KB |
| 15 | 2.51 KB | 2.97 KB | 4.56 KB |
| 16 | 2.71 KB | 3.23 KB | 8.13 KB |
| 17 | 2.54 KB | 3.03 KB | 4.12 KB |
| 18 | 3.00 KB | 4.23 KB | 6.25 KB |
| 19 | 2.56 KB | 3.74 KB | 6.17 KB |

The original compression problem is therefore no longer hiding in mass sub-2.5 KB chapters.

This does **not** mean all chapters must be the same length. Shorter scenes are allowed when the scene itself is complete.

## 7. Major continuity repairs verified

### Memory / first disappearance
- V10 grows the Memory fracture through ordinary life rather than jumping directly to crisis;
- false memories reuse real places / people / emotional truths;
- wrong memories can arrive with high confidence;
- Mau's first disappearance grows from a false instruction that feels independently verifiable.

### G5
- G5 forms while Mau is absent and the household is already under search pressure;
- Diablo remains the connector;
- Senku + Suika arrive in G5 rather than being duplicated later;
- Mai / Nijika / Ryo / Richeh / Tetia / Nazuna / Vamola / Turbo Granny / Seiko / Jinshi / Milim receive lived relational placement;
- Kusuri Yakuzen is a **locked G5 member**, not provisional;
- Kusuri receives her own lived chapter rather than a roster insertion;
- Kusuri continues with the community and her intended later Return/Stay answer is **STAY**;
- Kusuri's answer does not bind Hakari, Karane, Shizuka, Nano, or anyone else;
- adding Kusuri increased chapter count rather than compressing another scene.

### Second road / rescue / recovery
- Mau + Ori's second departure remains morally complicated;
- Rem / Kaneki / Aira find Mau first and remain essential witnesses;
- Mau is intermittently lucid rather than simply unconscious;
- body changes occur visibly during care;
- the larger family cannot immediately transport him;
- field stabilization conditions precede movement;
- road home remains slow;
- return to the inn is not a cognitive reset;
- Frieren can be recognized, forgotten, and re-recognized across the recovery;
- Rimuru reaches containment through questions / observation rather than instant solution;
- consent is delayed until a sustained clear window;
- Frieren's trust decision is separate from Mau's consent.

### The Noise / body / RCT
- The Noise remains a working designation, not an omniscient answer engine;
- containment improves observational access rather than magically explaining Mau;
- competing body-template adaptation is explicit;
- RCT is real but cannot perfectly repair toward a stable target when the whole template is unstable;
- stabilization toward arrival-state does not establish Mau's true original species;
- elf-like / long-lived adaptation remains hope, not a lifespan guarantee;
- the recovery date preserves:
  - "Then I'll remind you."
  - "As many as it takes."

### Move / Arrival House / city
- The Move is staged;
- old inn remains origin-home rather than being discarded;
- named G5 residents make non-identical choices;
- Arrival House grows from lived need;
- Searchers become a civic function rather than protagonist entourage;
- second community remains independent;
- Senku's later role is civic audit, not duplicate arrival;
- Maomao / Senku / Kusuri have distinct medicine / engineering / chemistry functions;
- systems are designed to survive their experts.

### Eren / law / agency
- Eren / Mikasa asymmetry does not erase individual agency;
- exit rights / appeal / due process remain material;
- Mau is not allowed to become civic infrastructure merely because he is useful.

### Last Defense
- combat is only one layer of defense;
- refuge / medical / information / infrastructure systems matter;
- Aira explicitly breaks the suppression construct;
- the city can "fail correctly";
- the device is traced through supply-chain manipulation without prematurely solving the mastermind;
- the later Noise overload is distinct from the Memory crisis;
- learned protocol is reused without assuming identical cause;
- Ori helps without becoming "reality itself" or Mau's sole metaphysical anchor.

### Goddess / Trial / Return-Stay
- Goddess authority is demonstrated as bounded domain authority rather than established omnipotence;
- the Trial does not reduce to a number of deaths;
- first deaths are individually lived;
- Rimuru / stranger / Frieren / Bocchi / Ori loops progressively expose Mau's agency problem;
- survival can be more punishing than dying;
- the exact loop count stays unresolved while the scale becomes hundreds;
- the Trial shifts from "why will you die?" toward "can you let other people choose?";
- Return and Stay remain morally open;
- individual terms remain private;
- the ten-day clock remains active;
- Mau's backdoor plan comes from Trial trauma interacting with his older self-sacrifice / control architecture;
- the family intercepts him before any Goddess contact;
- no collective request is made;
- no collective terms are shown;
- no binding divine agreement exists;
- S3 ends on Day 3 with seven days remaining;
- the first final individual choice belongs to S4.

## 8. Intentional unknowns

The following are **not holes** and must not be "repaired" by inventing answers:

- Mau's true origin;
- Mau's true baseline species;
- whether The Noise and memory manipulation share a source;
- exact Trial loop / death count;
- mastermind identity behind the wider anti-Otherworlder manipulation;
- most final Return/Stay decisions;
- long-term endpoint of Mau's adaptive biology.

## 9. Final production rule

For all future S3 work:

> **Latest merged branch state > filename suffix > old draft label.**

And:

> **Prior chat repair work must be preserved unless a later creator decision explicitly supersedes it.**

When a future correction is needed:
1. compare against the current merged chapter;
2. preserve lived prose already earned;
3. preserve downstream consequences;
4. add space instead of compressing;
5. update indexes / counts / handoff locks;
6. never rebuild from the old compressed v0.2 architecture.

## 10. Final result

Season 3 is now considered:

**continuity-merged, prior-chat-preserving, G5-integrated, full-prose-pass complete, and mechanically audited.**

Future changes should be treated as **new creator revisions**, not as completion of an unfinished compression pass.
