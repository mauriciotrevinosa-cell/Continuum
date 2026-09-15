# M3 — Character Production Model specification

Status: **design frozen for implementation**. This document defines the next M3 character layer before real artwork generation.

## 1. Goal

Continuum already has a Character Profile, Character Outfit, Reference Vault, character corpus, page-specific retrieval and ComfyUI boundary. The missing layer is a **project-specific Production Model**: a small, human-approved visual base that answers “how does this character look in The Arrivals right now?” before page-level retrieval adds special angles, acting, environment or technique.

The Production Model is **not** the whole corpus, **not** a LoRA, **not** a style reference and **not** an automatic promotion of generated images to canon. It is a curated, versioned project artifact whose references are always inspectable.

## 2. Non-negotiable separations

1. **Identity != wardrobe != acting != style/technique.** Existing `CharacterAspect`, `CharacterOutfit`, `ReferenceUse`, `BundleRole` and corpus roles already enforce most of this separation; extend rather than collapse them.
2. **Corpus != Production Model.** The corpus may contain hundreds of observations. A Production Model is a deliberately small preferred pack.
3. **Candidate != approved.** Automatically discovered material may suggest a pack but cannot become an identity anchor until a person confirms it.
4. **Generated model sheet != identity truth by default.** A generated sheet begins `PROJECT_CREATED / CANDIDATE`. Creator approval is required before it becomes the project Production Model.
5. **Original character grounding is different from source-work grounding.** Mau is grounded by creator-primary material and approved project designs. Franchise material may teach style/technique but can never define Mau's identity.
6. **Production Model precedes page-specific retrieval.** Page bundles first load the active Production Model; only then do they add angle/expression/pose/continuity/grammar/environment evidence.
7. **Wardrobe can change without changing identity.** The active outfit is a separate project/timeline choice.

## 3. Production Model object

Implement a project-scoped, versioned record associated with one `CharacterProfile`.

Suggested semantic fields (exact DB naming may follow repository conventions):

- `id`
- `project_key`
- `character_id`
- `version` (monotonic within project + character)
- `status`: `DRAFT | REVIEW | APPROVED | SUPERSEDED`
- `name` (e.g. `The Arrivals Production Model v1`)
- `summary`
- `identity_rules` / restrictions
- `active_outfit_id` nullable
- `head_sheet_reference_id` nullable
- `body_sheet_reference_id` nullable
- `created_from` provenance payload
- `approved_at`, `approved_by`/review marker using existing project review conventions where possible
- timestamps / row version

A separate typed association should connect the model to its preferred evidence. Do not encode an undifferentiated list in JSON if an existing typed reference relation can be reused cleanly.

Each association needs at least:

- reference / observation locator
- role: `IDENTITY | BODY | WARDROBE | EXPRESSION | POSE | ACCESSORY | SCALE`
- preferred / required flag
- ordering
- optional notes (“front face”, “profile”, “boots + staff”, etc.)

The system should prefer reusing existing `ReferenceItem`, `CharacterObservation`, `ReferenceCharacter` and `CharacterOutfit` records rather than duplicating source identity.

## 4. Standard model-sheet deliverables

The Arrivals standard is **two sheets**, not one crowded waist-up turnaround.

### HEAD / FACE sheet

Required views:

- FRONT
- THREE_QUARTER
- SIDE_PROFILE
- BACK_HAIR / rear head silhouette

Rules:

- same identity and hair architecture across views
- neutral or restrained baseline expression
- no outfit variation inside the sheet
- clean background
- no scene lighting that changes perceived colors/shape
- no accessories unless they are identity-critical; otherwise accessories belong to wardrobe

### FULL BODY sheet

Required views:

- FRONT
- THREE_QUARTER
- SIDE
- BACK

Must establish:

- total proportions
- shoulder/torso/limb proportions
- relative body build
- posture baseline
- footwear
- hairstyle length/volume relative to body
- default/current outfit silhouette
- recurring equipment only when appropriate to that outfit

### Optional follow-up sheets

These are useful but do not block Production Model v1:

- core expression sheet
- hand/gesture sheet
- height/scale lineup
- outfit-specific mini turnarounds
- accessory sheet

## 5. Model builder state machine

`NO_MODEL -> COLLECTING -> READY_TO_BUILD -> GENERATED_CANDIDATE -> HUMAN_REVIEW -> APPROVED`

- `COLLECTING`: seed/confirmed refs exist but required facets are incomplete.
- `READY_TO_BUILD`: enough approved evidence exists to attempt a sheet.
- `GENERATED_CANDIDATE`: model-sheet image exists; never automatically grounds production.
- `HUMAN_REVIEW`: creator can approve, reject or regenerate.
- `APPROVED`: this version can be first-line project grounding.
- approving v2 supersedes v1 but never deletes v1 or old render provenance.

