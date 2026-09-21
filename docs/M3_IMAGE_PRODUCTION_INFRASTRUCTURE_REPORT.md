# Image-production infrastructure pass — report

Branch: `m3/critical-path`. Started from `da3915f`
(`docs: lock manga rendering language` + the pulled story documents).
No GPU was used, no paid request was made, no money was spent, and no story
content was changed.

## 1. Commits

| Commit | What it does |
| --- | --- |
| `c8773fd` | records what the pass reuses, before any code changed |
| `42a2df6` | purpose-aware reference routing, end to end |
| `6a12dce` | locality and spend as separate policies; the hard spend cap; the paid provider; props and training tables (migration 0019) |
| `10a6586` | a second model-family graph and adapters in the ComfyUI backend |
| `42b8576` | production sheet kinds and variants (migration 0020); prop scale locks |
| `d221725` | foundation batches, cross-provider calibration, curated training manifests |
| `c57f9b4` | the pipeline documentation, the batch schema, every new setting |

## 2. Architecture decisions

1. **A reference carries what it was chosen to teach.** Routing is a pure,
   deterministic function in `continuum_core.routing`; the provider honours a
   purpose and may refuse it, never widen it. Identity is borne by exactly two
   purposes, both of which require a named cast member.
2. **Locality and spend are independent.** A production profile is now a named
   pair of two policies rather than a single ladder, so free remote compute is
   expressible without admitting anything paid.
3. **An unknown cost is not zero.** Pricing is configuration; an unpriced
   request cannot be reserved, so a provider nobody priced simply cannot be
   used for paid work.
4. **The budget is a ledger with reservations**, not a check in the UI. The
   budget row is locked before counting, so concurrency cannot overdraw.
5. **Model family means graph shape, not vendor.** The enum names the shape
   (`UNIFIED_CHECKPOINT` / `SEPARATE_ENCODERS`); vendor family names are
   aliases in config, which keeps the no-model-literals invariant honest and
   lets a new family be added by editing a table.
6. **Capability honesty over capability claims.** The split-encoder graph has
   no IP-Adapter path here, so it reports no reference conditioning and
   refuses a panel with a cast rather than drawing a stranger.
7. **A sheet is per variant.** `variant_key` makes "one approved sheet" mean
   one per outfit or per object, which is what a season actually needs.
8. **A prop's size is a measurement, not a hope.** Approving a prop produces a
   sentence that travels with every stage request; the prop's plates travel as
   recorded evidence and are never image-conditioned and never identity.
9. **A batch is a manifest**, priced and checked before anything moves, and
   started only by a person who names themselves.
10. **A training dataset is an exact hashed manifest** of material somebody
    approved for training, and style never shares a dataset with structural
    conditioning.

## 3. Migrations

* **0019** `spend_budget`, `spend_entry`, `project_prop`,
  `project_prop_reference`, `training_dataset`, `training_dataset_item`,
  `training_run`. Additive. Downgrade refuses if any of them holds rows.
* **0020** sheet kinds `MANGA_TRANSLATION`, `OUTFIT`, `ACCESSORY_SCALE`;
  `character_model_sheet_attempt.variant_key`; approved-uniqueness now
  includes the variant. Downgrade refuses if any row uses a new kind or a
  variant.

Both applied cleanly to the **test** database. The application database has
**not** been migrated in this pass — see section 9.

## 4. Tests

New: `tests/test_reference_routing.py` (13),
`tests/test_provider_policy_axes.py` (11),
`tests/acceptance/test_paid_budget.py` (9),
`tests/acceptance/test_m3_comfy_model_families.py` (8),
`tests/acceptance/test_m3_props_and_sheets.py` (10),
`tests/acceptance/test_m3_batch_benchmark_training.py` (12), plus two routing
cases added to `tests/acceptance/test_m3_layered_construction.py`.

They cover, by the directive's own list:

* **reference routing** — a style reference never becomes identity; a
  character reference never becomes a style authority; unrelated source
  material is not selected merely because it exists (and *is* selected when it
  genuinely teaches something); purposes are recorded in the recipe, the
  attempt inputs and the construction screen; the current outfit wins; a scale
  lock is carried and never image-conditioned;
* **provider policy** — free remote compute without paid; `FREE_ONLY` can
  never select a paid provider; a paid provider failing does not escalate to a
  dearer one; selection is deterministic; a source excerpt stays local
  whatever the policies say;
* **budget** — the cap holds with no overdraft; two concurrent reservations
  cannot both take the last dollar; released and settled reservations
  reconcile; prices are external; an unpriced request is refused; cost lineage
  is recorded;
* **character sheets** — the Character Pack and corpus are reused unchanged;
  attempts stay append-only; approval supersedes per kind *and variant*;
  evidence requirements are per kind;
* **calibration** — the same stage runs against different providers on equal
  terms; previous output is not overwritten; a frozen approval survives a
  comparison;
* **Kaggle/Comfy** — the existing unified-checkpoint path still works; the
  split-encoder family coexists; adapter metadata is recorded and changes the
  workflow hash.

Full gate, all green:

