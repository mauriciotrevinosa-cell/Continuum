# Visual Knowledge + Layered Renderer Architecture v0.1

**Status:** creator-directed architecture / implementation contract  
**Project scope:** Continuum-wide, first production target: The Arrivals  
**Companion:** `THE_ARRIVALS_MANGA_RENDERER_ARCHITECTURE_v0.1.md`

## 1. Core principle

Continuum owns the visual problem. A renderer solves a bounded stage of that problem.

The current panel-first rule remains intact:

> story beat -> panel contract -> visual references -> bounded panel render -> deterministic page composition -> Continuum lettering.

The new addition is that a panel does not need to be generated as one monolithic final image. It may be built through controlled stages.

## 2. Four separate systems

### A. Visual Knowledge

A searchable corpus of examples that answer questions such as:

- how to stage a two-person intimate conversation;
- how to draw a hand gripping fabric;
- how to make an abandoned path read as unused for years;
- how to use a low-angle action shot without losing anatomy;
- how a manga page breathes before a reveal;
- how lighting, screentone, rain, particles, magic or foliage can be treated.

A Visual Knowledge item is not automatically style training material and never becomes canon because it is useful.

### B. Project House Style

The project's current default rendering language.

For The Arrivals this is intentionally **evolving**, not a fixed percentage blend of four franchises. Frieren, Witch Hat Atelier, Call of the Night and Dandadan are the current strongest discovery references because they expose useful qualities, but new manga, illustrations, fan art, creator studies and successful project renders may improve the style later.

House Style answers:

> How does The Arrivals usually look?

### C. Scene Treatment

A deliberate scoped override layered on top of House Style.

Examples:
- oil-painting-like magical vision;
- watercolor memory;
- graphic/glitch Noise sequence;
- aggressive high-contrast ink for horror;
- unusually luminous color for divine magic.

A treatment must not silently rewrite identity, wardrobe, spatial canon, cast, chronology or panel semantics.

### D. Layered Construction

The process used to build the panel.

Recommended conceptual stages:

1. **COMPOSITION**
   - camera;
   - subject placement;
   - silhouettes;
   - depth;
   - perspective;
   - basic pose.

2. **DRAWING**
   - anatomy;
   - face;
   - hands;
   - hair;
   - clothing geometry;
   - props.

3. **LINE**
   - clean contours;
   - internal detail;
   - fabric folds;
   - material boundaries.

4. **VALUE / MATERIAL**
   - major dark/light masses;
   - skin / cloth / metal / stone / wood separation;
   - local material logic.

5. **LIGHT / SHADOW**
   - illumination;
   - cast shadows;
   - depth separation;
   - atmosphere.

6. **FX**
   - magic;
   - particles;
   - speed/motion;
   - smoke;
   - rain;
   - impact effects.

7. **ENVIRONMENT INTEGRATION**
   - background completion;
   - contact shadows;
   - spatial continuity;
   - environmental interaction.

8. **FINISH**
   - B&W ink/screentone or approved color finish;
   - cleanup that does not redraw protected structure.

9. **LETTERING**
   - always Continuum-owned;
   - never delegated to diffusion.

These are logical stages. A provider may combine adjacent stages internally if it still respects the stage contract and lineage.

## 3. Freeze / invalidation rule

The architecture must avoid repeated unrestricted img2img passes.

When a stage is approved:

> preserve approved structure unless a later stage has explicit permission to alter it.

Examples:

- approved face identity cannot be reinvented by LIGHT;
- approved hand anatomy cannot change because FX is added;
- approved panel geometry cannot move because FINISH runs;
- wardrobe geometry cannot mutate during screentone;
- background integration cannot add extra cast.

If an upstream stage changes, Continuum invalidates only dependent downstream artifacts.

Example:

`COMPOSITION v3 -> DRAWING v2 -> LINE v1 -> LIGHT v4`

If COMPOSITION changes, all later stages are stale.  
If LIGHT changes, COMPOSITION / DRAWING / LINE stay valid.

## 4. Panel reference pack

A panel should receive references by **role**, never as one undifferentiated image pile.

Recommended roles:

- IDENTITY
- BODY / PROPORTIONS
- WARDROBE
- ACTING
- POSE
- COMPOSITION
- CAMERA
- ENVIRONMENT
- MATERIAL
- ACTION
- TECHNIQUE
- MOOD
- HOUSE_STYLE
- SCENE_TREATMENT
- CONTINUITY
- SOURCE_PLATE when applicable

Continuum should retrieve the narrowest useful evidence for the exact panel.

Example query:

