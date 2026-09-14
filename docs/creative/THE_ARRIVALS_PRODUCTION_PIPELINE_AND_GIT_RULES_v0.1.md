# The Arrivals — Production Pipeline & Git Rules v0.1

**Status:** AUTHORITATIVE WORKFLOW / PROJECT RULE
**Date:** 2026-09-14
**Project:** `The Arrivals`
**Branch:** `creative/s1-season-board-v0.1`

## 1. Non-negotiable persistence rule

All meaningful creative, production, continuity, workflow, and pipeline decisions must be committed to Git.

Chat is not the source of truth.

If a conversation becomes too long, resets, or contains an error, project progress must still be recoverable from Git alone.

Therefore:

- approved story decisions are written to project documents;
- status changes are committed;
- production-readiness changes are committed;
- corrections supersede older decisions explicitly rather than relying on chat memory;
- important UI/pipeline decisions are also documented in Git;
- when two documents conflict, precedence/status must be explicit.

## 2. Episode production pipeline

Use the following five-stage workflow for `The Arrivals`.

### Stage 1 — Story / Structure Review

Human-involved.

Goal:
- verify the episode's main idea;
- verify scene order / major beats;
- verify important interactions;
- catch real structural holes;
- avoid reopening already-settled material without a continuity, pacing, canon, or production reason.

For episodes whose rough roadmap is already strong, this should be a fast pass rather than a full Story Room rebuild.

### Stage 2 — Voice Check / Green Light

Human-involved.

Goal:
- review representative conversations / character interactions;
- confirm that dialogue sounds like the actual characters;
- adjust character voice, emotional cadence, humor, restraint, or relationship dynamics as needed.

The Voice Check is intentionally **not** a line-by-line copyedit of the eventual full episode.

Default format:
- divide the episode into its meaningful story sections;
- for each section, show the important conversational direction and the representative lines / exchanges that establish character voice;
- include enough dialogue to judge whether the characters sound right;
- do not require human review of throwaway micro-lines, grunts, filler interjections, incidental `ugh` / `ah` sounds, or every transitional sentence;
- focus human attention on lines that reveal character, relationship, comedy, conflict, exposition, or emotional movement.

The S1E1 workflow establishes another important rule:

> **Written planning may contain an explicit thought, explanation, or line that should disappear during manga panelization if the image can communicate it better.**

Therefore Voice Check approval locks the **intent, voice, and dramatic information**, not an obligation to print every reviewed sentence as a speech balloon or narration box.

During Stage 4, visual acting, expression, composition, silence, reaction panels, or environmental storytelling may replace text when that improves the manga without changing the approved beat.

At the end of Stage 2, the human gives either:

- `GREEN LIGHT`, or
- a targeted revision request.

A GREEN LIGHT authorizes the assistant to complete the remaining detailed episode construction without requiring human review of every intermediate layer.

### Stage 3 — Full Episode Construction

Assistant-led.

Goal:
- expand approved structure into continuous detailed story / scene prose;
- complete remaining dialogue;
- preserve character voice established in Stage 2;
- manage pacing, transitions, silence, acting, and continuity;
- run internal canon / continuity / character checks.

This stage should follow S1E1 `Not This Time` as the gold-standard reference for dramatic writing and character economy.

### Stage 4 — Manga Panelization + Production QC

Assistant-led.

Goal:
- convert the approved episode into manga panel/page structure;
- preserve approved story beats rather than inventing new story;
- allow story-driven page counts;
- create chapter cuts based on dramatic need;
- run production QC before rough manga generation.

Page length is not quota-driven.

An episode/chapter may be significantly longer or shorter than another if the story requires it.

**Visual-first adaptation rule:** panelization is allowed and expected to remove redundant prose/dialogue when expressions, staging, action, panel rhythm, or composition already communicate the same information more effectively. Do not preserve text merely because it existed in the detailed draft.

### Stage 5 — Rough Manga Review

Human-involved.

Goal:
- review the actual visual result;
- judge composition, acting, expression, readability, page turns, pacing, and consistency;
- decide whether scenes need more or less visual space;
- approve or request revisions before finalization / later animation adaptation.

## 3. Human involvement rule

Default human involvement is concentrated in:

`Stage 1 -> Stage 2 -> Stage 5`

The assistant owns Stages 3 and 4 after GREEN LIGHT unless a genuinely consequential creative decision appears.

The assistant should return to the human before proceeding only when:

- a major story decision is required;
- two materially different creative directions would alter character/arcs;
- a character voice remains uncertain after the approved voice reference;
- a canon/continuity conflict cannot be resolved without changing an approved decision.

Do not escalate ordinary panel-count, transition, or micro-composition decisions.

## 4. Current Season 1 readiness model

Use a visible four-level readiness status for episodes / episode-sized concepts.

### Level 4 — Manga-ready

Meaning:
- structure approved;
- detailed story approved/completed;
- voice established;
- manga panel script ready;
- next step is rough manga production.

