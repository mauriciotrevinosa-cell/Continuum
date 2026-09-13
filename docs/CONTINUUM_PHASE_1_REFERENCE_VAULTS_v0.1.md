# Continuum — Phase 1 Reference Vaults v0.1

**Status:** APPROVED DIRECTION  
**Date:** 2026-09-13  
**Scope:** Phase 1 Library / Vault amendment  

## Decision

Phase 1 will include reusable **Character Reference Vault** and **Style Reference Vault** capabilities inside the user-level Library / Vault layer.

This does **not** move Character/Canon intelligence from Phase 5 into Phase 1. Phase 1 owns safe ingestion, cataloging, provenance, organization and retrieval of reference assets. Later phases add semantic analysis, canon reasoning, automated reference selection and generation.

The core remains project-agnostic. `The Arrivals` is the first project that will use these capabilities, not a hardcoded product feature.

## 1. Character Reference Vault

A character may have a reusable reference collection containing material such as:

- official art;
- manga/anime source images or extracted reference frames;
- user-provided fan art;
- user-provided sketches and design studies;
- approved Continuum-generated reference sheets later in the pipeline;
- face, hair, body-proportion and silhouette references;
- pose and body-language references;
- expression references;
- combat/action references;
- casual/daily-life references;
- object/accessory references;
- outfit and wardrobe references;
- alternate visual-language references.

Reference assets must retain provenance. At minimum, the catalog should be able to distinguish source-derived material, fan art, user-created material, generated material and project-approved material.

Fan art is allowed as visual inspiration, but must never silently become source canon. A user may explicitly mark it as useful inspiration or as the basis of a project-specific redesign.

### Character identity is not an outfit

Continuum must model recognizable character identity separately from clothing.

Identity may include stable or semi-stable features such as:

- face structure;
- body proportions;
- hair identity;
- height / scale relationships;
- distinctive marks;
- recurring accessories;
- posture and body language.

Wardrobe is variable and contextual.

A useful future reference key is conceptually:

`character_id + outfit_id + era + season/weather + condition + scene/context`

Possible outfit contexts include arrival/source appearance, everyday settlement clothing, work clothing, exploration/combat, seasonal/weather layers, formal clothing, handmade/local clothing, damaged/dirty states, festivals, dates, celebrations and funerals.

The Vault may store references for a new outfit in Phase 1. Whether that outfit becomes approved project continuity belongs to the project's later character/canon and approval layers.

## 2. Style Reference Vault

Continuum should support reusable visual references without forcing the project to imitate one source globally.

The project can have a coherent base visual identity while temporarily shifting visual language when the scene benefits from it.

Reference categories may include:

- base manga language;
- base animation language;
- action choreography;
- quiet acting;
- comedy / expressive deformation;
- romance / intimacy;
- horror / unease;
- mystery / deduction;
- memory / dream states;
- night lighting and atmosphere;
- compositing / color treatment;
- special experimental modes.

A temporary style shift should be intentional and tied to narrative, emotional or comedic purpose rather than random novelty.

Examples discussed for `The Arrivals` include using different sources for different techniques: Frieren for quiet acting and character reference, Bocchi for expressive/economic comedy, Call of the Night for stylized nocturnal atmosphere, action-focused sources for fight readability, and Apothecary Diaries-like visual language as a possible inspiration for deduction or clever-observation moments. These are reference directions, not hardcoded source requirements.

The project may also deliberately use stronger one-off visual transformations, including Spider-Verse-like changes of visual language, for special moments, hobby experiments, memories, comedy, perception shifts or thematic episodes.

## 3. Future reference bundles

Later Source Intelligence / Visual Lab stages should be able to build a small purpose-specific bundle for a panel, page, shot or scene instead of feeding an undifferentiated library to a generator.

Useful conceptual bundle classes are:

- **Canon references** — what a person/object/location must look like;
- **Technique references** — how a visual problem may be solved;
- **Continuity references** — how this project depicted the subject previously;
- **Mood references** — lighting, atmosphere, emotional texture and visual density.

Identity and technique must remain separable. Using an action source for choreography must not accidentally redesign the character to resemble that source.

## 4. Phase boundaries

### Phase 1 — Library / Vault

Phase 1 owns:

- safe reference ingestion;
- immutable-source preservation;
- reference catalog entries;
- provenance;
- user-defined organization and tags;
- character association;
- outfit association;
- style/reference collections;
- browsing and retrieval primitives;
- removal of Continuum records without mutating the original source asset.

Phase 1 does **not** need to understand the artistic meaning of every image.

### Phase 2 — Reader / Media

Provides practical viewing/inspection of those assets and source material.

### Phase 3 — Source Intelligence

May derive searchable visual features and observations such as page/panel structure, shot type, dialogue density, action intensity, expression, composition, number of characters, background complexity and other useful retrieval metadata.

### Phase 5 — Character / Canon

Adds character identity models, Source Canon, project snapshots, overrides, continuity-sensitive appearance logic and semantic character understanding.

### Later Visual / Production phases

Use reference bundles for rough manga, final manga, animatics, shots, animation and approved project assets. As `The Arrivals` accumulates approved pages and shots, its own approved work should increasingly become a first-class continuity reference source.

## 5. The Arrivals initial usage

The initial practical character-reference priority is expected to include the early cast such as Frieren, Fern, Mau, Bocchi, Yuta and Rimuru, then expand with the arrival groups as production requires them.

This priority is a project usage choice, not a core-schema hardcode.

A future slice-of-life story may also naturally introduce new clothing through character activity rather than a menu-only redesign. One discussed example is Marin and Wakana Gojo making outfits with help from Rimuru while other arrivals come through for fittings. Mau receiving simple comfortable everyday clothing is one possible beat. Such ideas remain story-room material until separately approved in project continuity.

## 6. Storage and safety rules

- Raw commercial/user source media remains outside Git and must not be duplicated into the repository.
- Git stores schemas, manifests, metadata, approved direction, provenance records and lightweight project/reference declarations.
- Source Vault assets remain read-only through Continuum.
- Derived thumbnails/features/indexes belong in derived/data storage, not beside immutable source files.
- A project may reference Library assets without turning Library membership into project membership.
- Sharing a project later must not package raw commercial source media.

## 7. Implementation timing

This document is a Phase 1 design commitment, not authorization to start implementation during the Phase 0 closure audit.

Phase 0 must finish independently. After Phase 0 closes, Phase 1 implementation can introduce the reference-vault data model and UI incrementally while preserving the approved phase architecture.
