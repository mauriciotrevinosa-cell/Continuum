# Continuum — Production Tooling Direction v0.1

**Status:** Approved direction for later production phases  
**Date:** 2026-09-12  
**Scope:** Phase 10 Visual Lab, Phase 11 Script/Manga/Storyboard/Animatic, Phase 12 Local Image/Video/Audio Production  
**Related:** `docs/CONTINUUM_ADAPTIVE_ANIMATION_BUDGET_v0.1.md`, `PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md`

---

## 1. Decision

Continuum will keep **ComfyUI** and **Remotion** as the two primary external tooling candidates to investigate for the future visual-production pipeline.

They solve different problems and should not be collapsed into one subsystem:

- **ComfyUI** is a candidate execution/provider layer for generative image/video/audio workflows.
- **Remotion** is a candidate deterministic composition/render layer for animatics, camera moves, layered motion, timing, captions, audio assembly, and economical final shots.

Neither tool becomes Continuum itself. Continuum remains the director/orchestrator and owns story state, shot intent, continuity, durable jobs, provenance, recipes, approvals, artifact lineage, and project decisions.

No dependency is added to Phase 0 by this decision.

---

## 2. Architectural boundary

Preferred future shape:

```text
Continuum Story / Director Engine
        ↓
scene + shot plan
        ↓
shot intent + narrative importance + motion requirements
        ↓
Adaptive Animation Budget (S / A / B / C / D)
        ↓
versioned Production Recipe
        │
        ├── generative work → provider abstraction → ComfyUI candidate
        │
        ├── deterministic composition → Remotion candidate
        │
        └── media encode / mux / inspection → FFmpeg and related media tools
        ↓
artifact + provenance + checkpoint + approval
```

Continuum must not hard-wire project logic directly to a ComfyUI graph or a Remotion composition.

Both should sit behind replaceable interfaces so a future provider can replace either one without rewriting story/project logic.

---

## 3. ComfyUI role

Repository evaluated:

`Comfy-Org/ComfyUI`

ComfyUI is retained as a **high-priority future production-engine candidate** because its node-graph workflow model aligns well with Continuum's planned recipe/provider architecture.

Useful capabilities include:

- reusable image/video/audio generation workflows;
- local execution;
- API-driven execution;
- model/provider modularity;
- reference conditioning and control workflows;
- inpainting/outpainting;
- masks and compositing support;
- upscaling;
- frame interpolation;
- segmentation/depth/vision helpers;
- partial graph re-execution;
- queueing and resource-aware execution.

### Intended Continuum use

Continuum should eventually be able to invoke named/versioned ComfyUI workflow recipes such as:

```text
character_keyframe_v3
controlled_character_acting_v2
background_generation_v4
hero_action_video_v1
fx_pass_v2
upscale_final_v3
```

The exact workflow files, models, seeds, settings, adapters, references, and outputs must be recorded in the Continuum recipe/manifest lineage.

### What ComfyUI does not own

ComfyUI must not decide:

- story canon;
- project branch state;
- who is in a scene;
- costume/injury/age continuity;
- whether a scene deserves Tier S;
- which shot is narratively important;
- final project approval.

Those remain Continuum responsibilities.

---

## 4. Remotion role

Repository evaluated:

`remotion-dev/remotion`

Remotion is retained as a **high-priority deterministic composition candidate**.

It is particularly interesting because many shots do not require expensive generative video.

A shot may instead be assembled from approved reusable assets:

```text
background
+ character layer(s)
+ pose variants
+ blink / mouth states
+ camera move
+ parallax
+ lighting change
+ subtitles when required
+ dialogue
+ ambience
+ SFX
+ music
```

This maps directly to the Adaptive Animation Budget philosophy.

### Intended use by tier

This is not a hard rule, only a likely production pattern:

- **Tier D:** often Remotion-heavy / deterministic composition.
- **Tier C:** often Remotion-heavy with limited generated assets.
- **Tier B:** mixed generated assets + deterministic assembly.
- **Tier A:** controlled generation plus detailed deterministic edit/composition.
- **Tier S:** expensive generation/provider chain followed by deterministic edit/compositing where useful.

The system should choose the cheapest technique that preserves the narrative function and visual standard of the shot.

