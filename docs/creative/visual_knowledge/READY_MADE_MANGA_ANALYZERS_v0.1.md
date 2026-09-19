# Ready-Made Manga Analyzer Audit v0.1

**Date:** 2026-09-19  
**Purpose:** identify pretrained components that can remove work from Continuum before we train anything ourselves.

## 1. Manga panel + text detector — strong immediate candidate

Model:
- `leoxs22/manga-panel-detector-yolo26n`
- https://huggingface.co/leoxs22/manga-panel-detector-yolo26n

Model card states:
- trained/fine-tuned on Manga109-s;
- detects panel/frame and text regions;
- lightweight YOLO nano model;
- Apache-2.0 model license;
- manga-specific augmentations preserve RTL assumptions;
- current card reports strong panel/text detection metrics.

Why useful:
- Continuum does **not** need to train a panel detector first;
- candidate for page → panel box preprocessing;
- combine with Manga109 panel-order-estimator for a ready-made structural baseline.

Caveat:
- the model's license and the underlying Manga109-s conditions both need to be recorded;
- model results are usable under the model/dataset terms, but Manga109-s source images are still not redistributable.

## 2. RT-DETRv4 Manga109-s v2 — richer detector candidate

Model:
- `tori29umai/rtdetrv4-x-manga109s_v2`
- https://huggingface.co/tori29umai/rtdetrv4-x-manga109s_v2

Model card states it detects:
- body;
- text;
- frame;
- face.

It is trained on single-page/some-spread Manga109-s material and explicitly mentions:
- ComfyUI workflows;
- automated panel-unit processing;
- manga-domain research.

Why useful:
- one model can provide body/face/frame/text boxes;
- helpful for:
  - panel extraction;
  - cast-count validators;
  - face/body cropping;
  - automated Visual Knowledge descriptors.

Trade-off:
- much heavier than the nano YOLO detector;
- evaluate speed/accuracy locally before making it a default dependency.

## 3. Manga page element segmentation

Model:
- `anonimkaq4/manga-page-element-segmentation`
- https://huggingface.co/anonimkaq4/manga-page-element-segmentation

Detects/segments:
- character;
- frame;
- speech bubble.

Why useful:
- instance masks are stronger than boxes for:
  - masking;
  - character-aware editing;
  - stage freeze/protection;
  - panel element extraction.

Important caveat:
- model card explicitly tells users to review MangaSeg, Manga109-s and Ultralytics terms before commercial use/redistribution;
- do not mark production-approved until dependencies/licenses are audited.

## 4. Recommended no-training structural stack

For first local prototype:

```
manga page
   ↓
pretrained panel/text detector
   ↓
panel bounding boxes
   ↓
Manga109 panel-order-estimator
   ↓
ordered panels
   ↓
optional face/body/text analyzer
   ↓
Visual Knowledge item metadata
```

This means we can likely avoid spending our first training cycle on:
- panel detection;
- basic text-region detection;
- basic reading-order heuristics.

We should spend custom training effort on problems that are actually unique to Continuum:
- House Style;
- identity consistency;
- layered rendering;
- scene treatment;
- difficult action;
- project-specific visual preferences.

## 5. Evaluation order

A. Test `manga-panel-detector-yolo26n` on a small local sample.

B. Pair its boxes with `panel-order-estimator`.

C. Compare RT-DETRv4 on the same sample.

D. Add segmentation model only if masks materially improve the layered workflow.

E. Do not integrate all three as permanent dependencies by default. Select the simplest one that passes our benchmark.

## 6. Architecture rule

These are **analyzer providers**, not core domain logic.

Continuum core should depend on an interface such as:

`analyze_manga_page(bytes) -> detected regions / confidence / analyzer lineage`

so the chosen detector can be replaced later.
