# Visual Knowledge Storage / Intake Routes v0.1

**Goal:** make Visual Knowledge fit Continuum's existing root model without creating unmanaged folders.

## Existing roots

Continuum already defines:

- `source_vault` — read-only owned/source media;
- `library` — library/acquisition state;
- `projects` — project data;
- `generated` — derived artifacts;
- `jobs` — job data;
- `models` — model weights/adapters;
- `cache` — disposable/rebuildable cache;
- `config` — configuration.

Do not introduce `visual_knowledge_root` unless a later architecture audit proves a real need.

## Route by material type

### User-owned manga collection
Preferred:
- Source Vault when it is already part of the user's durable media collection.

Properties:
- immutable/read-only;
- indexed, not copied;
- page/panel locators point back to source hashes.

### Fan art / illustration collection
Preferred:
- read-only `CONTINUUM_INTAKE_ROOTS`.

Example conceptual config:

```
FanArt:fan_art=D:/Continuum-Intake/FanArt
Illustration:illustration=D:/Continuum-Intake/Illustration
ArtistProcess:process=D:/Continuum-Intake/ArtistProcess
```

These are examples, not mandatory Windows paths.

Properties:
- source bytes remain outside Git;
- no automatic training approval;
- creator/source metadata retained when known.

### External datasets
Preferred:
- read-only intake folders, one collection per dataset/version.

Conceptual:

```
Manga109s:manga_dataset=D:/Datasets/Manga109-s-v2026
HumanArt:pose_dataset=D:/Datasets/Human-Art
```

Before indexing:
- register version;
- record URL;
- record license;
- record local acceptance/gated state;
- choose allowed uses.

### Derived crops / panels / lineart / masks / pose / depth
Preferred:
- `generated` for durable derived artifacts;
- `cache` only if safe to regenerate and not part of durable lineage.

Use content-addressed storage through Continuum. Never create arbitrary path trees by concatenating user input.

### Training materialization
A training run should not consume a hand-maintained folder as its source of truth.

Instead:
1. select approved item ids;
2. resolve exact source/derivative hashes;
3. create a training manifest;
4. materialize a temporary/reproducible training view;
5. train;
6. keep manifest/config/hash as lineage.

Temporary training views may live under jobs/cache; durable selected derivatives remain content-addressed.

### Trained weights
Store:
- LoRA;
- adapter;
- ControlNet-like weights;
- fine-tuned checkpoints

under the existing `models` root, registered with:
- base model;
- base hash;
- training manifest hash;
- config;
- software/version;
- license;
- benchmark result.

## Git policy

Allowed:
- metadata;
- schemas;
- registry records without secrets/local absolute paths;
- URLs;
- license summaries;
- code;
- benchmark definitions.

Forbidden:
- commercial manga images;
- user's private photos;
- bulk fan art;
- gated dataset bytes;
- model weights unless a separate explicit repository policy permits them.

## Remote-provider policy

A source being locally usable does not mean it may be sent to COMFY_REMOTE or another remote provider.

At render time, reference resolution must also check:
- data class;
- rights;
- provider policy;
- remote-source-excerpt setting.

The safest default for external copyrighted datasets is local processing/reference only unless explicitly allowed.
