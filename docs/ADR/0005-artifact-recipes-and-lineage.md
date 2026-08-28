# ADR-0005 — Source locators, artifact recipes, and lineage

- **Status:** Proposed — awaiting human approval (handoff §2 gate)
- **Date:** 2026-08-28
- **Implements:** Master Plan §2.3, §2.7, §92, §93.3, §106
- **Related findings:** F-39, F-40, F-41, F-42, F-46, F-72
- **Cross-references:** ADR-0001 (content-addressed storage), ADR-0003 (provenance union, tiers)

---

## Context

Two addressing schemes determine whether Continuum's central promises survive contact with a large library:

1. **Source locators** — how a claim, a citation, a bookmark, or a Send-to-Project reference addresses a passage in source material. §9 gives `SourceSegment` a single unspecified `locator` field.
2. **Generation recipes** — how a produced artifact records what created it, so it can be compared, selectively re-rendered, migrated to a new provider, or remastered years later. §92 lists the fields but does not separate the two kinds of information it contains.

Both are decided here and implemented later (locators in Phase 1/2, recipes in Phase 10+). They are in this ADR because both are *addressing and lineage* problems, and because both are extremely expensive to change once data exists.

---

## Decision

### 1. Source locators are derived from content, never from row identity (F-46)

```
<medium>:sha256:<asset_content_hash>#<unit-address>
```

Examples:

```
cbz:sha256:ab12…#page=12
epub:sha256:cd34…#para=417
pdf:sha256:ef56…#page=88&span=1204-1319
video:sha256:0a1b…#t=00:12:03.400-00:12:07.100
sub:sha256:2c3d…#line=88
txt:sha256:4e5f…#char=8120-8344
```

Required properties:

| Property | Why |
|---|---|
| **Deterministic** — same bytes produce the same locator | Re-ingest after a scanner improvement, a database restore, or a machine move must not change any stored citation |
| **Database-independent** — resolvable given only the file | Provenance must be inspectable and portable, not an internal join |
| **Human-inspectable** | §93.3 requires the user to see *why* Continuum believes a fact |
| **Coarse-to-fine** | A page locator stays valid when panel-level locators are added later; addresses nest rather than replace |
| **Range-capable** | Claims cite spans, not points |

**This is the load-bearing primitive of the entire provenance layer.** If a locator were derived from a database row id, then re-ingesting the same file would silently repoint every stored citation — a quiet, catastrophic failure that would not be noticed until the corpus was large and the damage was unwindable.

Locator generation is owned by one module per medium, with round-trip tests (`parse(render(x)) == x`) and stability tests (re-ingest the same fixture, assert identical locators).

**Open sub-decision, deferred to the Phase 2 EPUB spike:** whether EPUB uses `#cfi=` (EPUB CFI, standard, epub.js-native, brittle across reflow implementations) or `#para=` (our own deterministic paragraph index, stable but non-standard). The spike decides; the *shape* above accommodates either.

### 2. Provenance is a typed union, not a locator field

Restated from ADR-0003 §10 because it belongs to this addressing scheme:

```
Provenance = SourceLocator
           | Inference(from_claim_ids[], method, model_ref)
           | UserAssertion(user, timestamp, rationale)
           | Generated(recipe_id)
```

An inferred claim's provenance is not a locator — it is the set of claims it came from plus the method. A user-defined claim has no locator at all. Without the union, "show me why you believe this" dead-ends on the first inferred claim, which will be most of the interesting ones (F-72).

### 3. A recipe has two parts with two hashes (F-39)

§92 says the system must distinguish creative decisions from render implementation, then lists both in one flat field set. Flat, the distinction is unenforceable and "selective rerender" degenerates into "regenerate everything whose recipe hash changed".

```
GenerationRecipe:
    intent:      { story/episode/scene/shot ids, approved script revision,
                   character-state snapshot ids, outfit/design variant ids,
                   reference asset ids, timing, approved performance direction,
                   approval state }
    execution:   { provider id, model ref + version, adapters/LoRAs, seed(s),
                   sampler and settings, prompt-template package version,
                   input artifact ids, generation settings, post-processing chain }
    intent_hash, execution_hash
    recipe_schema_version, template_package_version
```

Then:

