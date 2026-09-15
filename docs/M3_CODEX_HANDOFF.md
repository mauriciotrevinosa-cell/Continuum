# M3 — Codex delegation package

Read `docs/M3_MANGA_PRODUCTION.md` first. The production semantics (runs,
pages, continuity, review, invalidation, promotion), the character reference
corpus, the ComfyUI backend and the web production loop are **done and
tested**. The tasks below plug into them; none may change them.

Global rules for every task:

* Public repository: no personal library titles, handles or media in code,
  tests, docs or commit text. Tests use invented names only.
* The Source Vault is read-only. Nothing is written into it; nothing from it is
  uploaded. Remote backends receive only a page bundle, and never third-party
  source excerpts unless the creator explicitly allowed them.
* No paid API or service. A backend that costs money is out of scope.
* No client-supplied filesystem paths (F-50). Address records by id.
* `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy packages apps workers`, `uv run lint-imports` and
  `uv run pytest` must pass. Web: `pnpm --dir apps/web lint`, `typecheck`,
  `test`, `build`.

## Done in-house (not for delegation)

* **T1 ComfyUI backend** - `packages/providers/src/continuum_providers/comfy.py`,
  settings `comfy_*`, diagnostics `GET /production/backends`, tests
  `tests/acceptance/test_m3_comfy_backend.py` (fake ComfyUI server).
* **T3 Page review UX** - `/projects/{id}/manga/production`,
  `/production/runs/{run}`, `/production/runs/{run}/pages/{page}`.
* **T4 Environment tags (minimum)** - "Use as environment" on corpus
  observations (`POST /library/character-observations/{id}/environment`),
  LOCATION descriptors matched per page from its script.
* **Character reference corpus** - see `docs/M3_MANGA_PRODUCTION.md` §9.

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

## T5 — Manga Grammar Index v1 (Priority B)

**Objective.** Persist page layout analysis so grammar retrieval is instant and
can rank across the whole library.

**Data model.** New Tier B table `manga_layout` (next migration):
`id, locator (unique), series_key, unit_key (catalog units are rebuilt by rescans; no foreign key), page_offset,
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

---

## T7 — Corpus review at scale (after the first real sample)

The corpus sweep finds hundreds of candidate source pages per franchise
character; confirming them is manual. Candidates to automate later, each only
producing *hints* a person confirms: panel crops from `analyze_layout` panels
(store as regions on observations), face/figure detection with a locally
installed, license-checked detector, and relative-scale pairs from shared
locators. Never auto-confirm; never let a hint count toward readiness.
