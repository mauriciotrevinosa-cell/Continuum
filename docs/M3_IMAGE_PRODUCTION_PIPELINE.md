# Image production: routing, policy, cost and comparison

How a panel becomes pixels, who decides what, and what Continuum refuses to do
on its own. Written after the infrastructure pass that added purpose-aware
reference routing, independent provider policies, a hard spend cap, a paid
provider, a second model family, production sheet variants, prop scale locks,
foundation batches, cross-provider calibration and curated training manifests.

## 1. The pipeline

```
STORY / CALIBRATION SPEC
  -> materialized page, panel contract (beat, shot, cast, anchors, forbidden)
  -> character state: production model, wardrobe at this story stage, props
  -> PURPOSE-AWARE REFERENCE RESOLVER
       retrieval offers -> routing assigns a purpose to each reference
       -> what each may influence, what was refused and why
  -> RENDER PACKET (references + purposes + scale locks + seed + contract)
  -> PROVIDER ROUTING (capability: can it draw this stage at all?)
  -> POLICY GATE      (locality: may it leave this machine?
                       spend:    may it cost money?)
  -> COST GATE        (estimate known? does it fit what is left? reserve it)
  -> TRANSMISSION GATE (per reference: may this image be sent there?)
  -> RENDER
  -> LINEAGE (model, family, adapters, workflow, settings, seed, conditioning,
              what was transmitted, what was withheld, what was refused)
  -> CREATOR REVIEW
  -> APPROVED / REJECTED / SUPERSEDED
```

Each arrow is a refusal point. Nothing degrades silently: a stage that cannot
be drawn correctly is blocked with the exact gap and a way forward.

## 2. Purpose-aware reference routing

**The change.** Retrieval used to answer "which references are about this
panel?". It now answers "what does the renderer need this reference to
teach?", and the answer travels with the reference.

Every reference enters a packet with a `ReferencePurpose`
(`continuum_core.routing`), and the purpose carries a rule:

| Property | Meaning |
| --- | --- |
| `influences` | IDENTITY / WARDROBE / LAYOUT / TREATMENT / DETAIL - what it may change |
| `character_scoped` | belongs to one named cast member |
| `identity_bearing` | may define who that person is (only IDENTITY and BODY) |
| `image_conditioned` | may be handed to the renderer as an image at all |
| `roles`, `facets` | which bundle roles and technique facets can carry it |

`STAGE_NEEDS` says what each construction stage asks for, in priority order,
with a budget. The composition stage asks for environment, architecture,
composition and depth; the line stage asks for line language; neither asks for
the other's material. A character-scoped budget is per cast member, so nobody
is crowded out.

Ranking inside a purpose, in order: does anything recorded about it actually
teach this; is it the current outfit; the project's standing
(`PREFERRED_FOR_CURRENT_LOOK` first); the corpus authority; confirmed over
candidate; quality; retrieval order; id. Fully deterministic.

**Hard rules.** A reference serves one purpose per packet. Character evidence
is never routed to a non-character purpose. An unconfirmed candidate never
grounds identity. Material from an unrelated source world is refused unless
something recorded about it matches this panel - availability is not relevance.
A purpose that is not `image_conditioned` (a scale lock, a palette note) is
carried as a recorded fact and never uploaded.

At render time the backend *honours* the purpose; it may refuse one but never
widen it. The identity lane takes only identity-bearing purposes, one adapter
per character, never blended. The scene lane takes the rest, with the stage
deciding what it may shape (composition → layout; later stages → treatment).

Recorded in `rough_attempt.artwork_provenance` and the stage recipe:
`routing.selected` (id, purpose, influences, why), `routing.rejected` (id,
reason), `references_transmitted`, `references_withheld`, `conditioning`.

## 3. Free versus paid, local versus remote

These are **two axes**, because conflating them is how a $0 product spends
money by accident:

* `LocalityPolicy`: `LOCAL_ONLY` | `REMOTE_ALLOWED` - may work leave this
  machine? A GPU session the creator opened in a notebook is remote and free.
* `SpendPolicy`: `FREE_ONLY` | `METERED_ALLOWED` | `PAID_ALLOWED_WITH_CAP` -
  may work cost money? A cheap API is nobody's local machine.

A `ProductionProfile` is a named pair of the two (`PROFILE_POLICIES`). Either
may be overridden alone:

```bash
CONTINUUM_LOCALITY_POLICY=REMOTE_ALLOWED   # use the free notebook GPU
CONTINUUM_SPEND_POLICY=FREE_ONLY           # and still never bill a card
```

