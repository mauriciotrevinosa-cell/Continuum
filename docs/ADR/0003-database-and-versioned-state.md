# ADR-0003 — Database, tier boundaries, and versioned state

- **Status:** Proposed — awaiting human approval (handoff §2 gate)
- **Date:** 2026-08-28
- **Implements:** Master Plan §2.2, §9–§12, §35, §69–§76, §106, §108
- **Related findings:** F-08, F-12, F-17, F-18, F-19, F-20, F-21, F-35, F-47, F-49, F-61, F-68, F-72, F-73, F-74

---

## Context

The Master Plan's most important product promise — "canon and generated continuity are separate" (§2.2), "new source canon never silently overwrites our story" (§89) — is stated repeatedly and never expressed as a schema rule. Left to review discipline, it will be violated: the first feature that learns from a project's own chapters will write project fiction into rows that canon retrieval reads, and unwinding that requires provenance archaeology.

The plan also conflates several notions of time and defines `SourceCanonSnapshot` in a way that has two incompatible readings. Both cost a full-schema migration if guessed wrong.

Phase 0 creates **six job/worker tables and nothing else** (ADR-0006). This ADR fixes the rules those later tables must obey, because the rules are cheap now and expensive later.

---

## Decision

### 1. Platform and toolchain

| Choice | Decision | Rationale |
|---|---|---|
| Database | **PostgreSQL 16+** with the `pgvector` extension installed by the first migration | §4; extension installed in Phase 0 to prove the image, **no vector column exists yet** |
| ORM | **SQLAlchemy 2.0 ORM**, with **separate Pydantic v2** schemas for API contracts | Not SQLModel: it fuses persistence with API contracts, and the database schema is the longest-lived asset in this product. It must not be shaped by API convenience. (D-06) |
| Migrations | **Alembic**, single head enforced in CI | A multi-head merge discovered at runtime is a very bad day |
| Primary keys | **UUIDv7** | Time-ordered (index locality), globally unique — required for §108 export/import and for merging data from two machines without sequence collisions (D-07) |
| Timestamps | `timestamptz`, UTC, **database clock** for all scheduling and lease logic | Clock skew must not affect correctness (D-09) |

### 2. Four tiers, one direction — the invariant that keeps canon separate from project state

| Tier | Contents | Mutability |
|---|---|---|
| **A — Observed source** | `SourceAsset`, `SourceSegment`, path observations | Append-only; never edited by the app; keyed by content hash |
| **B — Interpretation of source** | `CanonClaim`, source `Character`/`CharacterVersion`, `Event`, `Relationship`, `SourceBrain`, `CraftPrinciple` — each carrying provenance, confidence, and status | Versioned and correctable; corrections create revisions; history is never destroyed |
| **C — Project continuity** | `Project`, `Branch`, `ProjectCharacterState`, `StoryCalendarEvent`, world/institution/faction state, `VisualIdentity`, `VisualDesign`, `OutfitAssignment`, Change Graph edges | Mutable via events and deltas; branchable |
| **D — Generated artifacts** | `Artifact`, `ArtifactVersion`, `GenerationRecipe`, lineage edges | Reproducible from recipe (ADR-0005) |

**The invariant: foreign keys point only downward — D → C → B → A. Never upward.**

This is enforced by a CI test that reflects the SQLAlchemy metadata, classifies each table by tier from a declared registry, and asserts no FK violates the ordering. One test enforces §2.2 more reliably than any amount of review.

Corollaries:

- **Tier C never writes Tier B.** A canon sync (§71–§74) is not an edit to canon. It is: a new Tier B snapshot appears, and a Tier C *adoption decision record* describes what the project does about it. This is §89 expressed as a schema rule.
- **Tier B never references "current."** Everything is snapshot-scoped.
- Tier A is written only by ingestion, and only ever appended to.

### 3. `SourceCanonSnapshot` separates material from interpretation (F-18)

```
SourceCanonSnapshot = (material_cutoff_descriptor, asset_set_hash,
                       extraction_run_id, extractor_version)
```

Re-running extraction with a better model at the same story cutoff produces a **new snapshot**, because the claims changed even though the material did not. A project **pins a snapshot id**; moving to a newer snapshot is an explicit, diffable, user-approved action that reuses the canon-delta machinery of §71–§74.