- **"Is this shot still creatively valid?"** compares `intent_hash` only.
- **"Does this need re-rendering?"** compares `execution_hash`.
- **A remaster is a new `execution` over an unchanged `intent`** — §92's core requirement, obtained for free.
- **Provider migration** rewrites `execution` and leaves every approved creative decision intact.

Without the split, both of these are bespoke logic written under pressure years from now.

### 4. Artifacts are content-addressed (F-40)

`/generated/<sha256[0:2]>/<sha256><ext>`, with identity, human name, and version held in the database (ADR-0001 §4). Writes are temp → fsync → atomic rename.

One convention delivers deduplication, atomic and crash-safe writes, corruption detection, safe job re-runs (ADR-0002 §2), and backup integrity (ADR-0001 §9). Retrofitting content addressing after thousands of artifacts exist means rewriting every path in the database.

`ArtifactVersion` is the unit of identity for lineage; `Artifact` is the stable name the user sees across versions.

### 5. Lineage marks stale; it never deletes or auto-regenerates (F-41)

Lineage edges: `(artifact_version_id, derived_from_id, role)`.

When an upstream input changes, descendants are marked **`STALE`** and surfaced for review. They are:

- **never deleted** — the user may still want the previous render, and §35's version control depends on it;
- **never automatically regenerated** — §2.4 keeps the human in control, and §101 forbids spending expensive compute while an upstream cheap decision is unapproved.

Staleness propagation reuses the Change Graph (ADR-0003 §7), which is itself a rebuildable derived index.

### 6. Recipes are schema-versioned (F-42)

`recipe_schema_version` and `template_package_version` on every recipe. A recipe written today must remain **readable** in several years even if it is no longer **runnable**. Reinterpreting an old recipe under new field semantics would silently change what a stored creative decision meant — which is the one thing an archive of creative decisions must never do.

Old recipe versions are read through explicit upgraders; they are never re-parsed under the current schema.

### 7. Phase 0 scope

Phase 0 builds **only**:

- the SHA-256 content-hash helper (`packages/core/hashing.py`);
- `/generated` root resolution and the atomic-write primitive (ADR-0001);
- this ADR.

**No** artifact tables, no recipe tables, no lineage edges, no locator implementation. The synthetic job handler's marker files exercise the content-addressed write path and nothing more.

---

## Consequences

**Positive**

- Provenance survives re-ingestion, restore, and machine migration.
- Selective rerender, provider migration, and remastering are consequences of the intent/execution split rather than features to be designed later.
- Deduplication, crash-safety, and backup integrity come from one storage convention.
- Approved creative decisions are protected from silent reinterpretation.

**Negative / accepted costs**

- Content-addressed artifact paths are not human-browsable; the database holds names and a CLI helper resolves them.
- The intent/execution split requires discipline from handler authors deciding which side a field belongs on. The rule of thumb: *if changing it would change what the audience experiences, it is intent; if it only changes how the pixels were produced, it is execution.*
- Locators must be designed per medium, which is real work in Phases 1–4. It is much less work than repairing a corpus of broken citations.

---

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Locator = database segment id | Re-ingest silently repoints every citation. The failure is quiet, total, and discovered late. |
| Locator = file path + offset | Breaks on every file move and machine migration; ADR-0001 already makes path an observation, not identity. |
| One flat recipe hash | Any execution-level change invalidates creative approvals; remastering becomes indistinguishable from re-deciding. |
| Auto-regenerate stale descendants | Violates §2.4 and §101; can burn hours of local GPU time on work the user did not ask for. |
| Delete superseded artifacts to save disk | Destroys comparison and rollback, which are the point of §35. Disk is cheaper than a lost render. |
| Defer the locator decision to Phase 3 | Phases 1 and 2 would create segments and bookmarks first, and would have to invent a locator anyway — just without a decision record. |

---

## Verification

Phase 0: the content-hash helper and atomic-write primitive are exercised by the synthetic job handler, including the forced-re-run byte-identity assertion (ADR-0002, §110.10).

Phase 1–2, when locators are implemented:

- round-trip: `parse(render(locator)) == locator` for every medium;
- stability: re-ingesting an identical fixture produces byte-identical locators;
- coarse-to-fine: adding a finer address level does not invalidate a coarser locator;
- database-independence: a locator resolves to the correct passage given only the file.

Phase 10+, when recipes are implemented: an `execution`-only change marks descendants stale without invalidating `intent` approvals; an `intent` change does invalidate them.
