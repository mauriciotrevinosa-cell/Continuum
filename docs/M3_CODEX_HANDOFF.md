# M3 — Codex delegation package

Read `docs/M3_MANGA_PRODUCTION.md` first. The production semantics (runs,
pages, continuity, review, invalidation, promotion) are **done and tested**.
Every task below plugs into them; none may change them.

Global rules for every task:

* Public repository: no personal library titles, handles or media in code,
  tests, docs or commit text. Tests use invented names only.
* The Source Vault is read-only. Nothing is written into it; nothing from it is
  uploaded. Remote backends receive only a page bundle.
* No paid API or service. A backend that costs money is out of scope.
* No client-supplied filesystem paths (F-50). Address records by id.
* `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy packages apps workers`, `uv run lint-imports` and
  `uv run pytest` must pass. Web: `pnpm --dir apps/web lint`, `typecheck`,
  `build`.

---

## T1 — ComfyUI page backend (`COMFY_LOCAL` / `COMFY_REMOTE`)

**Objective.** A real `PageRenderProvider` that drives a ComfyUI server over
HTTP and returns a composition master plus black-and-white and color finishes.

**Architecture decision.** One adapter class, two registrations: local
(`http://127.0.0.1:8188`) and remote (URL from settings). The adapter never
reads the Vault or the database; it receives a `PageRenderRequest` whose
references already carry bytes.

**Files.**
* `packages/providers/src/continuum_providers/comfy.py` (new)
* `packages/providers/src/continuum_providers/registry.py` (register only when
  configured)
* `packages/config/src/continuum_config/settings.py`: `comfy_local_url`,
  `comfy_remote_url`, `comfy_workflow_dir`, `comfy_timeout_seconds` (all
  optional; absent ⇒ backend not registered)
* `packages/providers/workflows/page_v1/` (new): workflow JSON templates plus a
  `workflow.json` manifest `{id, version, sha256, nodes: {...}}` and a
  `MODELS.md` listing the checkpoint/adapter files expected, their sha256,
  license and source URL. **Do not download models from code.**

**Interface.**
```python
class ComfyPageProvider:
    backend: ArtworkBackendKind          # COMFY_LOCAL or COMFY_REMOTE
    capabilities: ArtworkCapabilities    # read from the workflow manifest + /object_info
    descriptor: ProviderDescriptor       # id "comfy.local" / "comfy.remote", Capability.PAGE_RENDER,
                                         # Locality LOCAL/REMOTE, CostClass.FREE, rough_output ARTWORK_CANDIDATE
    def render_page(self, request: PageRenderRequest) -> PageRenderResult: ...
```

**Behavior.**
1. `GET /object_info` once; if a node the workflow needs is missing, raise
   `ProviderUnavailableError(blocked_reason="MISSING_MODEL")` naming it.
2. Upload every reference image (`POST /upload/image`, unique names derived
   from sha256). CANON → identity conditioning nodes; CONTINUITY → identity
   and wardrobe; GRAMMAR → layout/composition conditioning only (low weight,
   never identity); ENVIRONMENT → background/perspective conditioning.
3. Fill the template: positive/negative prompt built from `request.page`
   (directions, constraints, intents) and `request.continuity`
   (`character_rules`, e.g. forbidden accessories become negatives), seed,
   width, height, `request.settings`.
4. Master first (`POST /prompt`, poll `GET /history/{id}`, fetch
   `GET /view`). Then the color finish **conditioned on the master**
   (img2img/control over the master, same size), and the black-and-white
   finish either from ComfyUI (same size) or
   `continuum_imaging.manga.bw_finish(master)`.
5. Provenance: `backend`, `model{name, version, sha256, license, source}` from
   `MODELS.md` values verified against `/object_info` file names, `workflow{id,
   version, sha256}` from the manifest, `settings` as actually sent, `seed`,
   `master_sha256`.
6. Timeouts and connection errors ⇒ `ProviderUnavailableError`
   (`MISSING_PROVIDER`) with remediation; the job stays retryable.

**Invariants.** Finishes share the master's geometry. `check_result()` must
return `[]`. No reference leaves the machine unless the backend is
`COMFY_REMOTE`, and then only the request's references.

**Tests.** `tests/providers/test_comfy_adapter.py` with an in-process fake
ComfyUI (a small ASGI app or `httpx.MockTransport`) that records uploads and
returns deterministic PNGs. Cover: capability discovery, missing node ⇒
MISSING_MODEL, reference roles routed to the right nodes, finishes same size,
full provenance, timeout ⇒ retryable error, remote receives exactly the
request's references.

**Acceptance.** With the fake server configured, the M3 acceptance loop
(`tests/acceptance/test_m3_page_production.py` pattern) runs with
`provider_id = "comfy.local"` and yields `ARTWORK_CANDIDATE` pages.

**Must NOT change.** `artwork.py` contracts, `manga.py`, `render.py`
semantics, migrations.

**Done when.** Tests pass; `docs/M3_MANGA_PRODUCTION.md` §5 updated with how to
start ComfyUI locally and which files `MODELS.md` expects.

---

## T2 — Remote page bundle (opportunistic free GPU)

**Objective.** Run `COMFY_REMOTE` against a ComfyUI started in a free notebook
session the user opens themselves. Not a production dependency.

