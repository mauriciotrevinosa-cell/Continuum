# M3 — Wardrobe timeline and LoRA/reference-conditioning strategy

Status: **design frozen for implementation**.

## 1. Wardrobe principle

A character's identity is stable; clothing evolves with the story. Continuum must therefore treat wardrobe as a timeline-aware layer on top of identity, not bake one outfit permanently into the character.

The current `CharacterOutfit` model is the correct foundation: an outfit belongs to a character and is explicitly not identity. Extend that concept minimally rather than creating a parallel closet system.

## 2. Wardrobe v1 scope

Before the first real-art sample, we only need enough wardrobe to cover the early episodes and prove the system.

For each early character, support:

- `ARRIVAL / DEFAULT`
- `SECONDARY` when story-supported
- optional `SLEEP / CASUAL`
- source-default outfit where applicable
- project-created variants as they are approved

Do **not** design the entire S1 closet now.

The wardrobe expands naturally after story events such as Rimuru / merchant access / guild work. The system should make later expansion easy without invalidating earlier art.

## 3. Outfit state

Each outfit should keep or expose:

- character
- name
- kind (`SOURCE_DEFAULT`, `SOURCE_ALTERNATE`, `PROJECT`, etc.)
- project key when project-specific
- era/story-stage label
- season/weather
- condition
- notes
- preferred reference(s)
- optional outfit model sheet / turnaround reference
- approval/review state where project-created
- availability window / timeline rule

If adding explicit availability fields requires a migration, keep the first schema small. A structured project/timeline association is preferable to packing production logic into free-form notes forever.

## 4. Timeline behavior

A production page should resolve wardrobe from project continuity/story stage, then allow a deliberate override.

Example conceptual stages:

- `EARLY_ARRIVAL`
- `INN_INITIAL`
- `MERCHANT_EXPANSION`
- later story-specific stages

Exact labels should come from project data rather than hard-coded enum values if the existing architecture already has a better project timeline primitive.

Rules:

- a later outfit never rewrites earlier pages
- a borrowed garment may be owned by one character but worn by another in a specific project state
- outfit changes do not create new character identities
- outfit model sheets can become project-approved wardrobe evidence without becoming identity anchors

## 5. Early The Arrivals notes

### Mau

- E1 clothing is not yet approved
- modern creator-photo clothing is not E1 wardrobe canon
- Anime Concept V2 clothing was rejected
- E1 default must be chosen separately and should support later recognizable borrowing/callbacks
- E1: no glasses
- later thin discreet round/slightly oval glasses are a story change, not an E1 accessory

### Frieren

- preserve recognizable source/default travel identity at arrival unless the script specifies otherwise
- later borrowed Mau clothing is wardrobe continuity, not identity drift
- known later callback: Mau layer/hoodie and cap become recognizable because Mau's initial wardrobe established them first

### Fern / Stark

- begin with a small source/project-approved early wardrobe
- do not pre-invent large closets before the story gives them access/reason

## 6. Why not train the LoRA first

A LoRA is not the discovery engine. It does not “search the manga” for more references. Discovery/corpus tooling finds and reviews evidence; LoRA training learns from a dataset we decide is suitable.

Training too early on a few mixed manga/anime/fan-art images risks learning:

- conflicting media/style
- wrong identity candidates
- unwanted outfits
- atypical deformation
- inconsistent proportions

The project should first establish approved Production Models and wardrobe evidence.

## 7. Staged visual-generation strategy

### Stage A — seed/reference conditioning

Input:

- a handful of good seed refs
- confirmed corpus evidence
- project restrictions

Use:

- reference conditioning / IP-Adapter or equivalent supported backend capability
- build standardized HEAD + FULL BODY sheet candidates
- generate additional review candidates when useful

Output remains non-authoritative until human review.

### Stage B — approved Production Model

After creator approval, use the Production Model as first-line character grounding for pages. Page-specific corpus refs solve angles, acting and pose.

### Stage C — dataset accumulation

Collect only approved/eligible material for possible character adaptation:

- confirmed source/official refs where training use is allowed and manually reviewed
- creator-owned/creator-approved original-character refs
- approved Production Model sheets
- approved project-created views
- approved artwork outputs that genuinely preserve identity

Keep rejected attempts, TEST renders and wrong-character candidates out.

### Stage D — optional LoRA/adaptation

Train only when the dataset is coherent enough to justify it. A rough target such as 15–30 useful images may be practical, but **quality, coverage and rights/training eligibility matter more than a fixed count**.

The LoRA should represent the project's stable character identity/design, not freeze every outfit into one look.

### Stage E — design exploration

Once identity is stable, use LoRA/reference conditioning to explore new project wardrobe/designs triggered by the story. New designs are candidates until approved, then enter Wardrobe with their own mini-sheet/references.

## 8. Training eligibility and provenance

Continuum already stores `rights_status` and `training_eligibility` on reference items. Any future training/export path must honor them.

Requirements:

- never treat “present in Vault” as permission to train
- manual review remains the default for training eligibility
- dataset manifest lists every source/reference/output and its eligibility/provenance
- do not export the whole Vault to a remote GPU
- remote jobs receive only the explicitly assembled approved dataset/bundle

## 9. ComfyUI relationship

ComfyUI remains the primary artwork backend currently implemented by Continuum.

The desired path is:

`Continuum character state -> Production Model + current Wardrobe + page refs -> ComfyUI -> master + B&W/color -> human review`

AIComicBuilder is an auxiliary source of useful character-turnaround/reference workflow ideas. It does not replace the provenance, continuity, review or Comfy boundaries already built into Continuum.

## 10. First-art blocker policy

The first real-art sample does **not** require a finished LoRA.

It does require:

- approved Production Models for the characters on the page
- approved current outfit decisions
- a backend capable of the required reference conditioning
- clean candidate/identity separation
- a fresh NON_CANON_SAMPLE beginning from Page 1 for true art continuity

LoRA can improve consistency later without delaying the first well-grounded real-art test.