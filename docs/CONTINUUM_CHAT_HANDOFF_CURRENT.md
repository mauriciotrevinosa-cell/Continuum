# Continuum — Current Chat Handoff

**Purpose:** Fast continuation context for a new ChatGPT conversation when the previous thread reaches its length limit.
**Status:** Current working handoff; update as major decisions change.

## 1. Product identity

Continuum and The Arrivals are separate things.

```text
CONTINUUM = app / creative studio / engine
THE ARRIVALS = one project created inside Continuum
```

The Arrivals is still the flagship personal project and is NOT abandoned. Continuum must remain generic enough for other users and other projects, including single-franchise continuations, alternate endings, What Ifs, or unrelated crossovers.

Relevant docs:
- `docs/CONTINUUM_PRODUCT_PROJECT_MODEL_v0.1.md`
- `docs/creative/THE_ARRIVALS_CREATIVE_DIRECTION_v0.2.md`
- `docs/CONTINUUM_LIBRARY_ACQUISITION_POOL_v0.1.md`

## 2. Sharing direction

Approved direction so far:
- Projects should eventually be exportable/importable between users/installations.
- A recipient should get an independent local copy/fork, not mutate the sender's project.
- Project packages should reference source dependencies rather than assume raw commercial media is bundled.
- Library membership does not imply project membership.

Pending discussion to resume:
- User proposed a more social model inside Continuum: friends, chat, project sharing, a `Shared with me` area, and the ability to save/import projects received from friends.
- This has NOT yet been fully designed or locked; resume from this idea in the next conversation.

## 3. The Arrivals creative state

The Arrivals creative direction is already high-confidence and mostly shaped, though still needs polishing before final canon lock.

Important preserved ideas include:
- Avatar/MC is concept-level canon and will be visually based on the user's appearance.
- MC arrives with amnesia and develops via `OBSERVE → UNDERSTAND → EVOLVE / CONSTRUCT`.
- Systems such as Mana and Cursed Energy can begin at zero and remain separate until earned compatibility/conversion exists.
- Six Eyes / Limitless example is preserved as the detailed model for learning powerful systems without effortless copying.
- Opening Cohort size is user-decided.
- Arrivals continue over a long-running arc; some characters arrive together, alone, or remain undiscovered for long periods.
- World growth: `camp → settlement → town → port → city → autonomous territory / nation`.
- Pillars are descriptive, not restrictive; later franchises may materially change ecology, politics, economy, magic, security, culture, etc.
- Otherworlders can be socially generalized and discriminated against even though they belong to different factions/worlds.
- Fear can create a reinforcing loop with curses/devils/anomalous phenomena.
- Not every episode must move the main plot; slice-of-life, relationship, infrastructure, craft, culture, recovery, and planning episodes can be substantive.
- Consequences should retain emotional weight; time travel/reset should not cheaply erase lived history.
- Character-specific Continuum overrides can later choose source snapshot, memory state, younger/older body, powers, and other arrival-state changes while preserving Source Canon separately.

## 4. Current Library/Vault work

Physical personal Vault root:

```text
C:\ContinuumVault
```

Claude created a scaffold with 49 active franchise folders. This is Mauricio's personal acquisition Vault, not a generic Continuum default.

Current user task: acquire source material, starting with manga/manhwa, then anime and other primary sources.

The user asked for one complete ordered manga/manhwa acquisition list 1–49 so nothing is left half-finished. Current acquisition strategy:
- download primary manga/manhwa/source material in priority order;
- do not waste time manually renaming, cropping, extracting, or restructuring files;
- put files in the appropriate existing franchise/media folder;
- later Continuum will normalize/inspect/register sources;
- fan art and optional extras can be added gradually after core source material.

Language preference:
- English is fully acceptable for manga/LN/subtitles.
- Japanese audio + subtitles is fine.
- English dub is also a valid and sometimes preferred performance source; e.g. the user prefers Frieren's English voice performance.

## 5. Current personal Library pool

Current active pool: 49 titles.

Favorites: 17
Likes: 22
Meh: 10
Cyberpunk: Edgerunners is outside for now because the user has not watched it yet.

Use `docs/CONTINUUM_LIBRARY_ACQUISITION_POOL_v0.1.md` for the exact current list and taste grouping.

Important clarification:
- `MEH` means current personal enthusiasm, not low narrative utility or removal.
- Dr. STONE is personally MEH largely because of dissatisfaction with its late time-machine implication, but its characters/worldbuilding utility is considered very high.
- Dealing with Mikadono Sisters Is a Breeze is in FAVORITES.

## 6. Development state

Phase 0 foundation implementation is effectively complete pending formal closure/integration/tagging. Do not silently skip the formal close.

Phase 1 is Library/Vault.

The current strategy is app-first, but source acquisition can happen in parallel once the Vault scaffold exists.

Continuum must remain franchise-agnostic at runtime. The 49-title pool must never become seed data or hardcoded application logic.

## 7. Response style / working style

- Default to Spanish.
- Be direct, practical, and collaborative.
- Prefer root-cause architecture over patches.
- Do not re-explain settled concepts unless needed.
- When giving PowerShell commands, make them exact and copy-pasteable.
- Preserve the distinction between `Continuum` as product and `The Arrivals` as a project.
- The user likes ideation where the assistant proposes an initial organization and the user corrects/approves it.

## 8. Immediate next step in the new chat

When the user starts the next conversation, resume without making them restate the project.

Suggested first instruction from the user:

> Continue Continuum from `docs/CONTINUUM_CHAT_HANDOFF_CURRENT.md`. Read the product/project model, The Arrivals creative direction v0.2, and the Library acquisition pool. We were in the middle of acquiring manga/source material and also had a pending idea for friends/chat/project sharing and a `Shared with me` area.

Then continue from whichever of those two threads the user chooses.