Resolution picks exactly one provider and never falls back: a paid provider
failing does not hand the work to a dearer one. A refusal names which axis is
in the way (`blocked_by: ["spend"]`) so the fix is one explicit decision.

Independently of both, a verbatim source excerpt never goes to a remote
provider unless the creator allowed it, and each reference is checked
individually (`transmission_refusal`) so one forbidden image withholds itself
instead of blocking the whole stage.

## 4. The paid budget

A cap that is only shown in the interface is decoration. The cap here is a
ledger:

* `CONTINUUM_SPEND_CAP_USD` (default **10.00**) is the hard limit for the
  scope in `CONTINUUM_SPEND_SCOPE`;
* before any paid request, `SpendLedger.reserve` locks the budget row
  (`SELECT ... FOR UPDATE`), sums reservations *plus* settled costs, and
  refuses if the estimate does not fit. Two requests racing for the last
  dollar cannot both win;
* a reservation is **settled** with the real cost or **released**. Reserved
  money is spent money until one of those happens;
* an **unpriced** request is refused. An unknown cost is not zero;
* money is integer micro-dollars. No floating-point cents.

Prices are configuration, never code:

```bash
CONTINUUM_IMAGE_PRICE_LIST='[{"provider_id":"google.image","model_ref":"<model>",
  "per_image_micros":39000,"up_to_pixels":1048576,"batch_per_image_micros":19500}]'
```

Each row may bracket by size and give a separate batch price. A provider and
model with no row simply cannot be used for paid work until somebody says what
it costs.

## 5. Providers

| Provider | Locality | Cost | Draws | Conditions references |
| --- | --- | --- | --- | --- |
| `fake.deterministic-*` | local | free | diagrams (never artwork) | no |
| `comfy.local` | local | free | pages, panel stages | yes (SDXL family) |
| `comfy.remote` | remote | free | pages, panel stages | yes (SDXL family) |
| `google.image` | remote | **paid** | images, sheets, panel stages | yes (attached) |

The paid provider is registered only when `CONTINUUM_GOOGLE_IMAGES_ENABLED` is
true *and* a key, endpoint and at least one model are configured. Registering
it does not permit it: the spend policy decides that separately. Two model
tiers are configurable - a cheap one for exploration and comparison, a better
one for the few artifacts everything else is built on - and which tier a
request uses is recorded with the result. It refuses any request carrying a
verbatim source excerpt.

Model identifiers live only in the provider registry and configuration
(`tests/invariants/test_no_model_literals.py`).

## 6. Model families and adapters

`comfy.*` builds a different graph per family, selected by configuration:

```bash
CONTINUUM_COMFY_MODEL_FAMILY=SDXL      # checkpoint -> encode -> sample
CONTINUUM_COMFY_MODEL_FAMILY=FLUX      # unet + dual text encoders + vae + guidance
CONTINUUM_COMFY_CLIP_NAMES='clip_l.safetensors;t5xxl_fp8_e4m3fn.safetensors'
CONTINUUM_COMFY_VAE_NAME=ae.safetensors
```

Neither family is "the good one". They are routed by what a task needs, and
the backend is honest about the difference: the IP-Adapter identity and scene
lanes are an SDXL-family path, so a FLUX backend reports **no** reference
conditioning and refuses a panel with a cast rather than drawing a stranger.
Environment-only stages are exactly where the two are worth comparing today.

Adapters are configuration too:

```bash
CONTINUUM_COMFY_LORAS='[{"name":"house-style.safetensors","strength_model":0.7,
  "strength_clip":0.6,"version":"1","sha256":"...","license":"...","source":"..."}]'
```

They are chained onto the base model once; the sampler and every conditioning
lane read the adapted model. Name, strengths, version, hash, licence and
source are recorded with every image and folded into the workflow hash - a
render with an adapter is not the same render without it.

`scripts/setup_comfy_free_gpu.py --preset animagine-xl-4.0 | flux-1-schnell`
prepares either family in a notebook session.

## 7. Character sheets

The existing Character Pack, corpus, production models and wardrobe are
unchanged and reused. What the sheet pipeline gained:

| Kind | Establishes | Variant |
| --- | --- | --- |
| `HEAD` | face, hair, head shape, marks; front / 3-4 / profile / back hair | - |
| `FULL_BODY` | proportions, scale, posture, silhouette | - |
| `MANGA_TRANSLATION` | the same character in the project's own B&W language | - |
| `OUTFIT` | one garment set they actually wear at a story stage | outfit |
| `ACCESSORY_SCALE` | one recurring object beside its wearer | prop |