```
uv run ruff check .          All checks passed
uv run ruff format --check . 444 files already formatted
uv run mypy packages apps workers   no issues in 143 source files
uv run lint-imports          4 contracts kept, 0 broken
uv run pytest -q             724 passed, 1 skipped, 0 failed
pnpm lint / pnpm typecheck   clean (web types extended for purposes)
```

The one skip is the Windows/POSIX-specific path case that never runs on this
machine. The database suite ran against the live test database, including the
concurrency case for the spend cap.

## 5. Existing components reused (not rebuilt)

Character Vault and profiles; the calibration cast and Character Pack; the
character corpus (observations, authority, status, role); character production
models and their evidence; wardrobe and per-stage outfit resolution; the
Reference Vault and its facets, descriptors and standings; Visual Knowledge
retrieval; the external-resource registry; the artwork/stage provider
contracts; the ComfyUI local and remote backends and their IP-Adapter lanes;
the Kaggle bootstrap and session recovery; the calibration chapter parser and
runs; layered construction, freeze and staleness; lineage and provenance
checks; the per-reference transmission policy; deterministic manifests.

The character-sheet pipeline was **extended**, not replaced: the same
`character_model_sheet_attempt` table, the same request/review/supersede flow,
the same evidence resolution from the corpus.

## 6. Readiness

| Area | State | What is missing |
| --- | --- | --- |
| Purpose routing | **working** | tagging real references with the technique facets so retrieval has more to route |
| Policy axes | **working** | nothing |
| Budget | **working** | a price row per real provider/model; settlement from invoices is manual |
| Character sheets | **infrastructure ready** | no provider implements `CharacterSheetProvider` except the paid one, which needs credentials; so sheets are requestable only once a key is configured or a Comfy sheet path is added |
| Unified-checkpoint family | **working** | unchanged from before |
| Split-encoder family | **working for prompt-and-upstream stages** | no reference conditioning; declared, not faked |
| Adapters | **working** | no adapter exists yet to load |
| Paid provider | **integration ready** | key, endpoint, model tiers and a price row |
| Foundation batch | **working (plan + reserve)** | executing a reserved batch item is still the ordinary per-artifact flow |
| Calibration benchmark | **working** | nothing |
| Training datasets | **working** | material has to be approved for training before it can be admitted |

## 7. The $10 cap, demonstrated

`tests/acceptance/test_paid_budget.py` proves it against the real database:
nine reservations of $1 leave exactly $1; a $2 request is refused naming both
numbers; the remaining $1 still fits; two concurrent workers racing for the
last dollar end up one reserved and one refused, with the ledger at exactly
$10 and `over_committed` false; releasing returns the money; settling records
the real cost; lowering the configured cap applies immediately.

## 8. Known blockers

1. **No paid credentials configured**, deliberately. The provider is dormant
   until `CONTINUUM_GOOGLE_IMAGES_ENABLED`, a key, an endpoint and at least one
   model tier are set, *and* a price row exists, *and* the spend policy admits
   paid work. Nothing was spent and nothing can be spent without all of that.
2. **No GPU endpoint.** `CONTINUUM_COMFY_REMOTE_URL` still points at an expired
   tunnel from the previous session; a real render needs a new session URL and
   a restart of the API and worker.
3. **The application database is still at 0018.** Migrations 0019 and 0020 are
   tested but not applied to the creator's live database.
4. **Character sheets cannot render on ComfyUI yet** - no `render_character_sheet`
   implementation there. The paid provider has one.
5. **No API routes or screens** for props, budgets, batches, benchmarks or
   datasets. They are services with tests; the construction screen shows the
   new routing purposes, and nothing else is wired to the web app yet.

## 9. Exact next commands

```bash
# 1. Apply the two new migrations to the application database (back it up first).
uv run alembic upgrade head

# 2. Optional: allow the free remote GPU without allowing any paid provider.
#    (in .env)
#    CONTINUUM_LOCALITY_POLICY=REMOTE_ALLOWED
#    CONTINUUM_SPEND_POLICY=FREE_ONLY

# 3. Open a free GPU session and point Continuum at it.
python scripts/setup_comfy_free_gpu.py --preset animagine-xl-4.0
#    then set CONTINUUM_COMFY_REMOTE_URL to the printed tunnel URL and restart
#    the API and the worker.

# 4. Compare two backends on the same calibration stage (no money involved):
#    CalibrationBenchmark(construction).compare(page_id, 1, "COMPOSITION",
#        ["comfy.remote", "fake.deterministic-stage"])
```

Paid work, when and if the creator wants it, needs all of:

```bash
CONTINUUM_SPEND_POLICY=PAID_ALLOWED_WITH_CAP
CONTINUUM_GOOGLE_IMAGES_ENABLED=true
CONTINUUM_GOOGLE_API_KEY=...            # set by the creator, never by Continuum
CONTINUUM_GOOGLE_IMAGE_ENDPOINT=...
CONTINUUM_GOOGLE_IMAGE_MODEL_CHEAP=...
CONTINUUM_GOOGLE_IMAGE_MODEL_HIGH=...
CONTINUUM_IMAGE_PRICE_LIST=[...]        # a row per model, or nothing is spendable
CONTINUUM_SPEND_CAP_USD=10.0
```

and then an explicit `FoundationBatch.reserve(manifest, approved_by="...")`.
**The foundation batch was not started, and nothing in Continuum starts it.**
