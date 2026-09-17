# The Arrivals — Manga Renderer Architecture v0.1

**Status:** creator-directed production architecture  
**Date:** 2026-09-17  
**Scope:** visual generation boundary for manga production and calibration

Animagine is a **support renderer**, not the author of the manga page.

The failed whole-page calibration pass established a hard architectural rule:
Continuum must own sequencing, page geometry, identity scope, lettering and
manga finishing. A diffusion checkpoint may render a bounded visual problem,
but it must not decide what the page is.

## 1. Continuum owns

- source-script and creator-note interpretation;
- explicit panel beats and their order;
- Japanese manga reading order inside rows (right-to-left);
- panel rectangles, gutters, margins and page assembly;
- which characters are allowed in each panel;
- which identity references may condition each character;
- environment/continuity constraints;
- negative constraints;
- all dialogue, captions, SFX and final typography;
- the production B&W finish and final page geometry;
- provenance: panel seed, prompt, refs, model and workflow.

## 2. The image model owns only a bounded panel image

The image provider receives one panel at a time:

1. one exact visual beat;
2. one shot class;
3. only the characters present in that panel;
4. only those characters' confirmed identity references;
5. page-wide canon constraints relevant to that panel;
6. no authority to add lettering, extra panels or extra cast.

A provider must be replaceable without changing page semantics.

## 3. Identity conditioning

Never concatenate several characters into one undifferentiated identity batch.

For a multi-character panel:

- group references by character;
- give each character at least one confirmed identity reference when capacity allows;
- apply each character's identity conditioning as a distinct stage;
- record the exact references used per panel.

Panel isolation is the first defense against face/body blending. Regional or
mask-based identity control can strengthen this later without changing the
page contract.

## 4. No whole-page re-diffusion

A completed page is assembled deterministically from panel outputs.

Do not send the composed page back through an image-to-image diffusion pass for
"cleanup" or color. That pass can mutate faces, panel geometry, props and text.
Color support may be produced per panel later; until then the panel composite
is the geometry-preserving color/support derivative.

## 5. Lettering

Generated pixels must contain no dialogue balloons, captions, pseudo-Japanese,
logos or invented speech text.

Continuum letters the page after artwork. Story-critical typography must come
from exact authored text, never from diffusion-model spelling.

Physical in-world markings (for example a jersey name/number) require a
separate controlled placement/inpaint step; the base panel renderer should
reserve a clean surface rather than hallucinate the marking.

## 6. B&W is the manga target

The production manga is not a photo/color illustration converted at the last
second by a destructive threshold.

The B&W finish should preserve line structure, force real edges to ink, keep
highlights/paper clean and apply screentone only to genuine midtones. A future
specialist manga/line-art provider may directly emit a better B&W panel while
preserving the same PageRenderProvider contract.

## 7. Animagine's role

Animagine XL 4.0 is useful as:

- a free remote-GPU panel image generator;
- an anatomy/composition support model;
- a color/support draft source;
- a calibration backend while stronger manga-specific components are added.

It is **not** responsible for:

- page layout;
- panel sequencing;
- manga lettering;
- cast assignment;
- continuity decisions;
- final B&W semantics.

This separation is intentional so a better panel renderer can replace or
complement Animagine without rewriting Continuum production.

## 8. Calibration consequence

The earlier whole-page renders remain useful evidence that infrastructure,
ComfyUI, IP-Adapter and remote execution work. They are not style targets.

New calibration attempts should test:

- deterministic panel geometry;
- identity isolation per panel;
- no model-generated lettering;
- page-beat readability;
- line-preserving B&W;
- progressively harder multi-character panels only after simple panels pass.
