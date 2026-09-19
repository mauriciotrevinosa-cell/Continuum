# External Manga / Drawing Dataset Audit v0.1

**Date:** 2026-09-19  
**Status:** web-verified discovery pass; no external bytes downloaded by this commit.

## Why this audit exists

Before Continuum spends time hand-building a "how manga works" dataset, use existing datasets, models and annotations where they already solve fundamentals.

The best current discovery is **Manga109-s v2026**: 87 professional manga volumes with panel/frame, face, body and text annotations, with terms that explicitly permit machine-learning/image-processing experiments and commercial use of resulting outputs/models under conditions. It is gated and redistribution of source images is forbidden.

This makes it a strong candidate for **manga fundamentals / structure / retrieval / validators**, subject to accepting its license and keeping its bytes local.

## Priority A — evaluate first

### Manga109-s v2026 — PRIMARY CANDIDATE

Official:
- https://manga109.github.io/manga109-project-website/en/
- https://huggingface.co/datasets/hal-utokyo/Manga109-s

Verified properties:
- 87 manga volumes;
- current v2026 release;
- professional Japanese manga;
- frame/panel, face, body and text annotations;
- gated download;
- source dataset redistribution forbidden;
- machine-learning and image-processing experiments are allowed;
- results/portions of results may be used commercially subject to stated conditions;
- published pretrained models/results must clearly indicate Manga109-s usage;
- direct copies/modifications of dataset images must not be treated as products.

Recommended Continuum uses:
- panel detection / cropping;
- manga page statistics;
- panel-layout grammar;
- character-count / body-region validators;
- reading-order experiments when combined with the panel-order estimator;
- line/screentone/reference retrieval experiments;
- benchmark material;
- potential training source **only after a local license acceptance record is stored**.

Do not:
- upload the dataset to Git;
- redistribute source pages;
- expose source pages through remote providers unless explicitly allowed;
- treat its visual style as The Arrivals House Style.

### Manga109 public annotations

Official:
- https://github.com/manga109/public-annotations

Includes:
- Manga109Dialog speaker-to-text relations;
- MangaUB annotations;
- Comic Onomatopoeia annotations.

Important:
- several annotation sets are CC BY 4.0;
- annotations still depend on Manga109 images for many uses.

Recommended:
- build validators and metadata enrichers without inventing labels ourselves;
- character count;
- background context;
- speaker/text relations;
- future lettering/balloon QA.

### Manga109 panel-order-estimator

Official:
- https://github.com/manga109/panel-order-estimator

MIT-licensed code that estimates reading order from panel bounding boxes.

Important:
- it does **not** detect panels itself;
- it can work with Manga109-style custom datasets.

Recommended:
- use as a baseline/reference for RTL page-reading order;
- do not make it the only layout engine; Continuum already owns intended page semantics.

### DiffSensei + MangaZero — HIGH-VALUE RESEARCH CANDIDATE

Official:
- https://github.com/jianzongwu/DiffSensei
- https://huggingface.co/datasets/jianzongwu/MangaZero
- https://jianzongwu.github.io/projects/diffsensei/

Why it matters:
- specifically targets customized B&W manga generation;
- supports character-conditioned manga panels;
- includes masked/region-aware control ideas;
- paper reports 43,264 manga pages / 427,147 annotated panels in the full training corpus;
- released MangaZero annotations currently expose tens of thousands of rows;
- DiffSensei code/model and MangaZero annotation card are marked MIT.

Critical rights caveat:
- the authors explicitly do **not** redistribute manga images because of license issues;
- annotations contain MangaDex URLs and the download script fetches images from there;
- MIT on annotation/code does not automatically grant training rights to every linked manga image.

Recommended:
- inspect architecture and annotation format immediately;
- consider DiffSensei as a renderer/provider experiment later;
- use annotations as structural research where permitted;
- do **not** mark downloaded MangaDex images training-approved automatically.

### MangaDiffusion / Manga109Story — RESEARCH DIRECTION

Official:
- https://siyuch-fdu.github.io/MangaDiffusion/
- https://github.com/siyuch-fdu/MangaDiffusion
- https://arxiv.org/abs/2412.19303

Why it matters:
- explicitly studies text-to-multi-panel manga;
- builds Manga109Story from Manga109 + dialogue annotations + panel order + MLLM captions;
- separates panels for generation and models intra-panel/inter-panel information.

Current limitation:
- public GitHub repository is minimal;
- dataset licensing must inherit/obey Manga109 constraints and should not be assumed production-ready.

Recommended:
- architectural reference;
- compare its dataset schema to Continuum's panel contracts;
- do not block our panel-first architecture waiting for its code.

## Priority B — preprocessing / control / validators