`2 subjects + intimate + eye-level + medium close + restrained relief + head touch + bedroom/recovery`

is preferable to:

`give model Frieren pages + Mau photos + favorite manga pages`.

## 5. Visual Knowledge taxonomy

Primary functional buckets:

- CHARACTER_CONSTRUCTION
- ANATOMY
- HANDS
- FACE
- HAIR
- CLOTHING
- POSE
- GESTURE
- CAMERA
- PERSPECTIVE
- COMPOSITION
- ACTION
- IMPACT
- MOTION
- EMOTION
- QUIET_ACTING
- ENVIRONMENT
- ARCHITECTURE
- MATERIALS
- LIGHTING
- ATMOSPHERE
- MAGIC
- FX
- LINEART
- SCREENTONE
- COLOR
- MANGA_GRAMMAR
- PANEL_LAYOUT
- PAGE_TURN
- PROCESS

An item can belong to multiple buckets.

## 6. Process Dataset

Timelapses, drawings with saved stages, CSP/PSD layer exports, artist breakdowns and similar material can teach **process**, not only final appearance.

Useful stage evidence:

`construction -> sketch -> clean drawing -> line -> flats/value -> shadow -> light -> FX -> final`

A process item should preserve links between stages from the same artwork.

Do not assume every timelapse is training-eligible. Process material may remain reference-only.

## 7. Existing Continuum types already help

Current Continuum already separates important concepts:

- `ReferenceClass.CANON`
- `ReferenceClass.TECHNIQUE`
- `ReferenceClass.CONTINUITY`
- `ReferenceClass.MOOD`
- `TechniqueFacet`
- `DescriptorFacet`
- `BundleRole`
- `VisualModeCategory`

The Visual Knowledge layer should extend these concepts rather than create a parallel reference system.

Notably, `VisualModeCategory.COMEDIC_DEFORMATION` already describes **chibi / super-deformed** as a rendering decision rather than identity.

## 8. Chibi note — intentionally non-urgent

Chibi versions are preserved as a **character visual mode / scene treatment**, not a separate identity and not a priority for the first production renderer.

Rules:
- source identity stays the same;
- chibi may intentionally alter proportions;
- outfit ownership/continuity still applies;
- use can be panel/scene/sequence scoped;
- do not train normal identity conditioning on chibi references;
- later create chibi-specific reference subsets if production needs them.

No immediate implementation work is required beyond preserving the distinction.

## 9. Storage / route plan

Do **not** add copyrighted datasets or the user's manga collection to the Git repository.

Use existing Continuum roots rather than inventing an unmanaged ninth root.

### Read-only source material
- user's 54 manga / owned references: Source Vault where appropriate;
- fan art / illustration collections: configured `CONTINUUM_INTAKE_ROOTS` read-only folders;
- third-party datasets: local read-only dataset/intake folders registered with provenance and license.

### Writable derived data
- thumbnails / crops / lineart / pose / depth / masks: `generated` or `cache` through the storage layer;
- training-ready materializations: derived artifacts referenced by manifest, never destructive rewrites of source;
- trained LoRAs / adapters / ControlNet-style weights: `models`;
- durable job state: `jobs` + database;
- project-specific selection/approval metadata: project/database layer.

### Git
Git stores:
- schemas;
- registry metadata;
- architecture;
- dataset licenses/URLs as metadata;
- benchmark definitions;
- House Style descriptions;
- code.

Git does not store:
- commercial manga pages;
- private user photos;
- fan art image corpora;
- gated datasets;
- generated model weights.

## 10. Training is downstream, not intake

Every item needs explicit allowed-use classification:

- `reference_only`
- `retrieval`
- `validator`
- `training_candidate`
- `training_approved`

Training approval requires separate rights/provenance review.

A beautiful image can be an excellent runtime reference and still be a bad or unauthorized training sample.

## 11. External datasets and internal collection are complementary

External manga/technical datasets can teach fundamentals:
- panels;
- reading order;
- character/text regions;
- pose;
- hands;
- line extraction;
- segmentation;
- layout.

The user's manga/fan-art corpus can teach:
- preferred solutions;
- atmosphere;
- rendering taste;
- scene-specific inspiration;
- eventual House Style evolution.

The goal is not to make The Arrivals look like a generic dataset. The goal is to avoid relearning basic visual structure while retaining project-specific direction.

## 12. Initial implementation order

1. dataset/visual-item registry + provenance;
2. external dataset audit;
3. runtime retrieval tags;
4. panel-stage artifact contract;
5. one simple end-to-end layered panel;
6. benchmark;
7. only then LoRA/control training;
8. expand to harder scenes after simple panels pass.
