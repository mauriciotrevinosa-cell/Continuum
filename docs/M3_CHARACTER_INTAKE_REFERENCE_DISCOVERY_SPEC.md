# M3 — Character intake and reference discovery specification

Status: **design frozen for implementation**.

## 1. Product goal

Adding a known character should feel like selecting from a library, not repeatedly typing franchise/name strings and manually rebuilding identity evidence.

Target flow:

`Family -> Character -> Snapshot -> Seed References -> Find More -> Review -> Build Production Model`

A custom/original escape hatch remains available.

## 2. Family selector

Replace free-form franchise entry as the default path with a searchable/scrollable family selector.

Requirements:

- search by canonical family title and aliases
- scroll/browse all known families
- show source availability (manga/anime/reference holdings) when known
- include `The Arrivals / Original` or equivalent custom-project path
- preserve the ability to create a family/character manually when the roster does not contain it

Do not hard-code a tiny dropdown. The selector must work as the roster grows.

## 3. Character autocomplete

After family selection, character entry becomes a family-scoped autocomplete.

Examples:

- select Jujutsu Kaisen
- type `Yu...`
- show matching known characters

The result should resolve to an existing `CharacterProfile` when one already exists rather than creating duplicates.

If a roster source already exists in project files/data, reuse it. If not, implement the smallest maintainable roster structure that can be populated later without a code change per character.

Suggested logical fields:

- family key
- canonical display name
- aliases
- subject kind
- source-work/project-original origin
- optional source snapshot/version note
- enabled/production-interest state

## 4. Snapshot / story-version metadata

Known source characters can have materially different designs/states over time. The intake flow therefore needs an optional project snapshot rather than pretending one name always means one visual state.

Snapshot may capture:

- source-era / arc / approximate point
- age/body state when visually relevant
- power/transformation state
- injuries or persistent physical state
- relationship/memory state when it affects project continuity
- project-specific overrides

Do not block simple characters on exhaustive lore metadata. This is a continuity field, not a lore database project.

## 5. Seed references

The creator can attach a small number of **seed references** to start discovery. Five is a useful example, not a fixed rule.

Seeds may come from:

- source manga
- official anime frames
- official art/model sheets
- creator-primary material for original characters
- project-created material
- fan art / supplemental material

Every seed keeps its existing authority/origin/provenance and does **not** become confirmed identity merely because it was selected as a seed.

The seed pack's purpose is: “this is what I mean by this character; search around this evidence.”

## 6. Find more references

`Find more references` searches Continuum's already-held/catalogued material first. It should not silently scrape the web or copy an entire external source.

Discovery should combine what Continuum already knows:

- selected character/family metadata
- seed reference labels/links
- existing curated references
- source catalog chapter/page metadata
- existing corpus observations
- available image similarity/embedding capability when implemented
- facet/angle/framing hints

The first implementation does **not** require perfect visual recognition. It may return candidates with uncertainty. Human review is the authority boundary.

Candidates should be grouped by needed facet so the creator can answer “what are we still missing?” rather than scroll an undifferentiated wall:

- Face: front / 3/4 / profile
- Hair/back silhouette
- Body/proportions
- Wardrobe
- Expression / quiet acting
- Pose / gesture
- Accessory/equipment
- Scale/co-occurrence

## 7. Candidate review

Every discovered item starts as CANDIDATE unless already confirmed by a person.

Review actions:

- Confirm for this character
- Reject character association
- Mark atypical
- Mark/prefer as anchor where allowed
- Assign facets
- Assign angle/framing/expression/pose
- Correct visual origin / authority
- Add notes

A wrong-character page may still remain useful elsewhere as grammar, technique, environment or another character's candidate. Rejecting a Frieren identity association must not delete the underlying source page.

## 8. Add to character from anywhere

Reference browsing is bidirectional. Wherever Continuum shows an inspectable reference/image, expose an `Add to character` action when semantically valid.

Flow:

1. choose existing character (searchable)
2. choose role/use
3. optionally choose outfit
4. candidate vs explicit human-confirmed review state
5. save association without copying source bytes

Role/use choices should map to existing vocabulary where possible:

- Identity / Face / Hair / Body / Proportions / Scale
- Wardrobe / Outfit / Accessory
- Expression / Quiet acting
- Pose / Gesture / Action pose
- Style
- Technique
- Mood

`Style` and `Technique` must never imply identity evidence.

This action should be available from curated References and corpus/source views. Fan-art browsing is a key use case: a useful image can be attached to an existing character without leaving the browsing flow.

## 9. Visual-origin rule

Keep acquisition source separate from visual authority.

Examples:

- official anime frame reposted by a fan account: acquired from fan/social source, visual origin `OFFICIAL_ANIME`
- actual fan illustration: visual origin `FAN_ART`
- manga page: `PRIMARY_MANGA`

Correcting visual origin may change authority classification according to existing rules, but it does not auto-confirm the observation.

## 10. Readiness UI

The intake screen should show a compact facet checklist:

- FACE FRONT
- FACE 3/4
- PROFILE
- HAIR/BACK
- FULL BODY
- PROPORTIONS
- DEFAULT/CURRENT OUTFIT
- optional: EXPRESSIONS / POSES / ACCESSORIES

States:

- missing
- candidates found
- confirmed but partial
- sufficient to build

`Build Production Model` becomes available when the required facet policy from `M3_CHARACTER_PRODUCTION_MODEL_SPEC.md` is satisfied.

## 11. Search scope and cost discipline

The initial product should prioritize:

1. already-curated character references
2. already-catalogued primary source pages
3. official/user-added references already in the Vault
4. supplemental/fan-art candidates already held

Do not make “download hundreds of external images” a requirement for basic character intake.

## 12. First-batch acceptance scenario

The implementation must support this real sequence:

### Frieren

- select family `Frieren: Beyond Journey's End`
- select existing `Frieren`
- see existing evidence/corpus
- add/confirm a few strong manga/official refs
- reject known wrong associations
- facet checklist reaches READY_TO_BUILD
- build model-sheet candidate
- creator reviews/approves

### Mau

- select `The Arrivals / Original`
- select existing `Mau`
- creator photos appear as creator-primary identity/body evidence
- Anime V2 appears only as stylization/support
- rejected V2 outfit cannot silently become default wardrobe
- add E1 wardrobe decision separately
- build candidate and approve only after visual review

Then repeat with Fern and Stark.

## 13. Safety/invariants tests

Tests should prove:

- selecting an existing character does not create duplicates
- candidate seeds do not become confirmed anchors automatically
- rejecting a character association preserves the underlying reference
- `Add to character` preserves source provenance
- fan art cannot silently become primary/official identity authority
- official visual origin can be recorded independently of where the bytes/link were acquired
- style/technique refs never condition identity
- custom/original characters remain supported
- Production Model build gating is facet-based, not a hard-coded image count

## 14. Deferred

Not needed in the first sprint:

- automatic internet scraping
- perfect face recognition
- automatic roster for every anime/manga ever made
- LoRA training
- video-character extraction

The purpose of this phase is a reliable human-steered intake loop that scales.