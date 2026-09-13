# Continuum — Mauricio Library Acquisition Pool v0.2

**Status:** Active personal Library acquisition reference  
**Date:** 2026-09-10  
**Scope:** Mauricio's current source-acquisition pool and raw Vault organization for `C:\ContinuumVault`  
**Supersedes:** `CONTINUUM_LIBRARY_ACQUISITION_POOL_v0.1.md`

This revision fixes an important modeling ambiguity discovered during source acquisition: a franchise/source family is not always the same thing as one individual manga, sequel, prequel, spin-off, adaptation, or side story.

## Core rules

```text
IN LIBRARY != IN THE ARRIVALS
FRANCHISE / SOURCE FAMILY != INDIVIDUAL WORK
RAW VAULT ORGANIZATION != APPLICATION CANON DECISION
```

The Library belongs to the user. Projects later choose what they use.

A single franchise/source family may contain multiple distinct works. Those works should not automatically become separate top-level Vault franchises just because they have separate titles.

## Vault hierarchy

Preferred raw layout:

```text
C:\ContinuumVault\
  <franchise-or-source-family>\
    manga\
      <work-or-series>\
        raw files / ZIP / CBZ / folders
    manhwa\
      <work-or-series>\
    light-novel\
      <work-or-series>\
    web-novel\
      <work-or-series>\
    anime\
      <work-or-series-or-adaptation>\
    fan-art\
```

The `<work-or-series>` level exists to disambiguate multiple works of the same medium inside one family. It is not a requirement to hand-normalize chapters, volumes, seasons, filenames, or releases.

Raw downloaded files remain preserved as received. Continuum should later hash, inspect, deduplicate, classify, extract and normalize them into derived data without modifying the originals.

## Important examples

### Witch Hat Atelier family

```text
C:\ContinuumVault\Witch Hat Atelier\
  manga\
    Witch Hat Atelier\
    Witch Hat Atelier Kitchen\
  anime\
  fan-art\
```

`Witch Hat Atelier Kitchen` is an official spin-off and should be acquired as a distinct work under the same Witch Hat Atelier source family, not as a separate top-level franchise.

Its authority/canon relationship to the main series can be labeled later by Source Intelligence; physical co-location does not silently declare every detail main-series canon.

### Jujutsu Kaisen family

```text
C:\ContinuumVault\Jujutsu Kaisen\
  manga\
    Jujutsu Kaisen 0\
    Jujutsu Kaisen\
    Jujutsu Kaisen Modulo\
  anime\
    Jujutsu Kaisen 0\
    Jujutsu Kaisen\
  fan-art\
```

`Jujutsu Kaisen 0` is the official prequel and should be treated as an essential source work in the Jujutsu Kaisen family.

`Jujutsu Kaisen Modulo` should remain a desired source work, but it should no longer be modeled as a separate top-level Vault franchise. It belongs under the Jujutsu Kaisen family.

If an older personal Vault scaffold already contains a top-level `Jujutsu Kaisen Modulo` directory, that is a scaffold artifact and may be migrated non-destructively into `Jujutsu Kaisen\manga\Jujutsu Kaisen Modulo` when convenient.

## Acquisition policy for related works

Do **not** interpret "collect the franchise" as "hunt every piece of derivative media ever published."

For each franchise/source family, prioritize:

1. main source work(s);
2. direct prequels/sequels that materially affect source continuity or characters;
3. official spin-offs with meaningful character/world material;
4. anime/adaptation material planned for the anime acquisition pass;
5. fan art gradually over time.

Low-value parody, promotional, guidebook, anthology, crossover, merchandise-only or highly peripheral material is optional unless Mauricio specifically wants it or it becomes useful.

This keeps acquisition comprehensive enough for Continuum without turning the Vault-filling phase into an exhaustive archival project.

## Current immediate acquisition order by source family

The practical order remains based on the earlier 49-title list, but related works are folded into their parent family when encountered.

1. Frieren: Beyond Journey's End — main manga completed for current acquisition pass
2. Witch Hat Atelier — acquire `Witch Hat Atelier` + `Witch Hat Atelier Kitchen`
3. Jujutsu Kaisen — acquire `Jujutsu Kaisen 0` + `Jujutsu Kaisen` + `Jujutsu Kaisen Modulo`
4. Dandadan
5. Gachiakuta
6. Chainsaw Man
7. That Time I Got Reincarnated as a Slime
8. The Apothecary Diaries
9. SPY×FAMILY
10. Bocchi the Rock!
11. Dr. STONE
12. Sakamoto Days
13. Solo Leveling — manhwa
14. My Dress-Up Darling
15. Call of the Night
16. Dealing with Mikadono Sisters Is a Breeze
17. Miss Kobayashi's Dragon Maid
18. Komi Can't Communicate
19. Attack on Titan
20. The 100 Girlfriends Who Really, Really, Really, Really, Really Love You
21. Tokyo Ghoul
22. BOFURI: I Don't Want to Get Hurt, so I'll Max Out My Defense
23. Kagurabachi
24. MarriageToxin
25. KonoSuba
26. My Deer Friend Nokotan
27. You and I Are Polar Opposites
28. Horimiya
29. I Made Friends with the Second Prettiest Girl in My Class
30. Food for the Soul
31. Alya Sometimes Hides Her Feelings in Russian
32. With You and the Rain
33. Smoking Behind the Supermarket with You
34. The Angel Next Door Spoils Me Rotten
35. Haimiya-senpai Is Scary and Cute
36. Lil' Miss Vampire Can't Suck Right
37. The Brilliant Healer's New Life in the Shadows
38. Rich Girl Caretaker
39. Oh Boy, Was I Wrong About Her
40. The Quintessential Quintuplets
41. Kaguya-sama: Love Is War
42. MASHLE: Magic and Muscles
43. The Healer Who Was Banished from His Party, Is, in Fact, the Strongest
44. Welcome to the Outcast's Restaurant!
45. My Status as an Assassin Obviously Exceeds the Hero's
46. Am I Actually the Strongest?
47. The Unaware Atelier Master
48. My Ribdiculous Reincarnation

The apparent change from 49 tasks to 48 source-family tasks is intentional: `Jujutsu Kaisen Modulo` is no longer counted as an independent top-level family. The number of individual works being acquired can be greater than 49 because a family may contain multiple works.

The old count was an acquisition convenience, not a technical or creative limit.

## Growth / discovery rule

When acquisition reaches a franchise and reveals a relevant sequel, prequel, alternate adaptation, or spin-off, evaluate it as a child work of that family before creating a new top-level Vault root.

Create a separate top-level family only when the work is genuinely independent enough that treating it as part of the same source family would be misleading.

Continuum runtime must never hardcode this personal hierarchy. Phase 1 should discover/register arbitrary source families and works from user data.

## Relationship to source canon and projects

Filesystem hierarchy does not itself determine canon authority.

Later Source Intelligence should be able to label each work/release with provenance and relationship such as main source, prequel, sequel, official spin-off, alternate adaptation, anthology, fan material, or unknown.

Projects then decide which source works/snapshots they actually use without rewriting the immutable source record.
