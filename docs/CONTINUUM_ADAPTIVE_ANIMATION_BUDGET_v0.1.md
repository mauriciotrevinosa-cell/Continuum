# Continuum — Adaptive Animation Budget v0.1

**Status:** Authoritative production addendum  
**Date:** 2026-09-12  
**Scope:** Continuum Production Engine, especially storyboard/animatic and local image/video/audio production phases  
**Authority:** This document supplements `PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md`. Where this document is more specific about shot-level animation planning, production cost, or motion allocation, this newer guidance wins.

---

## 1. Core production rule

Continuum must not define anime quality as "maximum motion in every shot."

The production target is **maximum perceived quality per unit of time/compute**, while preserving character consistency, cinematography, acting, sound, continuity, and the ability to remaster later.

The central question is not:

> What quality is this episode?

It is:

> What level of motion and production effort does this shot need to perform its narrative function?

A strong held drawing, limited-animation conversation, parallax shot, or controlled camera move can be the correct final shot. Full animation is reserved for moments that actually benefit from it.

This is a sustainability requirement for long-form projects. Continuum should be capable of producing many episodes without treating every minute like a feature-film action climax.

---

## 2. Adaptive Animation Budget

Every planned shot receives an `animation_tier` plus explicit motion requirements.

### Tier S — Hero

Use for moments meant to be remembered:

- major fights or decisive action beats;
- important power reveals;
- emotional climaxes;
- major transformations;
- unusually complex camera/action choreography;
- signature project moments.

Expected treatment may include:

- high motion density;
- detailed body mechanics;
- secondary motion;
- complex FX;
- stronger camera work;
- more iterations and manual review;
- higher compute/time allowance.

**Rule:** Tier S is not used merely because a shot could look cool. It is used because the story benefits from the contrast and the moment earns the production expense.

### Tier A — Character Acting

Use for important dialogue, romance, conflict, discovery, and character-driven scenes.

Prioritize:

- facial acting;
- eyes and gaze direction;
- hands and small gestures;
- posture changes;
- hair/clothing response when useful;
- subtle camera movement;
- clean timing and reaction shots.

The scene may contain much less total motion than Tier S while still feeling premium.

### Tier B — Standard

Default for ordinary scene coverage.

Typical techniques:

- strong key poses;
- mouth animation;
- blinks;
- head/torso motion;
- occasional gesture or pose change;
- reusable motion cycles where appropriate;
- camera movement over stable artwork;
- controlled background motion.

This tier should carry a large part of normal episode runtime.

### Tier C — Limited

Use for exposition, secondary conversations, connective material, low-intensity slice-of-life, and shots where extra movement would not materially improve the scene.

Typical techniques:

- held drawings;
- mouth/eye changes;
- pose swaps;
- pans, pushes, and reframing;
- parallax;
- simple loops;
- carefully timed cuts;
- reaction inserts.

Limited animation is an intentional production language, not automatically a defect.

### Tier D — Economy / Designed Hold

Use for establishing shots, atmosphere, montage beats, memories, location transitions, maps/objects, and other moments where composition/sound carry the scene.

Typical techniques:

- high-quality illustration;
- layered parallax;
- lighting/compositing changes;
- environmental movement;
- camera move;
- strong sound design and music;
- short duration or purposeful stillness.

A Tier D shot must still be authored. "Low motion" must never mean "unfinished."

---

## 3. Episode budget is a target distribution, not a hard quota

Continuum may suggest an initial distribution for a normal dialogue/slice-of-life-heavy episode such as:

- Tier S: roughly 5–8%
- Tier A: roughly 15–20%
- Tier B: roughly 35–40%
- Tier C: roughly 25–30%
- Tier D / designed holds / reuse: remaining runtime

These numbers are **planning defaults only**. They are not canon, not a fixed recipe, and must adapt to episode purpose.

Examples:

- a quiet relationship episode may have no Tier S shots;
- a finale may spend far more runtime in S/A;
- a montage-heavy episode may intentionally use more D;
- an action episode may increase S while reducing complexity elsewhere.

The user/director can override any suggested tier.

---

## 4. Shot data model

Storyboard/shot planning should eventually support fields equivalent to:

```text
animation_tier: S | A | B | C | D

priority:
- story
- emotion
- action
- character_acting
- comedy
- atmosphere

motion_requirements:
- full_body
- face
- eyes
- mouth
- hands
- hair
- cloth
- props
- background
- camera
- fx

reuse_allowed:
- rig
- pose
- cycle
- background
- crowd
- prop
- camera_template

quality_requirements:
- character_consistency
- drawing_detail
- compositing
- lighting
- lip_sync
- sound_sync
- continuity

budget:
- estimated_compute
- estimated_render_time
- expected_iterations
- manual_review_level
```

Exact schema names are implementation details, but the distinction between **narrative priority**, **motion requirement**, **reuse permission**, and **quality requirement** must survive implementation.

---

## 5. Quality hierarchy

When resources are constrained, Continuum should generally protect quality in this order:

```text
character/model consistency
→ strong key drawing / composition
→ continuity and readable acting
→ cinematography / shot choice
→ compositing / lighting
→ sound / voice / music timing
→ motion where motion adds value
→ additional motion density
```

This prevents the system from spending enormous compute on movement while allowing faces, proportions, staging, or continuity to degrade.

A beautifully composed low-motion shot can be more successful than a badly directed high-motion shot.

---

## 6. Reference-anime analysis

The user's Library may contain many anime sources. Continuum should not treat every source as a global quality target.

Instead, Source Intelligence should eventually allow selected anime to become **production-technique references** for specific problems, for example:

- economical dialogue staging;
- subtle romantic acting;
- atmospheric stillness;
- comedy through editing and composition;
- expressive stylization;
- action choreography;
- FX-heavy hero moments;
- crowd handling;
- backgrounds and environmental motion;
- camera language;
- use of held frames or limited animation.

The system should learn/reference **techniques and production decisions**, not blindly reproduce one show's complete style.

A project may therefore select a small reference set (for example, roughly 8–10 especially useful sources) even when the Library contains 50+ anime.

Reference selection is project-level and editable. Library membership never implies project membership or cast inclusion.

---

## 7. Production scheduler implications

The durable Production Job Manager should use animation tier when estimating and scheduling work.

Higher tiers may receive:

- more generation passes;
- more candidate frames;
- more temporal consistency checks;
- higher-resolution intermediate work;
- more manual approval gates;
- more expensive providers/models where the user permits them;
- larger retry/iteration budgets.

Lower tiers should preferentially use:

- reusable approved assets;
- cached backgrounds;
- pose/rig reuse;
- deterministic camera/parallax operations;
- lightweight motion;
- shorter render chains.

This budget belongs in the recipe/manifest so a finished episode can later be selectively remastered without regenerating everything.

---

## 8. Reuse must be intentional and traceable

Reuse is a production feature, not a hidden shortcut.

Reusable assets may include:

- locations/backgrounds;
- crowd elements;
- props;
- approved character poses;
- walk/run cycles;
- lip/blink systems;
- FX components;
- camera move templates;
- environment loops.

Every reused asset should retain version/provenance information so later visual-model upgrades can regenerate only affected shots.

Do not silently reuse an asset when continuity requires a different costume, injury state, age, location state, lighting condition, or project branch state.

---

## 9. Sound is part of perceived animation quality

Continuum should budget sound design, music, ambience, voice timing, pauses, impacts, and transitions alongside visual motion.

A limited-motion scene with excellent acting, timing, ambience, and composition can feel far more alive than a high-motion scene with weak sound.

The animation budget therefore must not consume the entire episode production budget. Audio and compositing remain first-class production stages.

---

## 10. Benchmark before scaling

Before committing to a full production cadence, Continuum should benchmark representative scenes from at least these categories:

1. quiet dialogue / slice-of-life;
2. important emotional acting;
3. comedy;
4. medium action;
5. Tier-S hero action;
6. establishing/atmosphere;
7. crowd or multi-character interaction.

For each benchmark record:

- wall-clock time;
- active compute time;
- GPU/CPU/RAM/VRAM use;
- retries;
- number of generated candidates;
- manual intervention time;
- final tier;
- perceived quality assessment;
- artifact/model/provider versions.

Only after benchmarks should Continuum estimate chapter/episode production time.

Do not promise a fixed "hours per episode" target before real measurements exist.

---

## 11. Approval and escalation

The system may recommend raising or lowering a shot's tier, but the director decides.

Useful warnings include:

- "This Tier S shot contributes little narrative value but dominates estimated render time."
- "This emotional scene is Tier C even though facial acting is story-critical."
- "This shot can reuse an approved background without changing continuity."
- "This effect can be isolated and remastered later instead of rerendering the entire shot."

The goal is to expose production tradeoffs before expensive generation begins.

---

## 12. Project implication for The Arrivals

The Arrivals is expected to contain substantial ordinary life, relationships, settlement/city growth, conversations, craft, exploration, and slower character change in addition to action.

That structure is an advantage: the project does **not** require maximum action-animation density in every episode.

The production language should deliberately create contrast:

```text
quiet / economical / intimate scenes
→ gradual buildup
→ selectively expensive character or action moment
→ return to sustainable production language
```

A rare Tier S moment should feel more significant because the entire series is not rendered at Tier S continuously.

The project should remain free to add new Library sources without committing to use those sources or characters in The Arrivals. Cast selection happens later at the project level.

---

## 13. Implementation placement

This addendum does not pull advanced animation generation into Phase 0.

It should influence later work as follows:

- **Phase 10 — Visual Lab:** develop style/quality comparisons and reference techniques.
- **Phase 11 — Script / Manga / Storyboard / Animatic:** assign and review shot tiers; estimate budgets before rendering.
- **Phase 12 — Local Image / Video / Audio:** execute tier-aware recipes and benchmark real production cost.
- **Phase 13+ — Advanced Director / Automation:** optimize episode-wide budgeting, reference-technique selection, adaptive scheduling, and selective remastering.

The underlying durable-job, provenance, versioning, provider, checkpoint, and artifact-lineage foundations remain mandatory.
