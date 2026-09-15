# M3 — Character foundation handoff

Date: 2026-09-15
Branch: `m3/critical-path`

## Current direction

The next production priority is **Character Production Models before real artwork**. The normal manga workflow audit is considered complete enough for this stage; do not spend the next Work session re-proving TEST render mechanics unless a regression appears.

## Prepared design package

Read these as the authoritative implementation package for the next sprint:

1. `M3_CHARACTER_PRODUCTION_MODEL_SPEC.md` — project-specific model architecture, model sheets, approval and bundle priority.
2. `M3_CHARACTER_INTAKE_REFERENCE_DISCOVERY_SPEC.md` — Family -> Character -> Snapshot -> Seeds -> Find More -> Review -> Build Model, plus Add to character.
3. `M3_WARDROBE_AND_LORA_STRATEGY.md` — early wardrobe timeline, conditioning-first strategy and later optional LoRA.
4. `M3_FRIEREN_REFERENCE_REVIEW.md` — concrete bad refs to reject and strong early source candidates to review.
5. `M3_AICOMICBUILDER_ADOPTION_NOTES.md` — what to adapt and what not to import from the pinned external tool.
6. `M3_WORK_SPRINT_PROMPT_CHARACTER_MODELS.md` — checkpointed execution prompt designed for a limited Work session.

## External tool

`tools/AIComicBuilder-upstream` is pinned as a clean Git submodule. It is an implementation reference/auxiliary tool, not a replacement for Continuum or ComfyUI. Do not edit inside the submodule.

## Early cast priority

1. Mau
2. Frieren
3. Fern
4. Stark

The generic system matters more than finishing all four in one sprint. If time is tight, land the infrastructure, then Mau/Frieren.

## Character truths already fixed for implementation

- Mau: creator-primary identity; Anime V2 is stylization only; V2 clothing rejected; E1 no glasses; modern creator-photo clothing does not define E1 fantasy wardrobe.
- Frieren: source-work grounding; invalid contents-page body anchor must be removed/rejected; Ch91 p14 and Ch123 p13 do not verify Frieren; early acting is attentive/deadpan, not globally confused.
- Fern: needs stronger body grounding before early real artwork.
- Wardrobe is separate from identity and grows with story access/events.
- Generated model sheets are candidates until explicit creator approval.
- Candidate observations remain forbidden from identity conditioning.

## Real-art sequencing after the character sprint

1. creator reviews/approves Production Models and early wardrobe
2. connect a real Comfy/GPU endpoint with model/workflow provenance
3. optional small smoke test if needed
4. create/use a **fresh NON_CANON real-art sample from Page 1**
5. review Page 1 before Page 2 unlock/continuity

The existing TEST-approved sample pages must not be treated as artistic continuity.

## Git discipline for Work

Every stable checkpoint must be:

`tests/checks -> commit -> push origin m3/critical-path -> handoff update -> next checkpoint`

Do not hold multiple hours of unpushed work. If credits/time end, the last stable checkpoint should already be remote.

## Deferred intentionally

- final LoRA training
- whole-chapter real rendering
- video pipeline work
- huge franchise roster
- perfect visual recognition
- importing AIComicBuilder wholesale
- canonical E1 / SAMPLE PASS

Use `M3_WORK_SPRINT_PROMPT_CHARACTER_MODELS.md` for exact execution order and stop conditions.