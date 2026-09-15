# M3 — AIComicBuilder adoption notes

Status: **external tool pinned; selective adaptation only**.

## 1. Upstream pin

Repository:

- upstream: `LingyiChen-AI/AIComicBuilder`
- pinned upstream commit: `e01e7dd501131922fb5051ec36926271d394b4d3`
- Continuum location: `tools/AIComicBuilder-upstream`
- integration form: Git submodule
- upstream license: Apache License 2.0

The submodule is intentionally kept clean. Continuum-specific edits must not be made directly inside it.

## 2. Why it is useful

AIComicBuilder already demonstrates several ideas relevant to the next Continuum phase:

- script/character pipeline separation
- project-level character management
- four-view character reference generation
- reference-image-aware frame generation in parts of its pipeline
- multiple image/video providers
- explicit style consistency prompting

The most immediately valuable piece is the **character turnaround / four-view concept**.

## 3. Important limitation

The current upstream `character-image` path builds one character turnaround largely from the character text description and asks for four views in a single 16:9 image.

That is not sufficient as The Arrivals' authoritative character model because our requirements are stronger:

- identity must be grounded in inspected source/creator references
- provenance/authority must survive
- wrong candidates must not silently become identity
- head and full-body coverage should be separated for readability
- generated sheets require human approval
- wardrobe is timeline/project state, not permanent identity

Therefore the upstream generator is an implementation reference, not a drop-in source of truth.

## 4. What Continuum should adapt

### A. Turnaround prompt structure

Reuse/adapt the useful four-view constraints:

- consistent character across views
- front / 3-4 / side / back
- consistent lighting/background
- consistent proportions/outfit within a sheet

Continuum changes the output standard to two sheets:

- HEAD: front / 3-4 / profile / back-hair
- FULL BODY: front / 3-4 / side / back

### B. Provider-neutral generation boundary

Where cleanly reusable conceptually, preserve the idea that character-model generation is a provider-backed job rather than UI-specific code. Continuum's existing provider/job/storage/provenance boundaries remain authoritative.

### C. Reference conditioning

AIComicBuilder's broader frame pipeline already passes character reference images in some generation paths. Study that mechanism, but implement reference conditioning through Continuum's own provider contracts and provenance rules.

The target is:

`confirmed evidence -> model-builder job -> generated candidate -> human review -> approved Production Model`

not:

`name/description -> generated image -> automatic canon`.

## 5. What Continuum should not import now

Do not spend the M3 character sprint importing:

- AIComicBuilder's whole Next.js application
- its database/schema wholesale
- its episode/video pipeline
- Seedance/Kling/Veo video generation
- duplicate project/character systems
- its complete prompt-management UI

These would create parallel sources of truth and consume the limited implementation window without advancing the first real manga page.

## 6. Relationship to ComfyUI

AIComicBuilder is **not a Comfy replacement decision**.

Current intended architecture remains:

`Continuum (source of truth / character state / manga page bundle) -> artwork provider -> ComfyUI local or remote -> outputs -> Continuum review`

AIComicBuilder contributes ideas/code for specialized preparation (especially model sheets) and possibly future provider patterns. If another image provider is added later, it should implement the same Continuum production boundary rather than bypass it.

## 7. Licensing discipline

Apache-2.0 allows adaptation subject to its terms. If source code from upstream is copied/modified into Continuum rather than merely studied:

- retain applicable copyright/license notices
- mark modified files as changed where required
- preserve any applicable NOTICE material if upstream later includes one
- document adapted source location/commit

The submodule itself retains upstream history/license.

## 8. First-sprint success criterion

We have used AIComicBuilder successfully when it helps us implement a better **Character Model Builder** inside Continuum without creating a second production system.

A successful result is not “AIComicBuilder runs.” A successful result is:

- Continuum accepts approved character evidence
- generates standardized model-sheet candidates
- preserves provenance
- requires human review
- feeds approved Production Models to the existing manga/Comfy pipeline.