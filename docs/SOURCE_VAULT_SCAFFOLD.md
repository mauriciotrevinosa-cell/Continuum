# Source Vault — acquisition scaffold

**Status:** Active operational reference
**Date:** 2026-09-09
**Scope:** Filesystem layout for human acquisition of source material. This is
**not** application seed data, and nothing here is franchise logic in code.

Derived from `CONTINUUM_FRANCHISE_MASTER_POOL_v0.3.md` (49 active franchises).

---

## The Vault is not in this repository, and never will be

```
C:\ContinuumVault          <- the Vault (source media)
C:\Continuum               <- this git repository
C:\ContinuumData           <- application-managed data and reports
```

Three separate roots, deliberately:

1. The Vault will hold licensed manga, manhwa, novels and anime. **That must
   never reach version control**, GitHub least of all.
2. ADR-0001 and FOUNDATION_APPROVAL amendment A-01 make the Vault
   structurally read-only from Continuum — it is never written to, not even
   diagnostically. A path inside the working tree would put it one careless
   `git add` away from being modified.
3. Reports and metadata stay in `C:\ContinuumData`, never inside the Vault.

`C:\Continuum\Vault` must not exist. The `.gitignore` in this repository
refuses `Vault/` and `ContinuumVault/` as a second line of defence.

---

## Layout

One folder per franchise, then one folder per source medium that **actually
exists**, plus `fan-art` everywhere.

```
C:\ContinuumVault\
    Frieren - Beyond Journey's End\
        manga\
        anime\
        fan-art\
    Solo Leveling\
        web-novel\
        manhwa\
        anime\
        fan-art\
```

Rules that produced it:

- **No empty categories for symmetry.** A franchise with only a manga gets
  `manga` and `fan-art`, nothing else. An absent folder is information: it
  says the medium does not exist yet.
- **No season, volume or chapter folders.** Drop a ZIP, CBZ, PDF, episode or
  whole season folder straight into the medium folder. Normalisation is
  Continuum's job later, not the human's now.
- **No language or subtitle folders.** An anime file may carry Japanese audio,
  an English dub, dual audio or embedded subtitles; all are valid. External
  `.srt`/`.ass` files live beside the video they belong to.
- **English dub is not inferior source material.** Performance preference is a
  legitimate authority signal — Frieren's English performance is the reference
  the user prefers, and the Vault must not encode a bias against it.
- **No artbooks, guidebooks, key visuals, interviews, model sheets, promos,
  OSTs or drama CDs.** Not part of the current acquisition target. If
  something genuinely useful turns up, a folder can be added then.

Windows-invalid characters are replaced consistently: `:` becomes ` - `, and
`?` is dropped. `×` is written `x` so it can be typed into a Save As dialog.

---

## Media map

49 franchises. `fan-art` is present in all of them and is omitted below.

### Favorites (17)

| Franchise | Source media |
|---|---|
| Bocchi the Rock! | manga, anime |
| Dandadan | manga, anime |
| SPY x FAMILY | manga, anime |
| Witch Hat Atelier | manga, anime |
| Solo Leveling | web-novel, manhwa, anime |
| Jujutsu Kaisen | manga, anime |
| Jujutsu Kaisen Modulo | manga |
| Frieren - Beyond Journey's End | manga, anime |
| The Apothecary Diaries | light-novel, manga, anime |
| That Time I Got Reincarnated as a Slime | web-novel, light-novel, manga, anime |
| Gachiakuta | manga, anime |
| Miss Kobayashi's Dragon Maid | manga, anime |
| Call of the Night | manga, anime |
| Dealing with Mikadono Sisters Is a Breeze | manga, anime |
| My Dress-Up Darling | manga, anime |
| Komi Can't Communicate | manga, anime |
| My Deer Friend Nokotan | manga, anime |

### Likes (22)

| Franchise | Source media |
|---|---|
| Sakamoto Days | manga, anime |
| Attack on Titan | manga, anime |
| With You and the Rain | manga, anime |
| Chainsaw Man | manga, anime |
| Smoking Behind the Supermarket with You | manga, anime |
| You and I Are Polar Opposites | manga, anime |
| I Made Friends with the Second Prettiest Girl in My Class | web-novel, light-novel, manga, anime |
| The Brilliant Healer's New Life in the Shadows | web-novel, light-novel, manga, anime |
| MarriageToxin | manga, anime |
| Food for the Soul | anime, manga |
| The Angel Next Door Spoils Me Rotten | web-novel, light-novel, manga, anime |
| Alya Sometimes Hides Her Feelings in Russian | light-novel, manga, anime |
| BOFURI - I Don't Want to Get Hurt, so I'll Max Out My Defense | web-novel, light-novel, manga, anime |
| Lil' Miss Vampire Can't Suck Right | manga, anime |
| KonoSuba | web-novel, light-novel, manga, anime |
| Tokyo Ghoul | manga, anime |
| Rich Girl Caretaker | web-novel, light-novel, manga, anime |
| Oh Boy, Was I Wrong About Her | web-novel, light-novel, manga, anime |
| Horimiya | manga, anime |
| The 100 Girlfriends Who Really, Really, Really, Really, Really Love You | manga, anime |
| Kagurabachi | manga |
| Haimiya-senpai Is Scary and Cute | manga |

