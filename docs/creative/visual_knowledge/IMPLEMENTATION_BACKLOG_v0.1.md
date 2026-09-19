# Visual Knowledge / Layered Renderer — Implementation Backlog v0.1

**Status:** implementation-ready backlog  
**Rule:** extend Continuum's existing reference, job, storage and production systems. Do not create a parallel app.

## Phase 0 — prerequisites already present

Continuum already has:
- read-only Source Vault;
- read-only intake roots;
- content-addressed derived storage;
- durable jobs;
- reference classes / facets / bundle roles;
- character identity separated from wardrobe;
- project reference manifests;
- rough recipes with masks, operations, placements and lineage;
- Comfy providers;
- panel/page production UI;
- panel-first renderer architecture;
- non-canon calibration chapter.

The implementation should reuse these.

## Phase 1 — dataset / Visual Knowledge registry

### Goal
Represent external datasets and local Visual Knowledge sources without ingesting bytes into Git or silently marking them training-safe.

### Required additions
- dataset record:
  - stable id;
  - display name;
  - version;
  - source URL;
  - local locator/root key;
  - license text/hash or acceptance record;
  - access/gated state;
  - allowed uses;
  - training policy;
  - last indexed timestamp;
  - manifest hash.
- visual item record:
  - source locator + hash;
  - parent page/video/process relation;
  - functional tags;
  - descriptors;
  - allowed uses;
  - review state;
  - derivative references.

### Existing code to inspect first
- `packages/core/src/continuum_core/references.py`
- `packages/production/src/continuum_production/manifest.py`
- `packages/storage/src/continuum_storage/derived.py`
- `packages/library/src/continuum_library/`
- `packages/db/src/continuum_db/models/`

### Acceptance
- no raw external dataset image is copied to Git;
- same source bytes dedupe by content hash;
- unknown/restricted rights are visible;
- reference use and training use are separate decisions.

## Phase 2 — importer / indexing durable jobs

### Goal
Index a directory/dataset incrementally.

Jobs:
- dataset scan;
- hash/index source;
- page metadata extraction;
- optional panel extraction;
- derivative generation;
- enrichment;
- rescan/diff.

Requirements:
- resumable;
- deterministic;
- source is never mutated;
- job restart is idempotent;
- progress visible in UI/API;
- individual corrupt files do not destroy whole import.

## Phase 3 — manga structural derivatives

Candidates:
- panel boxes;
- reading order;
- text/speech regions;
- face/body regions;
- character count;
- lineart;
- pose/keypoints;
- depth/segmentation when useful.

External tools are providers/analyzers, not hardwired into core.

Initial research candidates:
- Manga109-s annotations;
- Manga109 panel-order-estimator;
- MAGI for research comparison;
- Anime2Sketch for lineart;
- later other compatible analyzers.

## Phase 4 — retrieval

### Goal
Given one Panel Contract, retrieve a small evidence pack by role.

Input examples:
- cast count;
- shot;
- angle;
- acting;
- action intensity;
- environment;
- special challenge (hands, carrying, crowd, magic);
- house-style version;
- scene treatment.

Output:
- ranked references grouped by role;
- rationale / matched descriptors;
- rights/training warnings;
- exact ids/hashes in the production manifest.

Hard rule:
identity references are never substituted by style references.

## Phase 5 — layered panel state

Introduce a stage vocabulary such as:
- COMPOSITION
- DRAWING
- LINE
- VALUE_MATERIAL
- LIGHT_SHADOW
- FX
- ENVIRONMENT_INTEGRATION
- FINISH
- LETTERING

Need:
- stage artifact id;
- parent stage/artifact;
- input manifest hash;
- provider/workflow/model/seed;
- masks/protected regions;
- review state;
- invalidation graph.

### Freeze semantics
A downstream stage cannot mutate protected upstream structure unless the recipe explicitly authorizes that category of change.

## Phase 6 — vertical slice

Do **one environment-only panel** end to end before training anything.

Suggested target: CAL-01.

Prove:
story/calibration contract
→ retrieve refs
→ composition
→ drawing/line or direct bounded renderer
→ finish
→ artifact lineage
→ UI review.

No LoRA training required for this milestone.

## Phase 7 — benchmark runner

Run a small fixed suite with exact seeds/settings and store:
- attempt;
- configuration;
- refs;
- outputs;
- creator verdict;
- objective validator results where available.

Only compare model/dataset changes against the fixed suite.

## Phase 8 — training orchestration

Only after corpus + benchmark are working:
- materialize an exact training manifest;
- train a style LoRA or other adapter;
- store config/dataset hash/base checkpoint hash;
- save weights under `models`;
- register lineage;
- run benchmark before promotion.

Do not train from the entire 54-manga corpus by default.

## Phase 9 — UI

Minimum useful UI:
- Dataset Registry;
- Visual Knowledge browser/filter;
- source + derivatives;
- review / allowed-use controls;
- training candidate approval;
- per-panel reference pack;
- stage inspector;
- regenerate a stage;
- artifact lineage.

## Phase 10 — chibi later

Chibi/super-deformed already exists conceptually as `COMEDIC_DEFORMATION`.

Later work:
- tag chibi source references separately;
- prevent them from contaminating normal identity training;
- optionally create chibi character packs;
- allow panel/scene scoped chibi treatment.

Not urgent for the first vertical slice.