Current known example:
- S1E1 `Not This Time`.

### Level 3 — Ready for Voice Check / Detailed Pass

Meaning:
- main episode structure is already strong;
- major beats and emotional purpose are known;
- only a fast structural confirmation and voice check are needed before assistant-led completion.

Current working direction:
- much of S1E2–E15 belongs here, subject to quick confirmation and any already-known exceptions.

### Level 2 — Strong Rough Episode

Meaning:
- episode-sized concept is real and substantial;
- main content exists;
- placement / scene order / exact structure still needs organization before voice check.

Current late-S1 examples include:
- World Opens / Mercantile Town;
- Guild Jobs / Working Days;
- G3 Part 1 / First Days;
- Day in the Life / Maomao Chocolate.

### Level 1 — Concept / Beat Only

Meaning:
- important story beat exists but is not yet a complete episode structure.

Example:
- a final season sting such as Sukuna / `Malevolent Shrine` when treated as a beat attached to another episode rather than a standalone episode.

## 5. Late-S1 ordering checkpoint

Before finalizing the remaining late-S1 episode concepts and moving all of them into Voice Check, explicitly review the order of the final three full-length episodes.

This is a required scheduling/pacing checkpoint.

Do not assume the latest rough creation order is the final broadcast/manga order.

The Day-in-the-Life episode remains placement-open.

Sukuna remains the final Season 1 beat unless a later approved story decision changes that.

## 6. The Arrivals UI production board

The Continuum UI should expose a dedicated `The Arrivals` production pipeline / season board.

At minimum it should show, per episode or episode-sized concept:

- season;
- episode / working number;
- title / working title;
- readiness level (`4`, `3`, `2`, `1`);
- human-readable status;
- current production stage (`1` through `5` where applicable);
- manga status;
- anime status;
- source documents / canonical status file;
- latest approval / green-light state;
- blockers / notes;
- last meaningful Git commit or source-of-truth revision.

Suggested high-level manga states:

- `not_started`
- `structure_ready`
- `voice_check`
- `full_episode_build`
- `panel_script_ready`
- `rough_generation`
- `rough_review`
- `approved`

Suggested high-level anime states:

- `not_started`
- `adaptation_planning`
- `storyboard`
- `animatic`
- `production`
- `review`
- `approved`

The UI should make it immediately obvious how much of Season 1 is ready for manga production and how much remains at Levels 3, 2, or 1.

The exact count shown by the UI must be driven by committed project state rather than hard-coded assumptions.

## 7. Step 0 — E1 parity audit for S1E2–E15

Before the late-S1 ordering work, maintain a simple parity view answering: **what is still missing for each S1E2–E15 episode to reach the same manga-readiness level as S1E1?**

S1E1 is already Level 4 and therefore has no remaining creative/documentation gate before rough manga production. Its remaining blockers are production-infrastructure blockers shared by the project, such as the visual generation stack / Vault readiness; those do not reduce E1's creative readiness level.

For S1E2–E15, the normal remaining path to E1 parity is:

1. **Fast structure confirmation** — verify the existing roadmap still works; do not rebuild Story Room material unnecessarily.
2. **Voice Check + human GREEN LIGHT** — approve representative dialogue / character behavior.
3. **Full Episode Construction** — assistant converts the approved roadmap into the detailed continuous episode draft using E1 as the writing standard.
4. **Manga Panelization + Production QC** — assistant converts the completed episode into a manga panel script and checks continuity / production readiness.

After those four gates, the episode becomes **Level 4 / manga-ready**, equivalent in readiness to S1E1, and the next human checkpoint is Stage 5 after rough manga exists.

This means that for episodes already genuinely at Level 3, the human does not need to repeat E1's full heavy Story Room process. Human work is concentrated in the quick structure confirmation and Voice Check; the assistant completes the two large execution passes after GREEN LIGHT.

The UI should eventually expose this parity gap per episode so it is obvious which exact gate prevents an episode from reaching Level 4.

## 8. Near-term workflow

Current intended sequence:

0. audit S1E2–E15 against S1E1 and track the exact remaining parity gates described above;
1. review / arrange the final three late-S1 full-length episodes;
2. give the remaining late-S1 concepts a rapid structural pass;
3. move qualified episodes into Voice Check;
4. human gives GREEN LIGHT episode-by-episode;
5. assistant completes Stages 3 and 4;
6. human returns at Stage 5 for rough manga review;
7. all status changes are committed to Git;
8. in parallel, Continuum completes Full Vault Integration and manga-production readiness;
9. once the generation stack is stable, start rendering E1 while later episodes continue through the creative pipeline;
10. as S1 approaches completion, expand the already-established S2 opening material ahead of production.

## 9. Source-of-truth principle

The project must be recoverable from Git without relying on chat history.

If a status shown in the UI disagrees with committed project documents, the UI is wrong and must be corrected.

If chat disagrees with a later authoritative Git correction, Git wins.
