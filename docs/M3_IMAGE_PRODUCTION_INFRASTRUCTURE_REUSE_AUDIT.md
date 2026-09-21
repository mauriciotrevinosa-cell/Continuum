# Image-production infrastructure — exact reuse points

Status: audit for the "next image-production infrastructure pass".
Branch: `m3/critical-path`. Written before any code in that pass was changed.

The pass adds purpose-aware reference routing, independent provider policy axes,
a hard paid budget, a paid image provider, a second model family, production
character sheets, prop scale locks, a foundation batch and a cross-provider
calibration benchmark. **None of it is a rewrite.** This document records what
already exists, what each new piece is built on, and what is genuinely missing.

## 1. What already exists (do not rebuild)

| Concern | Where | State |
| --- | --- | --- |
| Character Vault / profiles | `character_profile`, `continuum_library.catalog` | complete |
| Character corpus (observations, authority, status, role) | `character_observation`, `continuum_production.corpus` | complete |
| Character production models + evidence + approval | `character_production_model`, `character_production_evidence`, `continuum_production.character_models` | complete |
| Character **sheet attempts** (append-only, review, supersede) | `character_model_sheet_attempt`, `continuum_production.model_builder` | complete, but only `HEAD` / `FULL_BODY`, and **no real provider implements the contract** |
| Wardrobe / outfits / per-stage resolution | `character_outfit`, `outfit_wear`, `continuum_production.wardrobe` | complete |
| Reference Vault (classes, origins, aspects, technique facets, descriptors, standings) | `reference_item` + link tables, `continuum_core.references` | complete |
| Visual Knowledge retrieval (facet/term ranked, explains itself) | `continuum_library.knowledge.VisualKnowledge` | complete |
| External resource registry (license, access, allowed uses) | `external_resource`, `continuum_library.resources` | complete |
| Artwork/provider abstraction | `continuum_providers.artwork`, `.stages`, `.contracts` | complete |
| ComfyUI local/remote page + stage backend, IP-Adapter identity lane and scene lane | `continuum_providers.comfy` | complete for one SDXL-family checkpoint |
| Free-GPU notebook bootstrap + session recovery | `scripts/setup_comfy_free_gpu.py`, `scripts/kaggle_session_checkpoint.py` | complete, one preset |
| Calibration chapter parsing / runs / pages | `continuum_production.calibration`, `.manga` | complete, single provider per run |
| Layered construction (contracts, stages, freeze, staleness, compose) | `continuum_production.layered` | complete |
| Lineage / provenance / reproducibility checks | `rough_attempt.artwork_provenance`, `check_stage_result`, `check_result` | complete |
| Per-reference remote transmission policy | `continuum_providers.policy.transmission_refusal` | complete |
| Deterministic manifests | `reference_manifest`, `continuum_production.manifest` | complete (generic) |

## 2. What is missing, and what it is built on

1. **Purpose-aware routing.** Retrieval today answers "which references teach
   this stage's techniques?" and the provider re-derives a conditioning lane
   from the bundle role. Nothing records *what a reference was selected to
   teach*. Built on: `TechniqueFacet`, `BundleRole`, `VisualKnowledge.retrieve`,
   `ConditioningPurpose` (already in `continuum_providers.stages`).
2. **Independent policy axes.** `ProductionProfile` couples locality and cost:
   allowing a remote free GPU currently requires a profile that also admits
   paid providers. `comfy.remote` is already `REMOTE` + `FREE`, so the data
   model is right; only the *rule* is coupled. Built on: `ProviderPolicy`.
3. **Spend ledger.** No budget exists at all. Needs its own tables and a
   reservation protocol; there is no "estimate" concept in providers either.
4. **Paid image provider.** No provider declares `CostClass.PAID`. The
   descriptor, capability and registry machinery already supports one.
5. **Second model family.** `comfy.py` hardcodes an SDXL-shaped graph
   (`CheckpointLoaderSimple` → `CLIPTextEncode` → `KSampler`). A second family
   needs a graph builder per family, not a second provider.
6. **Character sheets that are actually renderable.** The pipeline exists; the
   missing pieces are (a) sheet kinds beyond head/body, (b) a variant key so
   one character can have several approved outfit/prop sheets, (c) at least one
   provider implementing `CharacterSheetProvider`.
7. **Prop / accessory scale.** `CharacterAspect.ACCESSORY` exists but carries no
   dimensions, so nothing can keep a recurring prop the same size twice.
8. **Foundation batch / cross-provider benchmark / LoRA dataset.** None exist.
   All three are compositions over things that do exist (recipes, attempts,
   manifests, the resource registry).

## 3. Rules this pass must not break

* the Source Vault stays read-only, and a verbatim source excerpt is still
  never transmitted to a remote provider unless the creator allows it;
* free never escalates to paid, and paid never escalates to more expensive;
* identity conditioning stays character-scoped: setting, style, technique,
  wardrobe and accessory references are never identity evidence;
* no franchise, character or project literal enters a generic engine schema;
* no model identifier outside the provider registry and config;
* nothing auto-approves artwork, and no paid request happens without an
  explicit, budgeted, creator-initiated action.
