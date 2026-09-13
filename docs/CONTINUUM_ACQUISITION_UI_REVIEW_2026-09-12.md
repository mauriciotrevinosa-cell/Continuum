# Continuum — Acquisition UI/API Review — 2026-09-12

**Status:** Active review note  
**Reviewed implementation:** `phase-0/integrated-candidate` at `3471eef535771e4fc8e423bde91e05e49230f8c7`  
**Review-fix branch:** `review/acquisition-post-claude`  
**Scope:** Library Acquisition API/UI integration added after the Phase 0 final-candidate work.

---

## 1. What the implementation added

The reviewed commit adds a substantial Library Acquisition surface without hardcoding Mauricio's current franchise pool into runtime data.

Main additions:

- FastAPI `/library/acquisition` routes;
- acquisition overview, source families, family detail, queue, sources, intake, update watch, calendar, scaffold plan, and status;
- `AcquisitionStore` for reading acquisition-engine JSON documents;
- configurable acquisition data directory and CLI path;
- source-registry UI with add/test/enable/disable/remove controls;
- per-work search links into registered sources;
- chapter coverage and gap presentation;
- release/update calendar;
- empty-Library behavior rather than seeded franchise data;
- acceptance tests using invented fixtures;
- separation of Library acquisition from Project membership.

The overall direction is correct: the external acquisition engine owns acquisition/catalog rules; Continuum consumes its published documents instead of duplicating those rules in the web application.

---

## 2. Confirmed defects found during review

### 2.1 Refresh action could never run

The API route `/library/acquisition/refresh` calls the CLI verb:

```text
coverage
```

but `AcquisitionStore.ALLOWED_CLI` did not include `coverage`.

Result before the fix:

```text
Refresh UI -> API -> AcquisitionStore.build_command("coverage")
           -> AcquisitionCliError
```

So the main "re-read the Vault and rebuild the reports" action was structurally blocked by its own allowlist even though the route exposed it.

**Fix prepared on `review/acquisition-post-claude`:** add read-only `coverage` to the allowlist while continuing to reject `--apply`.

A regression test was added to ensure:

- `coverage` remains callable;
- `coverage --apply` remains rejected.

### 2.2 Missing CLI configuration could produce a bogus manual command

`run()` correctly rejected an unconfigured CLI, but the route then called `build_command()` in an attempt to show a manual command. `build_command()` did not reject a missing CLI path, so it could construct a command containing the literal string:

```text
None
```

as the script path.

**Fix prepared on `review/acquisition-post-claude`:** `build_command()` now rejects an absent CLI path rather than rendering a fake command.

A regression test covers this case.

### 2.3 Registered search templates were rendered as links without scheme validation

Source search templates are registry data. The first implementation rendered the resulting string directly as an `<a href>`.

Even in a local-first app, stored source metadata should not be able to create arbitrary navigation schemes.

**Fix prepared on `review/acquisition-post-claude`:** only valid `http:` and `https:` search templates become clickable links. Malformed or non-web schemes remain inert.

---

## 3. Integration items to verify locally before merging

### 3.1 Actual local acquisition paths

Mauricio's current acquisition state is under:

```text
C:\ContinuumData\acquisition
```

and the local CLI is expected under:

```text
C:\ContinuumTools\acquisition\acquisition_orchestrator.py
```

The implementation is correctly configurable and must remain project-agnostic, but the local `.env` needs to resolve the real current paths, e.g.:

```text
CONTINUUM_ACQUISITION_DATA_DIR=C:/ContinuumData/acquisition
CONTINUUM_ACQUISITION_CLI=C:/ContinuumTools/acquisition/acquisition_orchestrator.py
```

Do not hardcode these personal paths into runtime defaults or seed data.

### 3.2 Run the real CLI contract, not only the fake CLI

The commit reports 73 passing tests, but GitHub currently exposes no CI status/workflow run for commit `3471eef...`.

Before integration, run locally against the real orchestrator and confirm that the verbs expected by the UI match the actual CLI:

```text
coverage
sources add/list/remove/test/enable/disable
scaffold --no-rescan
ingest
```

The fake-CLI tests prove the web/API boundary; they do not prove that the external local CLI currently exposes identical command names and argument shapes.

### 3.3 Verify refresh after real document rewrites

After a successful CLI refresh, verify that the mtime cache observes rewritten documents and that all screens show the new state without restarting API/Web.

### 3.4 Verify real empty, partial, and large-Library states

Test at least:

- no acquisition directory;
- acquisition directory with only some documents;
- malformed/half-written JSON;
- current Mauricio Library;
- a synthetic larger Library than the current one.

This protects the product from accidentally optimizing only for the present personal dataset.

---

## 4. Architecture concern to resolve before calling the surface final

### Local-folder source registration vs F-50

The Foundation rule F-50 says the unauthenticated Phase 0 API is loopback-only and takes no raw filesystem-path parameters.

The new Add Source UI currently advertises:

```text
Website URL or folder you own
```

and can send a local folder string through `AddSourceRequest.url` with the `local-folder` adapter.

That is semantically a raw filesystem path arriving from the browser even though the field is named `url`.

Do not paper over the contradiction. Before final integration choose one explicit design:

1. keep browser registration URL-only and register local-folder sources through trusted local configuration/CLI; or
2. introduce an approved-root / opaque-handle mechanism so the browser never supplies arbitrary filesystem paths.

Until that decision is made, do not broaden local-folder access further.

---

## 5. UI/product direction

The current Acquisition screens are a useful operational Library surface, but they should remain a component of the Creative Studio rather than becoming Continuum's overall visual identity.

Keep the useful information architecture:

- family completeness;
- material relationship type;
- queue;
- source registry;
- intake/conflicts;
- update watch;
- release calendar;
- provenance/freshness.

Future polish should reduce the feeling of a developer/admin dashboard and move toward a media-library/studio experience while preserving diagnostics under secondary detail surfaces.

Avoid hardcoding current franchises, current source counts, or The Arrivals assumptions into this UI.

---

## 6. Performance/maintainability notes

The implementation already makes a good choice by caching parsed acquisition documents by mtime. Additional optimizations should be measurement-driven rather than premature.

Candidates after profiling:

- use stable `family_id` directly from queue documents when available instead of reconstructing it from family title;
- narrow screen revalidation after source-only actions instead of invalidating every Acquisition route when unnecessary;
- move expensive cross-document projections into the acquisition engine if JSON projection becomes a measurable API bottleneck;
- keep the API projection stable even as the external acquisition documents evolve.

Do not duplicate acquisition rules in TypeScript/FastAPI for speed. The external engine remains the source of truth.

---

## 7. Merge gate

Before merging the reviewed Acquisition implementation into the final candidate/master line:

- apply or cherry-pick the review fixes;
- run Python tests, lint, typecheck, import-linter;
- run Web lint/typecheck/build;
- exercise the real local acquisition CLI;
- verify the local `.env` points to the current acquisition data/CLI;
- resolve or explicitly defer the F-50 local-folder contradiction;
- verify no browser action can pass `--apply` or write raw Source Vault media;
- verify no current personal franchise list is used as runtime seed data.

The implementation is promising, but commit `3471eef...` should not be treated as final merely because its fake-CLI acceptance suite passes.
