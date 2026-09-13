# The Arrivals — Manga-First Production Workflow v0.1

**Status:** high-confidence production direction; implementation sequencing not yet locked  
**Date:** 2026-09-13  
**Project:** `The Arrivals`  
**Scope:** how approved story structure becomes manga, then anime, without skipping validation gates

This document defines the current preferred creative-production path for `The Arrivals`.

The key decision is:

> **The Arrivals should be developed manga-first before full anime production.**

This does not make manga a disposable prototype. The manga can be a finished expression of the same project canon while also de-risking later anime adaptation.

---

## 1. Why manga first

Manga is the most efficient place to validate:

- story structure;
- pacing;
- scene order;
- character acting;
- expressions;
- composition;
- visual continuity;
- outfits;
- important environmental information;
- emotional beats;
- dialogue quantity;
- whether an episode / chapter actually works before expensive motion production.

The project should not discover a structural story problem only after spending large compute and time on animation.

The working progression is:

```text
macro story spine
-> episode / chapter structure
-> Draft 1
-> manga panel script
-> rough manga
-> review / corrections
-> final manga
-> chapter approval / lock
-> anime adaptation draft
-> animatic / shot plan
-> tier assignment
-> animation production
-> final episode review
```

---

## 2. Story Room ownership

At the beginning, major episode / chapter development remains a human-guided Story Room process between Mauricio and the assistant.

Continuum should **not** autonomously generate twenty chapters from a season summary and declare them canon.

Early chapters establish the project's narrative grammar:

- how much silence is normal;
- how much dialogue Frieren actually needs;
- how Mau speaks before and after gaining confidence;
- how comedy and grief coexist;
- how long ordinary-life scenes are allowed to breathe;
- how arrivals are introduced;
- how much exposition is acceptable;
- how relationships change through behavior rather than labels.

Once enough chapters have been approved, Continuum may later propose drafts from higher-level beats, but approval remains explicit.

---

## 3. Draft layers

### Layer A — Episode / chapter structure

Answers:

- what happens;
- why each scene exists;
- what changes emotionally or materially;
- what information the viewer / reader gains;
- what remains hidden;
- what state each character enters and leaves with.

Example: `THE_ARRIVALS_S1E1_NOT_THIS_TIME_v0.1.md`.

### Layer B — Draft 1

Draft 1 converts approved structure into a readable dramatic script:

- scene action;
- visual rhythm;
- silence;
- transitions;
- original English dialogue;
- important gestures;
- continuity state;
- no unnecessary camera / panel micromanagement yet.

### Layer C — Manga panel script

The approved Draft 1 is then translated into manga language:

- page intent;
- panel order;
- panel size / emphasis where narratively important;
- establishing panels;
- close acting panels;
- silent reaction panels;
- speech balloon text;
- SFX where appropriate;
- page-turn reveals;
- continuity notes;
- outfit state;
- reference requirements.

Do not fix an arbitrary page count before the story has been panelized.

### Layer D — Rough manga

Generate / assemble rough pages first.

The rough pass exists to detect:

- bad pacing;
- confusing staging;
- inconsistent character positioning;
- weak page turns;
- dialogue that is too long;
- repeated shots;
- emotional beats without enough space;
- continuity mistakes.

Correct these before expensive final rendering.

### Layer E — Final manga

Only after the rough is approved should the system spend time on final-quality pages:

- consistent faces and bodies;
- intended outfit variants;
- final backgrounds;
- line / tone / shading treatment;
- lettering;
- polished effects;
- final page composition.

---

## 4. Source manga as voice / behavior reference

The user's legally held source manga can be used locally to analyze how a character behaves and speaks.

For writing, extract patterns such as:

- average line length;
- contraction usage;
- blunt vs indirect answers;
- frequency of silence;
- avoidance / deflection;
- characteristic reaction timing;
- recurring expressive grammar;
- whether concern is verbalized or shown through action;
- interpersonal distance and habits.

The source should inform **voice**, not become a quotation bank.

Preferred rule:

```text
learn the character's expressive grammar
!=
copy source dialogue into a new scene
```

For `The Arrivals`, final dialogue should be written primarily in English from the start rather than being translated from Spanish afterward.

---

## 5. Character identity is not one outfit

A character must not be represented internally as `character = one canonical outfit`.

Continuum should eventually support a wardrobe / look model with context such as:

```text
character identity
+ outfit / look
+ era
+ weather / season
+ role / activity
+ scene context
+ physical condition
```

Characters may therefore have:

- arrival clothing;
- casual / home looks;
- work clothing;
- travel looks;
- exploration / combat looks;
- seasonal looks;
- formal clothing;
- festival / event clothing;
- damaged / wet / dirty variants;
- repaired variants;
- clothing produced by people and industries that emerge in the settlement.

The goal is visual variety **without losing identity or continuity**.

The system must remember outfit state across scenes until an actual wardrobe change occurs.

---

## 6. Approval gates

No stage silently promotes itself to canon.

A useful approval model is:

```text
IDEA
-> DRAFT
-> REVIEW
-> APPROVED STORY
-> APPROVED MANGA
-> LOCKED CHAPTER / EPISODE CANON
```

Corrections should return to the cheapest correct layer.

Examples:

- bad line -> edit dialogue;
- bad panel rhythm -> panel script / rough manga;
- wrong emotional beat -> Draft 1 or scene structure;
- wrong story event -> episode structure;
- visual continuity error -> manga visual pass;
- anime acting / timing issue -> animatic / shot pass.

Do not hide story problems by polishing art.

---

## 7. What happens after the manga is approved

An approved manga chapter / episode becomes a strong adaptation source, not merely a mood board.

Next pipeline:

### 7.1 Anime adaptation draft

Determine what changes when sequential panels become time-based audiovisual storytelling.

A manga scene does not need a 1:1 panel-to-shot conversion.

For example:

- five manga panels may become a 90-second acting scene;
- exposition may become visual information;
- a silent page may become camera, wind, sound, and facial acting;
- an internal beat may require different audiovisual treatment.

The canon event remains stable while the medium changes its expression.

### 7.2 Shot list / animatic

Create:

- scene timing;
- shot order;
- staging;
- key poses;
- camera intent;
- dialogue timing;
- temporary audio;
- rough compositing.

This is where Remotion can eventually be especially useful for deterministic timing, camera moves, parallax, assembly, and audio synchronization.

### 7.3 Adaptive Animation Budget

Each shot / sequence is assigned an effort tier according to what the audience needs to perceive and remember:

```text
S — Hero
A — Character Acting
B — Standard
C — Limited
D — Economy / Designed Hold
```

The manga does **not** determine the tier automatically. Narrative importance, acting needs, motion needs, and production value do.

### 7.4 Benchmarks before promises

Before mass-producing anime episodes, benchmark representative material:

- quiet dialogue / slice of life;
- emotional acting;
- comedy;
- medium action;
- Tier-S hero action;
- atmosphere / establishing;
- multi-character interaction.

Measure real time and compute before estimating whole-season production.

### 7.5 Full anime production

Once the workflow is proven:

```text
approved manga / adaptation
-> durable production job
-> checkpointed shot generation
-> compositing / timing
-> sound / voice / music
-> episode review
-> approved anime episode
```

Long jobs must remain resumable rather than restarting after shutdown.

---

## 8. Where drafting happens now vs later

### Current state

Until Continuum has a real **Projects + Branches + Story Planning / Script / Manga** surface, the Story Room should continue using conversation + GitHub creative documents as the durable source of truth.

Do **not** force manga drafting into the current Acquisition UI or Phase 0 technical surface merely because those screens already exist.

The current appropriate workflow is:

```text
Story Room conversation
-> approved GitHub creative document
-> Draft 1 document
-> manga panel-script document
-> generation experiments
```

### Future Continuum state

When the relevant project phases exist, Continuum becomes the operational home for:

- Project `The Arrivals`;
- project branch;
- canon snapshots;
- episode / chapter entities;
- character / outfit states;
- Draft 1 revisions;
- manga page jobs;
- approval state;
- resulting artifacts;
- later anime adaptation jobs.

At that point conversation can remain the collaborative writing interface while **Continuum stores the structured project state and provenance**.

---

## 9. Immediate next step

For S1E1, the current state is:

```text
macro season direction         APPROVED / HIGH CONFIDENCE
S1E1 scene structure           APPROVED
Draft 1                        NEXT
manga panel script             AFTER DRAFT 1
rough manga                    AFTER PANEL SCRIPT
final manga                    AFTER ROUGH APPROVAL
anime adaptation               AFTER MANGA APPROVAL
```

The next artifact should therefore be **S1E1 Draft 1**, written scene by scene with sparse original English dialogue and visual action.
