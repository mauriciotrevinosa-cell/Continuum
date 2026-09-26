# The Arrivals — Branch Archaeology + Story Stop-Save Protocol v0.1

**Status:** ACTIVE WORKFLOW / ARCHAEOLOGY CHECKPOINT  
**Date:** 2026-09-26  
**Primary branch:** `m3/critical-path`

## 1. Why this exists

The Arrivals now spans many chats, historical Git branches, approved S1 material, S2 development and future-arc seeds.

A decision can be lost operationally even when it still exists somewhere in Git history.

This document establishes two protections:

1. **branch archaeology** — older branches remain searchable provenance and must be checked before declaring an inventory complete;
2. **story stop-save** — once a discussion becomes defined enough to affect future continuity, save it to Git before moving on.

The goal is not to turn every brainstorm sentence into canon.

The goal is to prevent already-developed ideas from becoming invisible.

---

## 2. Branch archaeology performed on 2026-09-26

All currently visible repository branches were reviewed at branch level.

### No unique later story work found

The following relevant branches are ancestors / fully behind `m3/critical-path` with no unique story commits that need recovery:

- `docs/the-arrivals-brainstorm-v0.3`
- `creative/s1e1-manga-panel-script-v0.1`
- `creative/origami-girl-reference-v0.1`
- `m2/closeout`
- `master`

Other divergent docs/audit/phase branches contain implementation, foundation, franchise-pool or source-vault material rather than hidden S2 narrative.

### Main historical creative branch

`creative/s1-season-board-v0.1` is the important divergent historical story branch.

It contains substantial S1 production history and early/future story development.

The current story-board reorganization did **not** lose the principal S2 story documents.

The following major S2/future documents were compared between the old branch and `m3/critical-path` and are identical:

- `THE_ARRIVALS_FRIEREN_FIRST_LOVE_CLARIFICATION_v0.1.md`
- `THE_ARRIVALS_FUTURE_FRIEREN_HIMMEL_MAU_ARC_SEED_v0.1.md`
- `THE_ARRIVALS_FUTURE_IDEAS_BOARD_v0.1.md`
- `THE_ARRIVALS_GROUP3_DIRECTION_v0.1.md`
- `THE_ARRIVALS_MAU_FRIEREN_POST_REVIVAL_PROMISE_BEAT_v0.1.md`
- `THE_ARRIVALS_MAU_POWER_SECRECY_AND_POST_SUKUNA_PROGRESSION_v0.1.md`
- `THE_ARRIVALS_S1_S2_EPISODE_STATUS_OVERVIEW_v0.1.md`
- `THE_ARRIVALS_S1_S2_G3_HANDOFF_v0.1.md`
- `THE_ARRIVALS_S2_SUKUNA_SECOND_CHANCE_MAJOR_ARC_SEED_v0.1.md`

`THE_ARRIVALS_MAIN_STORY_SPINE_v0.1.md` differs because the current version intentionally refines the city timing:
- older version leaned toward S2 founding/building more of the city;
- current version moves most large-scale city construction into S3 while keeping fortification/search/first move in S2.

That is an intentional later refinement, not accidental loss.

---

## 3. Confirmed branch-only material recovered now

Three documents were confirmed important enough to restore into the active branch:

### Mau/Frieren clothing callbacks

`THE_ARRIVALS_MAU_FRIEREN_CLOTHING_CALLBACKS_AND_E18_WARDROBE_BEAT_v0.1.md`

This approved addendum had not been fully integrated into the current S1 manga scripts.

It preserves:
- casual clothing borrowing before separation;
- the missing-item callback during separation;
- post-reconciliation hoodie callback;
- E18's Mau-coded clothing as an exaggeration of existing behavior rather than chocolate creating new desire.

It is now preserved in the story-board sources for the final S1 audit.

### E14 sunset / brooch callback

`THE_ARRIVALS_S1E14_SUNSET_BROOCH_VISUAL_CALLBACK_ADDENDUM_v0.1.md`

This locked visual addendum was not represented in the current E14 manga panel script.

It preserves:
- sunset/golden-hour staging;
- Frieren's Fern-reunion ornament/brooch visible while resting on Mau;
- coexistence of Fern and Mau in Frieren's emotional life rather than replacement.

It is now preserved in story-board sources for the final S1 audit.

### Creative change propagation rule

`THE_ARRIVALS_M3_CREATIVE_CHANGE_PROPAGATION_RULE_v0.1.md`

This approved workflow rule was branch-only.

It is now restored to `m3/critical-path`.

Core rule:

> **A later correction replaces only the semantic node it actually changes. Do not discard compatible upstream/downstream material simply because one older detail was superseded.**

This is the formal protection for surgical supersession.

---

## 4. Branch-only S1 notes that are already reflected in current scripts

Some historical correction files remain only on the old branch but their actual decisions are already present in current Level-4 material.

Examples verified during this audit:

### E16 Otherworlder origin correction