Each attempt carries a `variant_key`, so "one approved sheet" means one per
outfit or per object. Evidence requirements are per kind (`SHEET_EVIDENCE`): a
head sheet needs confirmed identity evidence, an outfit sheet needs the
garment, a prop sheet needs the object. Attempts stay append-only; approving
one supersedes the previous approval of the same kind *and variant*.

Outfits are added when they become persistent story state, not speculatively.

## 8. Props and scale locks

A prop (`project_prop`) is any recurring object a project wants to stay the
same: what it is, roughly how big it is, what its size reads against (a head,
a hand, a doorway), which references show it and from what view, and - only
when the story gives it one - what it means.

Approving a prop turns its measurements into a **scale lock**: one sentence
(`"<name>: about across 4 cm, 0.25x the wearer's head width"`) that travels in
`execution.backend_settings.scale_locks` on every stage of a panel where its
owner appears, and is recorded in the render's settings. The prop's own plates
travel in the packet as `ACCESSORY_SCALE`: recorded evidence, never an image
to copy, never identity. A draft measurement travels nowhere, and changing an
approved measurement returns the prop to draft.

The mechanism is generic: a prop is a row, and no object, character or project
is named in the engine.

## 9. Foundation batches

`docs/schemas/foundation-batch.v1.schema.json`. A batch is a manifest of
reusable anchors - character sheets, outfits, prop scales, calibration reruns,
interaction and ensemble tests, manga-language stress tests. A finished page
is deliberately not a batch item.

* `FoundationBatch.plan(manifest)` prices every item, reports the total and
  whether it fits, and **spends nothing**. An unpriced item blocks the batch;
  it does not cost nothing.
* `FoundationBatch.reserve(manifest, approved_by=...)` holds the money. It
  requires a person to name themselves and holds every item or none.
* Nothing in Continuum calls `reserve` for you.

## 10. Cross-provider calibration

`CalibrationBenchmark.compare(page, panel, stage, [provider ids])` draws the
same stage with each backend on equal terms: same panel contract, same routed
packet, same seed, one attempt each. `results()` puts them side by side with
each one's model, family, adapters, workflow, settings, seed, conditioning and
structure drift.

It never reviews and never overwrites. An approved environment master
(CAL-01/02/03, the approved second-floor set) is replaced only by a creator
approving something else; a comparison adds evidence to the panel's history.

## 11. Training datasets

`training_dataset` / `training_dataset_item` / `training_run`.

* An item is admitted only if a person already approved that material for
  training (`TrainingEligibility.APPROVED`, or a registered external resource
  whose allowed uses include `TRAINING_APPROVED`). An import never grants it.
* **Style and structural conditioning never share a dataset.** A `STYLE`
  dataset teaches line language, spot blacks, screentone, environment detail,
  atmosphere, action energy, panel hierarchy, composition. Pose, lineart,
  scribble, segmentation, depth and edges belong to a `STRUCTURE` dataset.
  A tag outside the kind's set is refused by name.
* Purpose tags, not franchise names. The engine works from tags; the project
  supplies them.
* `lock(dataset, reviewer)` derives the split from a seed, counts the items
  and hashes the manifest. A locked manifest never changes; a second version
  is a second row.
* A `TrainingRun` plans against a locked manifest only, hashes its config, and
  refuses to record an output that could not be reproduced (name, sha256,
  licence, where it was trained).

Nothing trains here. Running a job is a separate, deliberate act.

## 12. What stays creator-reviewed

* every artwork candidate: no automatic approval, ever;
* freezing a construction stage, and therefore what later stages build on;
* which outfit is persistent story state;
* prop measurements (approving one is what makes it a lock);
* admitting material to a training dataset, and locking the dataset;
* enabling remote compute, enabling paid providers, raising the cap, and
  starting a paid batch;
* the final story and pacing audit. Page and panel counts stay adjustable
  until then; story quality overrides page quotas.

## 13. Intentionally deferred

* colour production. Black-and-white first; colour is derived later from
  approved drawings and approved palettes. `COLOR_REFERENCE` is carried as a
  recorded fact today, not conditioned.
* reference conditioning for the FLUX family (no IP-Adapter path here yet);
  declared as unavailable rather than faked.
* running a training job, and any adapter trained from these manifests.
* automatic settlement of paid spend from provider invoices: costs are settled
  explicitly, with the estimate as the default.
* the second-season cast and anything not needed for Season 1.