### Meh (10)

| Franchise | Source media |
|---|---|
| Kaguya-sama - Love Is War | manga, anime |
| The Quintessential Quintuplets | manga, anime |
| The Healer Who Was Banished from His Party, Is, in Fact, the Strongest | web-novel, light-novel, manga, anime |
| Welcome to the Outcast's Restaurant! | web-novel, light-novel, manga, anime |
| Dr. STONE | manga, anime |
| MASHLE - Magic and Muscles | manga, anime |
| My Status as an Assassin Obviously Exceeds the Hero's | web-novel, light-novel, manga, anime |
| Am I Actually the Strongest | web-novel, light-novel, manga, anime |
| My Ridiculous Reincarnation | web-novel, light-novel, anime |
| The Unaware Atelier Master | web-novel, light-novel, manga, anime |

**Cyberpunk: Edgerunners has no folder.** It is `OUT FOR NOW` in the v0.3 pool
because the user has not watched it. Not a permanent exclusion.

---

## Findings that changed the layout

The pool document records taste, not media. Media types were verified rather
than assumed; these are the cases where verification changed the answer.

- **Jujutsu Kaisen Modulo** — manga only. A sequel by Gege Akutami with art by
  Yuji Iwasaki, serialised in Weekly Shōnen Jump from September 2025 to March
  2026. No anime, no light novel.
- **Haimiya-senpai Is Scary and Cute** — manga only. Began on Square Enix's
  Manga Up! in November 2025. No anime adaptation announced.
- **Kagurabachi** — manga only *for now*. The anime is real but premieres in
  **April 2027** (studio Cypic). An `anime` folder today would sit empty for a
  year, so it was not created. Add it when acquisition becomes possible.
- **My Ridiculous Reincarnation** — no `manga` folder. The manga adaptation is
  announced but not yet serialised. Web novel, light novel and anime exist.
- **Food for the Soul** — an **original anime** by Atto (Non Non Biyori) at
  P.A. Works; the manga is the adaptation, not the source. `anime` is listed
  first for that reason.
- **Solo Leveling** — `manhwa`, not `manga`, and the original is a Korean web
  novel. No `manga` folder exists or should.
- **Witch Hat Atelier** — the anime aired April–June 2026, so `anime` is real
  rather than aspirational.

Eight titles turned out to be full web novel → light novel → manga → anime
chains: Rich Girl Caretaker, Oh Boy Was I Wrong About Her, The Brilliant
Healer's New Life in the Shadows, I Made Friends with the Second Prettiest
Girl in My Class, Welcome to the Outcast's Restaurant!, My Status as an
Assassin Obviously Exceeds the Hero's, Am I Actually the Strongest, and The
Unaware Atelier Master.

---

## Open items

1. **Alya Sometimes Hides Her Feelings in Russian** — `web-novel` was **not**
   created. The series is widely documented as a light novel by SunSunSun, and
   a Kakuyomu web-novel origin could not be confirmed. Rather than invent the
   folder, it is left out pending confirmation.
2. **Lil' Miss Vampire Can't Suck Right** — the folder uses the pool
   document's spelling. The official English title is **Li'l** Miss Vampire
   Can't Suck Right.
3. **My Ridiculous Reincarnation** — the folder uses the pool document's
   spelling. The official English title is **My Ribdiculous Reincarnation**,
   a deliberate pun: the protagonist reincarnates as a hero's *rib*.
4. **Am I Actually the Strongest** — the trailing `?` of the real title is
   dropped because Windows forbids it in a directory name.
5. **Tokyo Ghoul** — `manga` and `anime` only. Official spin-off novels exist
   but are not primary source material; add `novel` if they become relevant.

---

## Re-running

`scripts/scaffold_source_vault.ps1` is idempotent and non-destructive. It only
ever calls `New-Item -ItemType Directory` for paths that do not exist. It never
deletes, renames, moves, hashes, converts or writes files, and it does not
touch existing media.

```powershell
.\scripts\scaffold_source_vault.ps1
```

Verified: a second run creates **0** directories and reports 224 already
present. It writes its report to `C:\ContinuumData\vault-scaffold-report.txt`,
outside the Vault.

Adding a franchise later means adding one line to the `$Pool` table and
re-running; existing folders and any media already in them are untouched.