## 6. Minimum evidence policy

There is intentionally **no magic minimum number such as exactly five images**. A handful of seed images starts discovery; readiness is facet-based.

For a source-work character, `READY_TO_BUILD` should normally require confirmed high-authority evidence for:

- face/front or near-front
- face 3/4
- profile/side or equivalent hair silhouette
- usable full body/proportions
- current/default outfit

Back view is desirable and may be inferred for a candidate sheet, but a generated back cannot retroactively prove source canon. If the source has a real back view, prefer it.

For a project-original character, use creator-primary identity/body evidence plus approved project design decisions. Creator photos do not automatically define fantasy wardrobe.

## 7. Page-bundle priority

When a page contains a character with an APPROVED Production Model:

1. active Production Model identity anchors
2. active wardrobe/outfit references
3. page-specific confirmed corpus refs for requested angle/expression/pose
4. approved continuity from earlier real artwork in the same run
5. grammar/technique/environment refs, which remain non-identity inputs

Candidates may be shown in the UI as suggestions but must remain excluded from identity conditioning, preserving the existing Comfy candidate-safety invariant.

If there is no approved Production Model, existing corpus grounding continues to work; the feature must be additive and backwards compatible.

## 8. Production Model UI

Character Overview gains a prominent **Production Model** panel above the large corpus:

- status/version
- active HEAD sheet
- active FULL BODY sheet
- current outfit
- preferred anchors grouped by role
- restrictions / invariants
- `Build / Regenerate candidate`
- `Approve`, `Reject`, `Supersede`
- `Open evidence`

Corpus remains available below/through its existing route. The UI should make the hierarchy obvious: “Production Model first; corpus for evidence and special needs.”

## 9. AIComicBuilder adoption boundary

Pinned upstream lives at `tools/AIComicBuilder-upstream` and must remain clean. Do not develop inside the submodule.

Useful upstream concepts/code to study:

- four-view character turnaround prompt and generation path
- character reference-image handling
- provider abstraction where it cleanly informs Continuum

Continuum-specific changes belong in Continuum code, with attribution/Apache-2.0 obligations preserved if source code is adapted.

Important difference from upstream: the current AIComicBuilder turnaround path is primarily text-description -> one four-view image. Continuum must instead support **approved reference pack -> standardized sheet candidate**, with source provenance retained. We are borrowing/adapting the turnaround idea, not replacing Continuum's character system.

## 10. First implementation batch

Implement the system generically, then exercise it in this order:

1. Mau
2. Frieren
3. Fern
4. Stark

Do not hard-code these characters into the production-model schema. They are acceptance fixtures / first real users.

For the first three episodes, these four are the immediate grounding priority.

## 11. Character-specific starting rules

### Mau

- project-original / creator-primary grounding
- Anime Concept V2 remains `PROJECT_CREATED / STYLIZATION`, not identity/body truth
- V2 clothing is rejected and cannot become the E1 default outfit
- E1: no glasses
- identity baseline: youthful soft oval/slightly rounded face, soft jaw, dark eyebrows, expressive eyes, moderate/small nose, soft mouth; deep-brown medium-length naturally voluminous lightly wavy irregular hair; slim-athletic youthful build; warm/open, curious/literal, quiet/observant acting
- modern creator-photo clothing does not define E1 fantasy wardrobe

### Frieren

- source-work character
- prefer primary manga / official anime/art for identity
- quiet/attentive/deadpan acting must not be contaminated by Mau's page-level disorientation tags
- remove/replace the known invalid body anchor before real art
- see `docs/M3_FRIEREN_REFERENCE_REVIEW.md`

### Fern / Stark

- source-work characters
- build the same facet-complete baseline rather than relying on a single crop
- Fern currently needs stronger body grounding before early-story real artwork

## 12. Acceptance criteria

The feature is ready for the first real-art sample when:

- a character can have multiple Production Model versions without overwriting history
- generated sheets cannot self-approve
- active Production Model refs are inspectable and provenance-preserving
- identity, wardrobe, acting and style/technique remain separate
- candidates never condition identity
- active wardrobe can change independently
- page bundle visibly shows that Production Model refs were selected before supplemental corpus refs
- Mau and Frieren can each reach APPROVED through the actual UI flow
- tests cover approval gating, candidate safety, supersession and bundle priority

## 13. Deferred on purpose

Not required before the first artwork sample:

- final LoRA training
- automatic perfect character recognition across every manga page
- dozens of finished character sheets
- full S1 wardrobe
- video/Seedance integration
- replacing ComfyUI

Those should not consume the first implementation sprint.