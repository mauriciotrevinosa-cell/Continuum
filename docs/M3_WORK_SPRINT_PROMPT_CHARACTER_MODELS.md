# M3 Work sprint prompt — Character Production Models before real artwork

Use this document as the execution prompt for the next Work session.

---

You are continuing **Continuum M3** on branch `m3/critical-path` in `C:\Continuum`.

## Mission

Before real manga artwork, implement the **Character Production Model** workflow so The Arrivals has a stable project-specific visual base for its early cast. Do not spend the sprint re-auditing already-proven production mechanics or exploring unrelated features.

The creator has a limited Work budget. Execute in the priority order below. **After every completed stable phase: run the relevant tests, commit, push to `origin/m3/critical-path`, and update the handoff before continuing.** If the session stops, times out or runs out of credits, completed work must already be on Git.

## Start state / required reading

First:

```powershell
cd C:\Continuum
git status
git fetch origin
git checkout m3/critical-path
git pull --ff-only
git submodule update --init --recursive
```

Do not discard creator/local changes if the working tree is dirty. Inspect and preserve them.

Read, in this order:

1. `AGENTS.md`
2. `docs/M3_CHARACTER_PRODUCTION_MODEL_SPEC.md`
3. `docs/M3_CHARACTER_INTAKE_REFERENCE_DISCOVERY_SPEC.md`
4. `docs/M3_WARDROBE_AND_LORA_STRATEGY.md`
5. `docs/M3_FRIEREN_REFERENCE_REVIEW.md`
6. `docs/M3_AICOMICBUILDER_ADOPTION_NOTES.md`
7. `docs/M3_MANGA_PRODUCTION.md`
8. `docs/M3_WORK_HANDOFF.md`
9. `docs/M3_CODEX_VISUAL_QA.md`

Pinned external reference:

- `tools/AIComicBuilder-upstream`
- upstream commit is pinned by submodule
- **read-only upstream**: do not develop inside the submodule and do not advance its pin during this sprint unless absolutely required and explicitly justified

## Existing truths — do not rediscover or undo

- Normal Manga Production technical loop works.
- Automatic page cast works.
- Full-page references are role-separated.
- TEST renderer/job status/review/unlock mechanics work.
- TEST pages are not artwork and cannot establish art continuity.
- Candidate observations must never condition identity in ComfyUI.
- Grammar/technique recent-page diversity was already implemented.
- Existing sample run contains TEST-approved pages 1–2; it is not the real-art continuity run.
- No real GPU endpoint is configured yet.
- No SAMPLE PASS or canonical run exists.
- Mau Anime V2 is stylization only; its clothing was rejected.
- Frieren has known bad identity associations documented in `M3_FRIEREN_REFERENCE_REVIEW.md`.

## Global implementation rules

1. Reuse existing `CharacterProfile`, `CharacterOutfit`, Reference Vault, `CharacterObservation`, project standing, job/provider/storage and review architecture. Do not create a parallel character library.
2. Keep identity / wardrobe / acting / style / technique separate.
3. Generated model sheets start as project-created candidates; they never self-approve.
4. Preserve all source provenance and content-addressed storage rules.
5. Do not build perfect visual character recognition in this sprint.
6. Do not scrape/download a huge web dataset.
7. Do not train a LoRA in this sprint.
8. Do not import AIComicBuilder wholesale.
9. Do not generate a chapter of real artwork.
10. Any DB migration requires a backup first, following the existing M3 handoff procedure.
11. Keep migrations minimal and forward-only; add acceptance tests for new invariants.
12. Prefer root fixes over compatibility patches.

# CHECKPOINT W0 — preflight only

Confirm branch/head, submodule, DB migration state and targeted test baseline. Do not spend significant time manually touring UI that was already audited.

If a new migration is needed later, take the documented `pg_dump -Fc` backup before applying it.

No commit is needed for W0 unless you must fix a genuine pre-existing blocker.

# CHECKPOINT W1 — Production Model foundation — HIGHEST PRIORITY

Implement the project-scoped, versioned Production Model described in `M3_CHARACTER_PRODUCTION_MODEL_SPEC.md`.