Without this split, either re-extraction silently mutates what a project believes it branched from, or extraction can never be improved without orphaning projects.

### 4. Character Brain is two entities in two tiers (F-17)

- **`SourceBrain`** (Tier B) — snapshot-scoped; every behavior rule carries evidence links to Tier A locators plus a confidence.
- **`ProjectBrainOverlay`** (Tier C) — branch-scoped; references a `SourceBrain` revision as its base; holds divergence and project-earned growth.

The brain a writer prompt consumes is **composed at read time** from `SourceBrain@snapshot + overlay@branch at project_time`. It is never a merged stored row. §70's example (source character vs project character) then falls out of the schema instead of needing special handling, and §94's own closing paragraph is honoured structurally.

### 5. Four time axes, never sharing a column (F-68)

Every temporal field is explicitly typed as exactly one of:

| Axis | Meaning | Primary consumers |
|---|---|---|
| `source_time` | In-universe time within source canon | Canon claim validity, character versions |
| `project_time` | In-universe time within a project branch | Story Calendar, travel feasibility, relationship pacing (§97) |
| `narrative_order` | Position in the telling (chapter/episode/scene sequence) | Reveal ordering, foreshadowing, spoiler boundary (§20, §21, §82) |
| `record_time` | Real-world time the system learned or recorded something | Snapshots, audit, job telemetry, backup consistency |

`narrative_order` is the one most likely to be forgotten and the one the continuity validator needs most: "was this revealed to the audience before it was used?" is a `narrative_order` question a chronological timeline cannot answer.

**In-universe time must tolerate imprecision.** "Some weeks later", "before the war", and "at some point during the academy years" are normal source statements. A bare timestamp forces implementers to invent fake precision. In-universe temporal fields use an interval-with-uncertainty representation: `earliest`, `latest`, `precision`, `label`.

### 6. Branching is delta-only, with one owner (F-12)

§35's "a branch references a parent state and stores only its changes; never duplicate entire universes" is accepted. Its cost is that every read of project state becomes a resolve-through-ancestry operation.

**Decision:** state resolution is a single, centrally-owned, heavily-tested function — `resolve_state(branch_id, at_project_time)` — with a materialization cache keyed by `(branch, time, schema_version)`. No feature re-implements ancestry walking. Branch archive/restore (§104) and selective merge (§35) are built on that one function.

### 7. The Change Graph is a derived index (F-19)

It is rebuildable from facts that exist elsewhere (a chapter references a character state; a scene references an event). It must be droppable and fully reconstructible by a job.

This yields a strong invariant test — `rebuild_change_graph()` is a no-op on a healthy database — and removes a class of silent corruption in which a bug in edge-writing loses continuity relationships undetectably.

### 8. Deletion never destroys interpretation (F-20)

§62 says removing an item removes derived records, not originals. The dangerous cases it leaves open are resolved as:

| Removed | Behavior |
|---|---|
| Source asset | **Soft-delete.** Pure caches cascade. Reader progress and user notes survive independently. |
| Tier B claims whose only provenance was that asset | **Never deleted.** Marked `provenance_status = MISSING_SOURCE`: still visible and inspectable, down-ranked in retrieval, ineligible for promotion to locked canon. |
| Generated artifacts referencing it | Marked `STALE` (ADR-0005), never deleted. |

A naive `ON DELETE CASCADE` would silently destroy user-corrected knowledge — the worst data-loss bug this product could have.

### 9. Corrections key on locator and claim identity, not extraction run (F-49)

A user correction is a first-class Tier B record keyed by `(claim_identity, locator)`. It carries higher precedence than any extraction output, survives re-extraction, and is re-applied automatically to a new snapshot with a conflict report where the underlying claim materially changed.

If corrections were attached to an extraction-run row, the next re-extraction would orphan them — silently discarding the user's review work, which is the most demoralizing possible failure in a review-loop product.

### 10. Provenance is a typed union (F-72)

```
Provenance = SourceLocator                                  (read from source)
           | Inference(from_claim_ids[], method, model_ref) (derived from other claims)
           | UserAssertion(user, timestamp, rationale)      (user-defined)
           | Generated(recipe_id)                           (produced by generation)
```

