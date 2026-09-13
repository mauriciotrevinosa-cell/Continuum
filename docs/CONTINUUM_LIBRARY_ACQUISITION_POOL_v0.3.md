# Continuum — Mauricio Library Acquisition Pool v0.3

**Status:** Active personal Library acquisition reference  
**Date:** 2026-09-10  
**Scope:** Mauricio's current manga/manhwa acquisition order and related-work organization for `C:\ContinuumVault`  
**Supersedes:** `CONTINUUM_LIBRARY_ACQUISITION_POOL_v0.2.md`

This revision expands the acquisition map so sequels, prequels, alternate adaptations and useful official spin-offs are grouped under their parent source family instead of being modeled as unrelated top-level franchises.

## Core rules

```text
IN LIBRARY != IN THE ARRIVALS
FRANCHISE / SOURCE FAMILY != INDIVIDUAL WORK
RAW VAULT != REPO
RAW VAULT ORGANIZATION != CANON DECISION
```

`C:\ContinuumVault` remains local personal data outside the Git repository. This document records the intended personal acquisition structure only. Continuum runtime, migrations, tests, fixtures and first-run behavior must remain source-agnostic.

Do not interpret this list as a requirement to archive every parody, anthology, promo, guidebook or minor derivative ever published. Current target is:

1. main source work;
2. direct sequel/prequel;
3. alternate source adaptation when materially useful;
4. official spin-offs with meaningful character/world material;
5. low-value parody/anthology only if Mauricio later wants it.

Raw downloaded files remain untouched. Continuum will later hash, inspect, classify, deduplicate, extract and normalize them into derived data without modifying originals.

## Folder rule

When a family has multiple works in the same medium, use one child folder per work:

```text
C:\ContinuumVault\<Family>\manga\<Work>\raw files
C:\ContinuumVault\<Family>\manhwa\<Work>\raw files
```

For a family with only one work in that medium, existing files directly inside `manga`/`manhwa` do not need to be moved merely for cosmetic consistency.

On Windows, folder names must be sanitized only where required by illegal filename characters such as `:`, while preserving recognizable titles.

## Current manga/manhwa acquisition order — 48 source families

### 1. Frieren: Beyond Journey's End
- `Frieren Beyond Journey's End` — main manga.
- Current pass already acquired; do not reorganize merely for aesthetics.

### 2. Witch Hat Atelier
Acquire:
- `Witch Hat Atelier` — main manga.
- `Witch Hat Atelier Kitchen` — official culinary spin-off with recurring cast/world material.

### 3. Jujutsu Kaisen
Acquire:
- `Jujutsu Kaisen 0` — prequel.
- `Jujutsu Kaisen` — main manga.
- `Jujutsu Kaisen Modulo` — sequel/related continuation work.

`Jujutsu Kaisen Modulo` is no longer a separate top-level Vault family.

### 4. Dandadan
- `Dandadan` — main manga only for current pass.

### 5. Gachiakuta
- `Gachiakuta` — main manga only for current pass.

### 6. Chainsaw Man
- `Chainsaw Man` — main manga, including its internally divided parts; no separate folder is required merely because the manga has Parts 1/2.

### 7. That Time I Got Reincarnated as a Slime / Tensura
Acquire current high-value manga set:
- `That Time I Got Reincarnated as a Slime` — main manga adaptation.
- `The Slime Diaries` — daily-life/world spin-off.
- `Trinity in Tempest` — world/character spin-off.
- `The Ways of the Monster Nation` — world-travel/worldbuilding spin-off, if available from the user's source.
- `Clayman's Revenge` — alternate-timeline/character-focused spin-off, if available.

Do not currently chase every Tensura gag manga, anthology or promotional derivative.

### 8. The Apothecary Diaries
Acquire where available:
- `The Apothecary Diaries - Nekokurage` — Square Enix manga adaptation.
- `The Apothecary Diaries - Minoji Kurata` / `Maomao no Koukyuu Nazotoki Techou` — alternate manga adaptation of the same source novels.
- `The Apothecary Diaries - Xiaolan's Story` — official Xiaolan-focused spin-off; acquire when available in the user's preferred/accessible release.

The two main manga adaptations are parallel adaptations, not sequel/prequel branches.

### 9. SPY x FAMILY
- `SPY x FAMILY` — main manga only for current manga pass.

### 10. Bocchi the Rock!
Acquire:
- `Bocchi the Rock` — main manga.
- `Bocchi the Rock - Kikuri Hiroi's Heavy-Drinking Diary` — official Kikuri side story/spin-off.

### 11. Dr. STONE
Acquire:
- `Dr STONE` — main manga.
- `Dr STONE 4D Science` — official post-main limited continuation.
- `Dr STONE Reboot Byakuya` — official spin-off/reboot work; preserve separately so Source Intelligence can later record its authority/canon status instead of assuming equivalence with main canon.

### 12. Sakamoto Days
Acquire:
- `Sakamoto Days` — main manga.
- `Sakamoto Holidays` — official spin-off.

### 13. Solo Leveling
Under `manhwa`, acquire:
- `Solo Leveling` — main manhwa/webcomic.
- `Solo Leveling Ragnarok` — sequel manhwa/webcomic.

### 14. My Dress-Up Darling
- `My Dress-Up Darling` — main manga only for current pass.

### 15. Call of the Night
- `Call of the Night` — main manga only for current pass.

### 16. Dealing with Mikadono Sisters Is a Breeze
- Main manga only for current pass.