Minimum functional scope:

- one character can have multiple project Production Model versions
- status lifecycle at least draft/review/approved/superseded or semantically equivalent
- preferred evidence is typed/grouped, not an undifferentiated image pile
- active/current Production Model can be resolved for a character in a project
- active outfit remains separate
- generated sheet refs can be attached but cannot self-approve
- approval/supersession preserves history
- existing character corpus remains valid and backwards compatible
- expose API needed by the web UI
- Character Overview visibly shows Production Model status/version/evidence

Bundle behavior:

- approved Production Model evidence is preferred before general corpus evidence
- page-specific confirmed evidence may supplement it
- existing candidate safety remains intact
- grammar/technique/environment can never become identity through this feature

Tests must cover:

- versioning/supersession
- human-approval gating
- candidate safety
- bundle priority
- identity/wardrobe separation

### End W1

Run relevant tests/lint/typecheck for touched surfaces.

Then:

```powershell
git add -A
git commit -m "feat(m3): add project character production models"
git push origin m3/critical-path
```

Update `docs/M3_WORK_HANDOFF.md` with exact result/commit and any migration.

**Do not continue until W1 is committed and pushed.**

# CHECKPOINT W2 — Character intake: Family -> Character -> Snapshot

Improve the current new-character flow according to `M3_CHARACTER_INTAKE_REFERENCE_DISCOVERY_SPEC.md`.

Required:

- searchable/scrollable Family/Series selector
- family-scoped character autocomplete
- selecting an existing character reuses it rather than duplicating it
- Custom / Original escape hatch remains
- optional project snapshot/version metadata without turning this into a lore database
- roster data must be maintainable without hard-coding each character into UI source

Look for an existing roster/character-selection artifact before inventing a second source. If there is no usable existing roster in the repo/data, introduce the smallest clean structure and document how it is populated.

First acceptance families/characters only need to prove the generic UI with real data relevant to The Arrivals; do not spend the sprint creating exhaustive franchise rosters.

### End W2

Relevant tests + web checks, then:

```powershell
git add -A
git commit -m "feat(m3): add roster-driven character intake"
git push origin m3/critical-path
```

Update handoff. Stop safely here if time is already tight.

# CHECKPOINT W3 — Seed refs, Find More, review, Add to character

Implement the human-steered evidence loop.

Required:

- select a handful of existing refs/observations as seeds; no fixed `5 images` rule
- `Find more references` searches already-held/catalogued material first
- candidates grouped by missing/useful facet
- accept/confirm, reject association, atypical, anchor (when allowed), facet/angle/framing metadata
- preserve authority and visual-origin separation
- rejecting a character association does not delete the underlying source/reference
- `Add to character` action from relevant reference/corpus browsing UI
- choose character + role/use + optional outfit
- style/technique cannot become identity evidence

Do not claim image recognition if the implementation is metadata/hint based. Candidate uncertainty must be visible.

Tests must cover the invariants above.

### End W3

Tests/checks, then:

```powershell
git add -A
git commit -m "feat(m3): add character seed and reference review flow"
git push origin m3/critical-path
```

Update handoff.

# CHECKPOINT W4 — Character Model Builder

This is the highest-value stretch goal after W1–W3.

Study `tools/AIComicBuilder-upstream`, especially its character turnaround generation, but implement the feature inside Continuum using Continuum's provider/job/storage/provenance boundaries.

Required product behavior:

- build from **approved/confirmed reference pack + character rules**, not name/text alone
- standardized HEAD candidate: front / 3-4 / profile / back-hair
- standardized FULL BODY candidate: front / 3-4 / side / back
- generated result is `PROJECT_CREATED` candidate/review material
- model-sheet attempt records backend/model/workflow/settings/provenance similar to other generated artifacts
- creator can inspect, reject/regenerate, or approve into a new Production Model version
- if no real capable backend is configured, the UI must truthfully report the gap rather than fabricate artwork

Important: the existing Comfy adapter may be reused/extended if appropriate, but do not break manga page generation. A provider-neutral model-builder job is preferred over burying generation logic in a React component.

