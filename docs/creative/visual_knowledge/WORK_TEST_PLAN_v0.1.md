# Work Test Plan — Manga Renderer v0.1

**Purpose:** use Work only when a concrete vertical slice exists. Do not spend browser/computer credits exploring blindly.

## Gate 0 — before Work

Do not invoke Work merely to inspect architecture.

Required first:
- Claude/local integration audit completed;
- code implemented locally;
- local tests pass;
- one vertical slice is expected to work;
- test inputs and expected outputs are written down.

If the app or ComfyUI is accessible only on a private localhost that Work cannot reach, stop. Use Claude/local execution instead and give Work artifacts only if that provides value.

## Test W01 — CAL-01 environment

Cheapest meaningful end-to-end test.

Steps:
1. open Continuum;
2. locate the calibration run;
3. materialize CAL-01 panel contract;
4. inspect retrieved reference pack;
5. start render;
6. wait for durable job;
7. confirm artifact appears;
8. inspect lineage;
9. verify no invented cast/text;
10. record result.

Expected:
- correct settlement geography;
- renderer receives no character identity refs;
- stage outputs are preserved;
- page/panel relationship is correct;
- no source data is modified.

Capture:
- run/page/panel ids;
- artifact ids;
- provider/model/workflow/seed;
- manifest hash;
- screenshots;
- expected vs observed.

## Test W02 — simple identity panel

Only after W01 works.

Tests:
- one character;
- exact identity pack;
- wardrobe separately selected;
- no pseudo-text;
- regeneration preserves lineage.

## Test W03 — two-person quiet acting

Only after W02.

Tests:
- two distinct identities;
- shared composition;
- touch/eyeline;
- acting refs separate from identity;
- no face blending.

## Test W04 — CAL-18

Only after W03 is reliable.

Tests:
- Mau + Frieren;
- recovery acting;
- head contact;
- wardrobe;
- no speech balloons;
- subtle emotion.

## Test W05 — CAL-17

Last / expensive.

Do not spend Work credits here until the simpler tests pass.

Tests:
- action;
- cast;
- Sukuna-through-Mau geometry;
- Red/Blue;
- barrier;
- Mahoraga;
- no extra characters;
- causality.

## Work's role

Work should primarily:
- exercise the UI;
- trigger known workflows;
- wait through multi-step web/app operations;
- collect evidence;
- verify expected state transitions;
- report reproducible failures.

Work should **not** be asked in the same run to:
- discover architecture;
- redesign the pipeline;
- rewrite large code areas;
- randomly iterate prompts.

Use Claude/local for code changes after each test report.