### 17. Miss Kobayashi's Dragon Maid
Acquire current high-value manga family:
- `Miss Kobayashi's Dragon Maid` — main manga.
- `Kanna's Daily Life` — Kanna spin-off.
- `Elma's Office Lady Diary` — Elma spin-off.
- `Lucoa is My xx` — Lucoa/Shouta spin-off.
- `Fafnir the Recluse` — Fafnir/Takiya spin-off.
- `Ilulu Doesn't Understand Love` — Ilulu/Taketo spin-off.

Official anthology material is optional, not required in the current pass.

### 18. Komi Can't Communicate
- Main manga only for current pass.

### 19. Attack on Titan
Acquire:
- `Attack on Titan` — main manga.
- `Attack on Titan No Regrets` — Levi/Erwin prequel.
- `Attack on Titan Before the Fall` — prequel.
- `Attack on Titan Lost Girls` — character-focused side/prequel material.

Parody works such as Junior High/Spoof material are optional for later, not current acquisition requirements.

### 20. The 100 Girlfriends Who Really, Really, Really, Really, Really Love You
- Main manga only for current pass.

### 21. Tokyo Ghoul
Acquire:
- `Tokyo Ghoul` — main first series.
- `Tokyo Ghoul re` — direct sequel.
- `Tokyo Ghoul Jack` — official prequel.

Short one-shot/bonus material can remain with the closest parent work unless it clearly needs its own work folder.

### 22. BOFURI
- Main manga adaptation for current pass. Light novels belong to the later/light-novel acquisition pass.

### 23. Kagurabachi
- Main manga only for current pass.

### 24. MarriageToxin
- Main manga only for current pass.

### 25. KonoSuba
Acquire current high-value manga set where available:
- `KonoSuba` — main manga adaptation.
- `KonoSuba An Explosion on This Wonderful World` — Megumin prequel manga.
- `KonoSuba Continued Explosions` / `Even More Explosions on This Wonderful World` — later Megumin/Yunyun spin-off manga, if available.
- `KonoSuba Extra Attention to That Wonderful Fool` — Dust-focused manga adaptation, if available.
- `KonoSuba Consulting With This Masked Devil` — Vanir-focused manga adaptation, if available.

Game manga, anthology and gag-only derivatives are not required for the current pass.

### 26. My Deer Friend Nokotan
- Main manga only for current pass.

### 27. You and I Are Polar Opposites
- Main manga only for current pass.

### 28. Horimiya
- `Horimiya` — main serialized manga adaptation for current pass.
- The original `Hori-san to Miyamura-kun` webcomic may be added later as a separate source work if easily available; it is not required to block the current manga pass.

### 29. I Made Friends with the Second Prettiest Girl in My Class
- Main manga adaptation for current pass.

### 30. Food for the Soul
- Main manga/source adaptation available to the user; no additional related work required for current pass.

### 31. Alya Sometimes Hides Her Feelings in Russian
- Main manga adaptation for current pass.

### 32. With You and the Rain
- Main manga only for current pass.

### 33. Smoking Behind the Supermarket with You
- Main manga only for current pass.

### 34. The Angel Next Door Spoils Me Rotten
- Main manga adaptation for current pass.

### 35. Haimiya-senpai Is Scary and Cute
- Main manga only for current pass.

### 36. Lil' Miss Vampire Can't Suck Right
- Main manga only for current pass.

### 37. The Brilliant Healer's New Life in the Shadows
- Main manga adaptation for current pass.

### 38. Rich Girl Caretaker
- Main manga adaptation/source work available to the user for current pass.

### 39. Oh Boy, Was I Wrong About Her
- Main manga/source work available to the user for current pass.

### 40. The Quintessential Quintuplets
- Main manga only for current pass.
- Anime-original/special continuation material belongs to the later anime pass, not this manga pass.

### 41. Kaguya-sama: Love Is War
Acquire:
- `Kaguya-sama Love Is War` — main manga.
- `We Want to Talk About Kaguya` — official spin-off focused on side characters/events around the main story.

Official doujin/parody material is optional and not required for current pass.

### 42. MASHLE: Magic and Muscles
- Main manga only for current pass.

### 43. The Healer Who Was Banished from His Party, Is, in Fact, the Strongest
- Main manga adaptation for current pass.

### 44. Welcome to the Outcast's Restaurant!
- Main manga adaptation for current pass.

### 45. My Status as an Assassin Obviously Exceeds the Hero's
- Main manga adaptation for current pass.

### 46. Am I Actually the Strongest?
- Main manga adaptation for current pass.

### 47. The Unaware Atelier Master
- Main manga adaptation for current pass.

### 48. My Ribdiculous Reincarnation
- Main manga/source work available to the user for current pass.

## Discovery rule during acquisition

If Mauricio encounters a title not listed above that clearly belongs to one of these families, do not guess or create another top-level family immediately.

First classify it as one of:

```text
main source
prequel
sequel
parallel/alternate adaptation
official spin-off
anthology/parody
fan work
unknown
```

Meaningful source/prequel/sequel/spin-off material can receive a child work folder. Anthology/parody/promotional material is optional unless Mauricio specifically wants it.

## Non-destructive migration rule

The existing 49-folder personal scaffold may contain older top-level folders that are now understood as child works, especially `Jujutsu Kaisen Modulo`.

Do not delete or overwrite them automatically.

A local maintenance step may:

1. create the new target child folders;
2. move existing content only after verifying source and destination;
3. preserve filename collisions by renaming the incoming duplicate rather than overwriting;
4. leave raw media untouched internally;
5. report exactly what moved/created/skipped.

## Relationship to future Continuum ingestion

This personal filesystem is only an acquisition convenience. Phase 1 should eventually discover arbitrary families/works and store explicit relationships in metadata/database structures rather than inferring canon solely from folder paths.
