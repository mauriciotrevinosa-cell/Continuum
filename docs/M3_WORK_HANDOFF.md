# M3 work handoff

## W5 checkpoint — Exercise first character batch — 2026-09-15

W5 exercised the generic Production Model / evidence workflow against the real
early cast and closed the one genuine gap: the Production Model API existed but
the creator had no UI to create, review or approve a model, so the flow could
not actually be driven end to end. A new `ProductionModelPanel` on the
character page now lets the creator create a DRAFT model for a project, attach
confirmed observations by role (identity/body/wardrobe/expression/pose/
accessory/scale), submit for review, and approve with a reviewer name. Approval
still supersedes the previous approved version and never self-approves.

Real data state (verified against the app DB, not manufactured):

- **Mau** (`01a0a1ac-3b87-73ec-82e3-2ca783d4cf38`, PROJECT_ORIGINAL): 11
  confirmed observations (10 CREATOR_PRIMARY grounding + 1 PROJECT_CREATED
  stylization "Mau - Anime V2 aceptado / ropa pendiente"). Identity/body/
  expression/pose READY; wardrobe and accessory PARTIAL. No production model
  yet. E1 outfit exists as a PROJECT outfit ("E1 — ropa funcional / concepto
  exploratorio"). Forbidden rules correctly surface "E1 SIN LENTES" and the
  later-glasses progression. V2 clothing remains stylization-only, not
  identity/body/wardrobe.
- **Frieren** (`01a09cdd-4391-72dd-8b3e-b7aa0ad6b962`, SOURCE_WORK): 4
  confirmed + 361 candidates. The invalid body anchor
  `01a0a2c1-916a-7427-80f1-c548b1fdea00` ("Frieren full figure, opening
  chapter" = contents/index page) is still CONFIRMED and must be rejected by
  the creator. Ch91 p14 (`01a0a2c1-91c7-72b9-9561-dc7647139aaa`) and Ch123 p13
  (`01a0a2c1-91c7-72f9-8980-85537c1ba025`) remain CANDIDATE and must be
  rejected. The recommended replacement pack (Ch1 p14, Ch2 p13, Ch3 p24,
  Ch5 p14, Ch6 p7) is present as CANDIDATE and awaits creator confirmation.
- **Fern** (`01a09cdd-d675-71c9-9ceb-fa37936c62fa`, SOURCE_WORK): 1 confirmed
  (FACE only) + 294 candidates. Body/wardrobe/expression/pose all MISSING; not
  grounded. No outfit yet.
- **Stark**: no `CharacterProfile` exists yet. The roster-driven intake flow
  (W2) is the correct path to create him; no code change is required.

No creator approvals were impersonated. No production model was created or
approved on the creator's behalf. The exact creator actions remain in
`docs/M3_FRIEREN_REFERENCE_REVIEW.md` §7.

Validation: web `pnpm typecheck`, `pnpm lint` (no warnings), and 21 web tests
all pass. No migration was needed. UI route:
`/library/characters/{character_id}` (new Production model panel).

## W4 checkpoint — Character Model Builder — 2026-09-15

W4 is implemented at commit `cc79391` on `m3/critical-path`. Continuum now has
a provider-neutral `CHARACTER_MODEL_RENDER` job for reference-grounded HEAD
(front, three-quarter, profile, back hair) and FULL BODY (front,
three-quarter, side, back) candidates. Requests are accepted only from a
Production Model in REVIEW or APPROVED state and snapshot its confirmed typed
evidence, identity rules, restrictions and active outfit before the durable GPU
job is queued.

Generated sheets are stored content-addressed as `GENERATED` references with
`visual_origin=PROJECT_CREATED`. Each attempt records provider/backend, model
identity and hash, workflow identity and hash, exact settings, seed, source
evidence and parent attempt. A human can inspect, reject or regenerate a
candidate. Approving a sheet records the reviewer and creates a new DRAFT
Production Model version; it does not approve that model or claim creator
approval. Approved sheets of the same type supersede, and the new version also
keeps the latest approved sheet of the other type.

The character page exposes the builder, attempt/job state, candidate image,
provenance summary and review actions. The shipped registry currently has no
real `CHARACTER_MODEL_RENDER` provider, so the UI reports the exact missing
backend action and no job or placeholder artwork is created. AIComicBuilder
remains pinned and untouched at `e01e7dd501131922fb5051ec36926271d394b4d3`.

Database: app DB is at `0009_m3_model_builder`. Required pre-migration backup:
`C:/ContinuumData/backups/continuum-pre-0009-20260915-053915.dump` (3,221,923
bytes). Validation: the full Python suite passed after the W4 integration
fixes, with the single expected POSIX-only skip on Windows. The final human
review constraint then passed the W4 and schema-drift tests. Ruff, mypy (115
source files), all four import contracts, web lint/typecheck, 21 web tests and
the Next.js production build passed. Source Vault bytes were verified unchanged
by the W4 acceptance flow.

UI route: `/library/characters/{character_id}`. W5–W8 are not started in this
checkpoint. W5 creator work remains Mau, Frieren, Fern and Stark in that order;
Mau and Frieren first. Frieren still needs the explicit reference decisions in
`M3_FRIEREN_REFERENCE_REVIEW.md`; Mau must retain creator-primary identity,
V2 stylization-only status, rejected V2 clothing and the E1 no-glasses rule.

## W3 checkpoint — Human-steered evidence loop — 2026-09-15

W3 is implemented at commit `b61fc8c`. The existing held-material search,
candidate filters and observation review controls were retained and completed:
reference detail now presents a clear Add to character action with character,
typed aspect/use, optional outfit and optional preferred-seed status. Removing
an association continues to leave the underlying reference and source intact.

Corpus review already exposes confirm/reject-association, atypical, anchor,
facet, angle, framing-derived hints, expression, pose and independent visual
origin. The new backend guard also prevents STYLE, MOOD and TECHNIQUE references
from being changed into grounding identity evidence, including through a later
manual review. Candidate uncertainty remains visible and candidate observations
remain excluded from production identity. Validation: full M3 character-corpus
acceptance file, ruff, mypy and Next.js production build pass. No migration was
needed. Next checkpoint: W4, provider-neutral reference-grounded HEAD/FULL BODY
model-sheet candidates with truthful backend gaps and human review.

## W2 checkpoint — Roster-driven character intake — 2026-09-15

W2 is implemented at commit `fc4d52f`. The character creation screen now uses
a searchable, scrollable family/series input sourced from catalogued holdings
and existing character profiles. It shows held media counts, exposes maintained
catalog aliases, scopes character autocomplete to the selected family, and
opens an existing matching profile rather than creating a duplicate. Manual
families and an Original / Custom path remain available.

An optional project/story snapshot creates a draft Production Model version and
records the small structured snapshot in `created_from`; it does not approve the
model or turn the profile into a lore database. The roster is data-driven and
requires no per-character UI source changes. Validation: focused HTTP acceptance
test, franchise-neutrality invariant, ruff, mypy, TypeScript and Next.js
production build pass. No migration was needed. Next checkpoint: W3, the
human-steered evidence discovery and review loop.

## W1 checkpoint — Character Production Model — 2026-09-15

W1 is implemented at commit `d436108` on `m3/critical-path`. Continuum now has
project-scoped, versioned character production models with typed evidence,
separate active wardrobe and identity-sheet fields, explicit DRAFT -> REVIEW ->
APPROVED workflow, human reviewer attribution and automatic supersession. A
partial unique index prevents two approved versions for one character/project.

Approved model evidence is placed before general confirmed corpus evidence in
page bundles and is deduplicated there. Candidate or rejected observations
cannot be attached; stylization/project-created evidence cannot define identity,
body or wardrobe. Existing projects with no production model retain the prior
corpus-based behavior. The character page now shows a prominent Production
model panel with project, status, version, evidence count, active outfit, sheets,
identity rules, restrictions and reviewer.

Database: app DB is at `0008_m3_models`. Required pre-migration backup:
`C:/ContinuumData/backups/continuum-pre-0008-20260915-050529.dump` (3,209,185
bytes). Validation: new W1 acceptance tests pass; the existing full page-loop
test passes with approved-model priority asserted; DB invariants, ruff and mypy
pass; the Next.js production build passes. No Source Vault files, real project
creative approvals, generated artwork, SAMPLE PASS or canonical run were made.

Next checkpoint: W2, workflow templates and deterministic input bindings.

## Codex continuation — 2026-09-15

See `docs/M3_CODEX_VISUAL_QA.md` for the 16-page visual audit, evidence shortlist,
Page 3 review pack and stop condition B. Recent-page craft diversity is now
implemented and active on API port 8002: repeated grammar sets 4 -> 1, possible
repeated compositions 2 -> 1. Full suite: 569 passed, one explicitly POSIX-only
skip on Windows; Python checks and web lint/typecheck passed.

Critical visual finding: the inherited confirmed Frieren full-body reference
is a contents page, not usable body evidence. Ch91 p14 and Ch123 p13 are not
verified Frieren appearances. Creator must review the supplied replacement
shortlist; confirmation state has not been impersonated. Two source forest
pages were tagged for environment, but seven automatic environment gaps remain.
Mau clothing is still unapproved. Sample Page 3 stays READY, zero attempts,
continuity v3. No GPU, SAMPLE PASS, canonical run or new art pipeline.

The original handoff below records the starting checkpoint; its diversity
follow-up is superseded by the continuation above.

Branch: `m3/critical-path` (unmerged). Head: see `git log -1` (the commit that adds
this file). Previous checkpoints: `aa06785` (web loop, corpus, ComfyUI),
`d97cf64` (plans, full-page references, preview, QA, visual origin backend),
`69a7c5b` (web: cast, references, job status, chapter review).

Safe to continue: **yes**. All tests, ruff, mypy, import-linter and the web
checks passed at the last commit. The app database is migrated.

## Database

- App DB `continuum` is at **`0009_m3_model_builder`**. Backups taken before each
  migration: `C:/ContinuumData/backups/continuum-pre-0005-*.dump`, `-0006-*`,
  `-0007-*`, `-0008-*`, `-0009-*`.
- No further migration is pending. Before any new migration: take a
  `pg_dump -Fc` backup first (see `docs/M3_MANGA_PRODUCTION.md`), then
  `uv run --no-sync python -m alembic upgrade head`.
- Never run DB test files while a full suite runs: they share `continuum_test`.

## Current real data state (S1E1 Chapter 2)

| Run | Id | Purpose | State |
|---|---|---|---|
| Sample | `01a0a2c4-87f6-7727-b793-986c0165eabb` | NON_CANON_SAMPLE | 16 pages; pages 1-2 approved as a sample technical pass (TEST renders); page 3 READY; continuity v3; no sample decision |
| Chapter technical preview | `01a0a36c-ee44-7440-940d-204807948f2a` | WORKFLOW_TEST | 16 pages, all test-rendered, never approved |

No SAMPLE PASS. No canonical run. The sample run's TEST-render approvals can never pass a sample.

Latest chapter QA on the preview: 16/16 rendered, 16 with grammar pages, 0 cast
warnings, 0 character-reference warnings, 7 environment gaps, 4 repeated grammar
sets, 2 possible repeated compositions, 14 pages carrying unverified Frieren
candidates. The same two candidate pages (Chapter 91 p14, Chapter 123 p13) appear
on 14 pages, and several grammar pages repeat on 9-16 pages.

## Routes to test

- `http://127.0.0.1:3001/projects/the-arrivals/manga/production`
- Sample run: `/production/runs/01a0a2c4-87f6-7727-b793-986c0165eabb`
- Sample chapter review: `/production/runs/01a0a2c4-87f6-7727-b793-986c0165eabb/chapter`
- Preview chapter review: `/production/runs/01a0a36c-ee44-7440-940d-204807948f2a/chapter`
- A page: `/production/runs/{run}/pages/{page}` (cast, full-page refs, job status)
- Characters: `/library/characters/{id}` and `/library/characters/{id}/corpus`
- Diagnostics: `/settings/diagnostics`
- Roughs (`/production/roughs/...`) is the separate ADVANCED / OVERRIDE tool.

## Commands

```
# stack (from the Claude app: .claude/launch.json configs continuum-api, continuum-worker, continuum-web)
uv run --directory C:\Continuum --no-sync continuum-api
uv run --directory C:\Continuum --no-sync continuum-worker
cd apps/web && pnpm build && next start -p 3001
# checks
uv run ruff check . && uv run ruff format --check . && uv run mypy packages apps workers && uv run lint-imports
uv run pytest tests/acceptance/test_m3_page_production.py tests/acceptance/test_m3_chapter_preview.py tests/acceptance/test_m3_character_corpus.py tests/acceptance/test_m3_comfy_backend.py
uv run pytest
cd apps/web && pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

The first manga page or chapter view after an API restart takes 15-25 s while
grammar layouts are measured and cached in memory; later requests take about 1-2 s.

## DONE

- **Automatic page cast.** `continuum_production/plan.py::page_plan` derives
  `characters_present`, `primary_character`, `supporting_characters`, speakers,
  unmapped speakers, uncertainty, `primary_intent` and `environment_tags` from
  script names and dialogue speakers.
  - A recorded override is stored in `production_page.cast_override`
    (`POST /production/pages/{id}/cast`, "Correct the cast" UI).
  - The plan's cast drives grounding checks, dependencies, corpus retrieval and bundles.
- **Full-page references by role.** `plan.py::page_references`, in the bundle
  as `grammar`, `technique` and `environment_pages`.
  - Each carries `role`, `why`, `teaches`, `status` (LAYOUT_MATCH or CANDIDATE),
    `identity_evidence: false` and an image served from
    `GET /production/source-pages/{unit_key}/{offset}/image`.
  - They are sent to backends as GRAMMAR / TECHNIQUE / ENVIRONMENT inputs,
    never as CANON.
- **Visible job status.** The page view shows queued / rendering / complete /
  failed, with a spinner, requested, started, last-update and finished times,
  the failure reason, and polling. A "WORKFLOW TEST - NOT ARTWORK" banner
  appears for the test backend.
- **Chapter technical preview.** A `WORKFLOW_TEST` run
  (`POST /production/runs/{id}/preview`, then `POST .../preview-render`).
  - Every page is READY, rendered only by the test backend, never approved,
    and never feeds continuity.
- **Chapter review.** `/production/runs/{id}/chapter`, backed by
  `GET /production/runs/{id}/chapter`.
  - It lists every page with plan, character refs, grammar and technique
    thumbnails, environment status, test render and warnings.
  - `manga.py::chapter_qa` flags problems and fixes nothing.
- **Visual origin.** `reference_item.visual_origin` is kept apart from
  `origin`/provenance.
  - Set it via `POST /library/character-observations/{id}/visual-origin` or the
    corpus explorer select.
  - Official anime or art moves an observation to OFFICIAL authority; it stays
    a candidate until confirmed. Refreshes keep the judgement.
- **Candidate safety.** The ComfyUI adapter never uses CANDIDATE observations
  for identity conditioning (`candidates_not_used_for_identity` in provenance).
  QA flags bundles with only candidates or with candidates present.
- **Test renderer caption.** It shows WORKFLOW TEST, integrated page, origin,
  scene, cast, intent and dialogue count.

## PARTIAL

- **Technique and environment pages are chosen from measured layout** (panel
  count, largest panel, negative space, ink). Their content is not verified;
  each says so.
  - Environment has no tagged references yet: gap on 7 pages.
  - Tagging exists: "Use as environment" on corpus observations.
- **Grammar/technique selection lacks per-chapter diversity.** The same pages
  recur across the chapter; QA flags it.
- **Candidate observations still enter sample bundles** (flagged), and the same
  two Frieren candidates recur. Real identity grounding needs the creator to
  confirm corpus pages.
- **Chapter review has no cast warnings** because the real script names
  everyone. Speaker mapping uses first names only.

## NOT STARTED

- Grammar layout index persisted in the database (handoff T5): the cache is
  per API process.
- Remote bundle export/import (T2), episode package (T6), corpus hints (T7).
- Any real GPU run.

## Known bugs / rough edges

- **Grammar cache is lost on restart:** the first chapter view is slow.
- **Chapter view cost:** it calls `assemble` for every page on each load (16
  pages is about 2-5 s warm).
- **`distinct_sources` counts** curated references by reference, not by source
  volume.
- **`PAGE_STATE`** of a preview page shows IN_REVIEW after rendering; that is
  expected and it can never be approved.

## Next highest-value task

1. Connect a real GPU ComfyUI endpoint: `CONTINUUM_COMFY_LOCAL_URL` or
   `CONTINUUM_COMFY_REMOTE_URL`, plus `CONTINUUM_COMFY_CHECKPOINT`, `_VERSION`,
   `_SHA256`, `_LICENSE`, `_SOURCE`, and IP-Adapter nodes installed.
   - For a remote server, decide `CONTINUUM_COMFY_REMOTE_ALLOW_SOURCE_EXCERPTS`.
   - Render only sample page 3 (READY) and stop for creator review.
2. Before that, the creator confirms a handful of Frieren corpus pages (face,
   body, wardrobe, angles) in `/library/characters/{frieren}/corpus`. Frieren
   then stops relying on candidates and has more than 4 confirmed references.
3. Add chapter-level diversity to grammar/technique selection (penalise
   locators already used on the previous 2 pages). Small change in
   `plan.py`/`rank_grammar`, with a QA test.

## ComfyUI status

The adapter is implemented and tested against a fake server. **No real GPU
endpoint is configured**: both COMFY_LOCAL and COMFY_REMOTE report "not
configured". No artwork has been generated.