Historical note:
`THE_ARRIVALS_S1E16_OTHERWORLDERS_ORIGIN_CORRECTION_v0.1.md`

Current E16 manga script already preserves:
- Otherworlder is coined here;
- neutral/new term;
- no prior registry/history/known recurring Otherworlder bureaucracy.

### E19 Okarun memory + G3 grouping correction

Historical note:
`THE_ARRIVALS_S1E19_OKARUN_MEMORY_AND_G3_GROUPS_REVISION_v0.1.md`

Current E19 manga script already preserves:
- fixed G3 travel groupings;
- Okarun knows there is an important missing person;
- he cannot retrieve name/face/identity;
- the absence itself is real to him.

These historical notes do not need to override current scripts, but remain useful provenance.

---

## 5. Remaining old-branch S1 files

The old creative branch still contains:
- green-light/voice-check records;
- corrections;
- cinematic breathing passes;
- wardrobe notes;
- editorial/process documents;
- older spatial bible revisions;
- production checkpoints.

Many current drafts/manga scripts/editorial overviews were successfully reorganized under:
`docs/creative/the_arrivals_story_board/s1/`.

The remaining branch-only S1 files are **not assumed irrelevant**.

Before the final S1 story/pacing audit is declared complete:

> perform a final historical-addenda sweep against `creative/s1-season-board-v0.1`.

This is now a required audit step.

Do not delete the historical creative branch before that sweep is complete.

---

# 6. Story Stop-Save protocol

## 6.1 When to save

Create a Git stop-save when a conversation reaches any of these thresholds:

- a character/group roster becomes a strong working choice;
- an arc's cause → consequence structure becomes understandable;
- a relationship direction affects later payoffs;
- a future scene is referenced by multiple later ideas;
- a power/world rule will constrain future writing;
- a correction supersedes an older node;
- a brainstorm has accumulated enough detail that losing it would force re-invention;
- the creator says some equivalent of “me gusta / así / déjalo / eso funciona” **and** the idea has meaningful downstream continuity.

Do **not** save every stray possibility as canon.

---

## 6.2 Status labels

Every stop-save must state its confidence.

Use:

### `BRAINSTORM / RESERVOIR`
Interesting idea. Preserve it, but it does not constrain future writing yet.

### `STRONG DIRECTION / DETAILS OPEN`
The concept/function is wanted. Exact wording, scene mechanics or placement can change.

### `DEFINED / HIGH-CONFIDENCE`
The causal/story decision is substantially decided even if scripting remains.

### `LOCKED / PRODUCTION SOURCE`
Approved material that downstream production should follow until explicitly revised.

Never silently upgrade one status into another.

---

## 6.3 What a stop-save records

At minimum:

- date;
- scope / arc;
- status;
- what was decided;
- what remains open;
- downstream consequences;
- contradictions or older nodes affected;
- whether the new decision replaces only one node or an entire branch;
- source/provenance when it came from an older file/branch.

---

## 6.4 Surgical supersession

Default rule:

> **Replace the smallest semantic unit necessary. Preserve everything else that still works.**

Example already established:
- old recovery version had Mau verbally mirror `I love you`;
- newer decision removes only that mirrored line;
- recovery, kiss, Frieren confession and surrounding relationship arc remain.

Never interpret:
> “this line changed”

as:
> “that whole document/arc is wrong.”

---

## 6.5 Conversation workflow

During active brainstorming:

```text
brainstorm freely
→ idea gains shape
→ discuss/refine
→ reaches stop-save threshold
→ write/update Git checkpoint
→ continue brainstorming
```

Do not interrupt every few messages to save.

Save at natural conceptual stopping points.

If several tightly connected ideas are developed in one session, save them together as one coherent checkpoint rather than creating dozens of tiny files.

---

## 6.6 Before major planning transitions

Mandatory stop-save/checkpoint before:

- moving from one major S2 block to another;
- turning block inventory into episode outline;
- beginning definitive S2 scripts;
- beginning final S1 audit;
- promoting future/S3 material into active S2 continuity;
- changing major group membership;
- changing a relationship endpoint;
- changing a core power/world rule.

---

# 7. Immediate current source of truth for S2 accumulation

Use:

`docs/creative/the_arrivals_story_board/S2_COMPLETE_CONTINUITY_INVENTORY_v0.1.md`

as the active accumulation document while S2 is still being assembled.

It should contain:
- what we already know;
- strong directions;
- open details;
- real gaps;
- post-Sukuna material that belongs in S2;
- explicit supersessions.

It is **not** an episode lock.

When a discussion adds enough defined S2 material, update that inventory as the stop-save.

---

# 8. Confidence statement

After this branch review:

- there is **no evidence of a separate hidden S2 outline/major arc branch** that the current `m3` story board failed to migrate;
- the major historical S2 documents are present in the active branch;
- some S1 addenda/workflow records did remain branch-only, which is why the final S1 audit must include the historical-addenda sweep;
- future story sessions should use the stop-save protocol so new developed ideas do not remain only in chat memory.