### MAGI / The Manga Whisperer

Official:
- https://github.com/ragavsachdeva/magi

Capabilities:
- panel detection;
- text detection;
- character detection/clustering;
- reading order;
- speaker association;
- OCR/grounding.

License:
- project states provided models/datasets are for academic research only.

Recommended:
- evaluate locally as a **development-time analyzer**;
- useful benchmark against our own importer/panel extraction;
- not production dependency until license/use is acceptable.

### Anime2Sketch

Official:
- https://github.com/Mukosame/Anime2Sketch

MIT-licensed code/weights according to repository.

Purpose:
- extracts sketches/lineart from illustration, anime and manga.

Recommended:
- potential derivative generator for Visual Knowledge;
- candidate for `lineart` stage extraction;
- benchmark against ComfyUI-native lineart preprocessors.

This is a tool, not a manga fundamentals dataset.

### Human-Art

Official:
- https://github.com/IDEA-Research/HumanArt

Properties:
- 50,000 images across natural and artistic scenarios;
- body/keypoint annotations;
- explicitly useful for controllable human generation.

Restriction:
- requested for non-commercial use.

Recommended:
- anatomy/pose research and validation only unless future license permits intended use;
- useful because artistic-domain poses are closer to our rendering problem than photo-only datasets.

### COCO-WholeBody

Official:
- https://github.com/jin-s13/COCO-WholeBody

Properties:
- 133 whole-body keypoints per person;
- face, hands, feet and body coverage.

Restriction:
- annotations described as research/non-commercial; image copyright remains separate.

Recommended:
- anatomy/keypoint validator experiments;
- not automatically production-training eligible.

### FreiHAND

Official:
- https://lmb.informatik.uni-freiburg.de/resources/datasets/FreihandDataset.en.html

Purpose:
- hand pose and shape.

Restriction:
- research only; commercial use prohibited.

Recommended:
- reference/validator research only;
- do not use as production training data without compatible permission.

### Informative Drawings

Official:
- https://github.com/carolineec/informative-drawings

Purpose:
- image-to-line drawing model with geometry/semantic objectives.

Recommended:
- architecture/preprocessing reference;
- possible line-derivative comparison.

This is more useful as a tool/method than as a prepackaged manga dataset.

## Priority C — niche / restricted / fallback

### eBDtheque

Official:
- https://ebdtheque.univ-lr.fr/

100 pages with panels, balloons, characters and text-line annotations.

Restriction:
- scientific/non-commercial computer-science use only unless separate validation is obtained.

Recommended:
- benchmark/validator research;
- too small and restricted to be a foundation.

### AMP-D — Artificial Manga Panel Dataset

Official:
- https://github.com/aasimsani/artificial_manga_panel_dataset
- https://www.kaggle.com/datasets/aasimsani/ampd-base

Synthetic page/layout/speech-bubble data.

Recommended:
- useful for layout/balloon parser testing where synthetic data is acceptable;
- not a source for artistic quality.

### DeepFashion2

Official repository/paper provide garment categories, landmarks and segmentation.

Recommended:
- clothing geometry/segmentation research;
- not a manga dataset;
- license/data-use terms need separate verification before any training use.

## Google suggestions that are NOT yet accepted

The pasted Google answer mentioned an "OpenSketch dataset" and generic "LineArt datasets."

Current audit result:

> no single unambiguous canonical OpenSketch package matching that description was verified in this pass.

Therefore:
- do not create a dependency named `OpenSketch` yet;
- do not download an arbitrary similarly named repository;
- keep the requirement as **line drawing / geometry dataset or extractor**;
- Anime2Sketch and Informative Drawings are verified concrete alternatives for the preprocessing side.

## Proposed foundation stack

For the first serious experiment:

1. **Manga109-s v2026** — manga fundamentals and annotated professional pages.
2. **Manga109 public annotations** — dialogue/character/background metadata.
3. **panel-order-estimator** — RTL reading-order baseline.
4. **DiffSensei/MangaZero annotations** — customized manga generation research and schema ideas.
5. **Anime2Sketch** — lineart derivative candidate.
6. User-owned 54-manga/fan-art corpus — project taste/reference layer, not mixed blindly into foundation training.

Technical pose/hand datasets are optional auxiliary research, not required to begin.

## Download/install policy

This commit intentionally downloads nothing.

Before any external dataset is materialized:
1. user accepts gated license if required;
2. Continuum stores dataset id/version/license/provenance;
3. bytes stay outside Git;
4. raw data is read-only to normal processing;
5. derivatives are content-addressed;
6. training eligibility is explicit per dataset/item;
7. remote-provider exposure is separately controlled.

This avoids spending hours ingesting a dataset we later discover cannot be used for the intended production path.