**Decision.** No cloud infrastructure. The user starts a notebook, launches
ComfyUI with a tunnel URL, and pastes the URL into settings. Continuum talks to
it through T1. Optionally, an offline mode: export one attempt's bundle as a
zip, run it in the notebook, import the result.

**Files.** `packages/production/src/continuum_production/bundle_export.py`,
`scripts/page_bundle.py` (`export --attempt ID --out DIR`, `import --attempt
ID --result ZIP`, dry-run by default), `docs/M3_REMOTE_BACKEND.md`.

**Bundle format** `continuum.page-bundle-export/1`: `manifest.json` (page,
plan, continuity, settings, seed, width, height, references
`[{role, sha256, file, character, facet, teaches}]`), `refs/<sha256>.<ext>`.
Only the attempt's inputs and continuity masters. Never profile series lists,
never catalog data, never file paths.

**Import.** Accept `master.png`, `bw.png`, `color.png`, `provenance.json`;
validate with `check_result()`; store through the same code path as
`_render_page` (factor a shared `record_page_result`). Refuse if the attempt
is not `QUEUED`/`BLOCKED`, or hashes/geometry do not match.

**Tests.** Export contains exactly the inputs; import refuses a mismatched
geometry or missing provenance; accepted import makes the attempt `GENERATED`.

**Must NOT change.** Review semantics; nothing is uploaded automatically.

---

## T3 — Page review UX (web)

**Objective.** The creator reviews the current page, not a dashboard.

**Routes.** `apps/web/app/production/runs/[runId]/page.tsx` (run),
`apps/web/app/production/runs/[runId]/pages/[pageId]/page.tsx` (page). Link
from the project/episode view: "Start sample" (profile + chapter + proposed
placements) and, only when `canonical-readiness.ready`, "Start canonical
production". Otherwise show the readiness reasons verbatim.

**Run view.** Header: purpose badge (`NON-CANON SAMPLE` never looks like
canon), profile name/version/status, continuity version. Contact sheet: one
small tile per page (color finish of the approved or latest attempt), state
chip (WAITING, BLOCKED, READY, IN REVIEW, APPROVED, STALE) and reasons on
hover. "Refresh sources" button → `POST /production/runs/{id}/refresh`, then
list changes (kind, key, old → new). Sample decision: PASS / FAIL with notes;
PASS is disabled with the API's reason when any approved page is a test render.

**Page view.** Left: master / B&W / color toggle (same geometry, so overlay
toggling works). Right: script (directions, dialogue, constraints, intents,
lineage incl. overlay insertion), references grouped by role (CANON,
CONTINUITY, GRAMMAR with "teaches", ENVIRONMENT, gaps), dependencies, attempt
history (append-only, newest first, provenance drawer with model/workflow/
settings/seed), actions: Generate (seed optional), Reject, Regenerate, Approve
(the decision the API allows). A BLOCKED page shows the missing references and
links to the character's reference page. A WAITING page says which page must be
approved first.

**Data.** Only the M3 routes and the existing attempt image route. Poll the
attempt's job while it is queued.

**Must NOT change.** API routes; the M2 roughs screens (they remain
ADVANCED/OVERRIDE).

**Done when.** Lint/typecheck/build pass; a vitest for the state chips and
readiness gating; manual check against the API with the test backend.

---

## T4 — Environment references

**Objective.** Let the creator tag references with setting tags so
`ENVIRONMENT` retrieval has something to return.

**Decision.** Reuse `ReferenceDescriptor` values (no new table). Tags are
lowercase words (`forest`, `village`, `road`, `interior`, `night`).

**Work.** A "Setting tags" field on the reference detail screen (web) using
the existing descriptor routes; no new API unless one is missing. Bundles
already match descriptor values against `profile.setting.environment_tags`.

**Invariant.** Environment references never override the project's Spatial
Bible; the bundle keeps listing them under ENVIRONMENT with "teaches".

---

## T5 — Manga Grammar Index v1 (Priority B)

**Objective.** Persist page layout analysis so grammar retrieval is instant and
can rank across the whole library.

**Data model.** New Tier B table `manga_layout` (migration `0006`):
`id, locator (unique), series_key, unit_id FK catalog_unit, page_offset,
panel_count, largest_panel_share, negative_space, ink_density, panels JSONB,
analyzer_version, analyzed_at`. No pixels stored.

**Worker job.** `grammar.index` (durable job, resumable, bounded batch): for
each `MANGA_CHAPTER` unit not yet analyzed at the current analyzer version,
read up to 3 interior pages via `source_page_reader`, run `analyze_layout`,
insert rows. Read-only on the Vault.

**Retrieval.** `catalog_grammar_candidates` reads `manga_layout` first and
falls back to on-demand analysis. `rank_grammar` unchanged.

**Tests.** Job resumes after interruption; re-run is a no-op; analyzer version
bump re-analyzes; retrieval uses stored rows.

---

## T6 — Episode package skeleton (Priority C, minimal)

A read-only `GET /projects/{id}/episodes/{ep}/package` that lists the episode's
chapters (materialized hashes), production runs and their states, and
placeholders for `music_references`, `opening_items`, `ending_items` (empty
lists, documented). No generation, no UI beyond a link.