### Phase 11 value

Remotion may also be useful before final animation for:

- playable animatics;
- storyboard timing;
- shot-duration tests;
- dialogue timing;
- temporary camera moves;
- temporary sound/music placement;
- quick alternate edit comparison.

That makes it potentially valuable before Phase 12 begins.

---

## 5. S/A/B/C/D clarification

The animation tier belongs to a **shot or sequence**, not to an entire anime and not automatically to a scene type.

Examples:

- A minor fight may be Tier C or B and be resolved through a cutaway, reaction shot, impact sound, short insert, or aftermath.
- A major fight may earn Tier S.
- A routine political discussion may be Tier C/B.
- A politically decisive conversation may be Tier A/S even if the characters remain seated.
- A long-awaited emotional reunion may deserve Tier S acting with relatively little body motion.

Therefore the production question is:

> What must the audience actually see, and what can be implied or composed more economically without weakening the scene?

This principle should drive provider/workflow selection.

---

## 6. Production-reference library implication

Anime acquisition for early production research should serve two independent purposes:

1. **Cast/source coverage** — sources needed for characters likely to appear early in a project such as The Arrivals.
2. **Production-reference coverage** — sources that demonstrate useful solutions to recurring animation/directing problems.

A source may satisfy one or both.

Reference tags may eventually include concepts such as:

```text
HERO_ACTION
MEDIUM_ACTION
CHARACTER_ACTING
INTIMATE_DIALOGUE
POLITICAL_MEETING
ECONOMY_HOLD
LIMITED_ANIMATION
COMEDY_TIMING
CAMERA_LANGUAGE
MAGIC_FX
CITY_ESTABLISHING
CROWD_SCENE
ATMOSPHERE
BACKGROUND_MOTION
EMOTIONAL_CLOSEUP
```

Continuum should retrieve techniques by problem, not treat one anime as the quality/style target for every shot.

---

## 7. Durable-job requirement

External tooling must not bypass Continuum's durable job architecture.

Long production workflows must remain resumable and checkpointed.

A future ComfyUI or Remotion integration should therefore be invoked as atomic/restartable production steps, for example:

```text
shot planning
→ keyframe generation
→ consistency approval
→ motion generation
→ deterministic composition
→ audio pass
→ encode
→ QC
```

A failure in the final encode must not require regenerating the expensive visual generation stage.

Every stage should preserve inputs, outputs, provider/tool version, recipe version, timing, retries, and error state.

---

## 8. Reproducibility and selective remastering

Generated and composed shots should retain enough information to reproduce or selectively upgrade them later.

Record where applicable:

- tool/provider;
- tool version;
- workflow/composition identifier and version;
- model references;
- seed/settings;
- source/reference asset IDs;
- project/branch state;
- animation tier;
- approved inputs;
- intermediate artifacts;
- output artifact;
- render/compute time;
- manual approvals.

If a better model becomes available later, Continuum should be able to remaster selected Tier S/A shots without rebuilding the entire episode.

---

## 9. Installation policy

Do **not** install or vendor ComfyUI or Remotion into the Continuum repository merely because they are approved candidates.

Before implementation:

1. benchmark the actual hardware;
2. inspect current upstream versions and licenses;
3. determine external-tool vs package/provider deployment;
4. define a stable provider contract;
5. test a minimal end-to-end shot recipe;
6. measure storage/VRAM/RAM/render-time impact;
7. record results before committing to the stack.

Large model files and generated media must not enter Git.

External tools/models should live under configurable tool/model roots, not be embedded into the application repository.

---

## 10. Current decision summary

```text
ComfyUI
STATUS: KEEP / HIGH-PRIORITY FUTURE PROVIDER CANDIDATE
PRIMARY VALUE: modular generative image/video/audio workflows
EARLIEST SERIOUS PHASE: Visual Lab experiments, then Phase 12 execution

Remotion
STATUS: KEEP / HIGH-PRIORITY FUTURE COMPOSITION CANDIDATE
PRIMARY VALUE: deterministic animatics, editing, layered economy animation, rendering
EARLIEST SERIOUS PHASE: Phase 11 animatics, then Phase 12 composition
```

No other repository evaluated in the same discussion is currently promoted to this approved production-tooling shortlist.