If AIComicBuilder source code is actually adapted/copied, preserve Apache-2.0 obligations and record source file/upstream commit in comments/docs. Do not edit the submodule.

### End W4

Tests/checks, then:

```powershell
git add -A
git commit -m "feat(m3): add reference-grounded character model builder"
git push origin m3/critical-path
```

Update handoff with what is real vs still backend-blocked.

## TARGET STOP FOR A ~5-HOUR SESSION

A strong session ends with **W1–W4 solid and pushed**. Do not sacrifice architecture/tests to claim more characters/features.

Everything below is lower priority. Continue only if W1–W4 are stable and time remains.

# CHECKPOINT W5 — Exercise first batch

Use the generic flow for:

1. Mau
2. Frieren
3. Fern
4. Stark

Priority if time is limited: **Mau + Frieren first**, Fern next, Stark last.

Do not impersonate creator approvals.

For Frieren, surface the exact known reject/confirm actions from `M3_FRIEREN_REFERENCE_REVIEW.md`; creator review can remain pending.

For Mau, preserve creator-primary identity, V2 stylization-only status, rejected V2 clothing and E1 no-glasses rule.

This checkpoint may be data/setup/UI verification rather than a large code feature.

Commit/push any durable project setup or fixtures only if they belong in Git under existing project-data rules. Do not commit private creator photos or copyrighted source pixels.

# CHECKPOINT W6 — Wardrobe v1

Implement the minimum timeline-aware/project wardrobe behavior from `M3_WARDROBE_AND_LORA_STRATEGY.md`.

Required:

- current outfit can be selected separately from identity
- early/default/secondary/casual variants can coexist
- project-created outfit can have preferred refs/model sheet and review state
- later outfit does not rewrite earlier continuity
- system can eventually represent a garment owned by one character but worn by another without cloning identity

Do not design the entire S1 wardrobe.

Commit + push with a dedicated commit and update handoff.

# CHECKPOINT W7 — clean real-art sample setup from Page 1

Only after the character foundation is ready enough:

- create or expose the ability to create a **fresh NON_CANON_SAMPLE from Page 1** for actual artwork continuity
- keep it clearly separate from the existing workflow-test/sample history
- do not approve/generate artwork just to make the run look complete
- existing TEST pages must never enter its art continuity

If this is already possible without code changes, document the exact creator action instead of adding redundant code.

Commit/push only if code/data schema actually changed.

# CHECKPOINT W8 — Production Model -> Comfy bundle wiring, only if time remains

Make sure Comfy/page bundle consumes:

1. approved Production Model identity refs
2. current wardrobe refs
3. page-specific confirmed refs
4. real approved continuity
5. grammar/technique/environment in non-identity roles

No real GPU endpoint needs to be connected in this sprint. Diagnostics must remain truthful.

Commit/push if changes are needed.

# Explicitly deferred

Do NOT spend the sprint on:

- LoRA training
- whole-chapter real rendering
- video/Seedance/Kling/Veo
- importing all AIComicBuilder functionality
- persistent grammar index
- general UI polish unrelated to this workflow
- a giant franchise roster
- perfect character recognition
- canonical E1 production
- SAMPLE PASS

# Handoff requirement at session end

Before stopping for any reason, ensure all stable work is pushed. Update `docs/M3_WORK_HANDOFF.md` with:

- resulting HEAD
- checkpoints completed / partial / not started
- migrations and backup path if any
- tests/checks actually run and exact results
- UI routes to inspect
- creator actions still required
- backend/GPU truth
- blockers
- exact next highest-value action

Never say a generated model is approved unless the creator actually approved it. Never promote TEST or model-builder candidate images to canonical artwork.

---

## Creator success condition after this sprint

The creator should be able to open a character and understand, at a glance:

- who the character is in source/project terms
- which evidence defines identity
- what the current The Arrivals Production Model is
- what outfit is active
- what evidence is missing
- how to add/confirm/reject refs
- how to build a standardized model-sheet candidate
- that nothing generated becomes official without their approval

Once Mau/Frieren (then Fern/Stark) are grounded through this workflow, the next phase is GPU/Comfy connection and a **fresh real-art NON_CANON sample from Page 1**, reviewed page by page.