§2.3's four categories are only meaningful if each has a representable provenance. Otherwise "show me why you believe this" (§93.3, §55) dead-ends on the first inferred claim — which will be most of the interesting ones.

### 11. Embeddings are model-versioned rows, not a column (F-47)

```
segment_embedding(segment_id, embedding_model_ref, dim, vector, created_at)
```

A column on `SourceSegment` would make switching or upgrading an embedding model a destructive migration, would break search until the whole corpus is re-embedded, and would prevent A/B comparison or coexisting text and image embeddings. With rows, re-embedding is a normal durable job. (Phase 3; no vector column in Phase 0.)

### 12. Optimistic concurrency on mutable project state (F-21)

Every mutable Tier C row carries `row_version`, checked on update. Two browser tabs, or a user editing while a worker writes a post-chapter state delta, otherwise silently last-write-wins.

### 13. "Locked" is disambiguated (F-73)

Four distinct guarantees get four distinct names: `design_status = LOCKED` (do not regenerate), `claim.user_locked` (do not contradict), `approval_required` (do not change without approval), `story_anchor` (protect this outcome through ripple adaptation). Collapsing them means the continuity validator and the ripple engine disagree about what a lock means at exactly the moment it matters.

### 14. Entity proliferation is resisted (F-61)

§106 lists 30+ concepts and asks for a cut. Most world-state concepts collapse into one pattern:

```
WorldEntity(id, kind, ...)                       -- settlement, institution, faction, infrastructure
WorldEntityState(entity_id, valid_from, valid_to, payload JSONB)
```

`EpisodeFocusTag` and `EpisodeImportance` are tags, not tables. A concept earns a table when it needs its own foreign keys, its own indexes, or its own constraints — not merely because it has a name in the spec.

### 15. Migration policy (F-35, §110.14)

- Alembic, **single head enforced in CI**.
- Every migration reviewed for destructiveness; column drops are two-phase (deprecate, drop in a later release).
- **Downgrade is best-effort and explicitly not a data-preservation guarantee.** The supported recovery path is restore-from-backup (ADR-0001 §9). Stating this plainly is better than implying reversibility the migrations do not have.
- CI tests: clean database → `upgrade head`; and `upgrade head` → `downgrade base` → `upgrade head`; and exactly one head.

---

## Consequences

**Positive**

- §2.2 and §89 become mechanically enforced rather than aspirational.
- Re-extraction, re-embedding, and correction all become normal operations instead of migrations.
- User corrections are structurally protected from being silently discarded.
- Machine migration and export/import work because identity is content- and UUID-based.
- Later schema growth is bounded by an explicit "when does a concept earn a table" rule.

**Negative / accepted costs**

- Read-time composition (brains, branch state) is slower than a denormalized row. Mitigated by the materialization cache, and correctness here is worth more than read latency.
- The four time axes make temporal code more verbose. That verbosity is the point.
- Snapshot pinning means users must explicitly adopt improved extraction. This is the desired behavior (§74), not a cost.

---

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| One `CharacterBrain` table with `project_id NULL` | The first "learn from our own chapters" feature corrupts canon with project fiction, unrecoverably. |
| SQLModel | Fuses persistence and API contract; the schema is too long-lived to be shaped by API convenience. |
| `bigserial` primary keys | Sequence collisions on export/import/merge across machines (§108). |
| One timeline column with a "kind" discriminator | Every query must remember to filter it; the one that forgets produces a subtly wrong continuity answer. |
| Snapshot = story cutoff only | Re-extraction silently changes what a project branched from. |
| `ON DELETE CASCADE` from assets to claims | Silently destroys user-corrected knowledge. |
| Embedding column on the segment | Model upgrade becomes a destructive migration with search downtime. |
| Full-copy branching | Explicitly forbidden by §11; storage and divergence-tracking both become unmanageable. |

---

## Verification

- `test_fk_tier_direction.py` — reflect metadata, assert no FK from Tier A/B to Tier C/D. **The single highest-value structural test in the project.**
- `test_110_14_migrations.py` — clean migrate, round-trip downgrade/upgrade, single head.
- From Phase 3 onward: `rebuild_change_graph()` is a no-op on a healthy database; a correction survives re-extraction; a snapshot pin is not silently advanced.
- Phase 0 applies §1, §2 (registry + test scaffold), §15 only. No Tier A–D tables exist yet.
