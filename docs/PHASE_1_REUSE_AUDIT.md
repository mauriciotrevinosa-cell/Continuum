# Continuum — Phase 1 Reuse Audit

**Status:** RECORDED for the Phase 1 M1 + M2 audit
**Date:** 2026-09-13
**Branch:** `phase-1/integrated-candidate`
**Scope:** kickoff expansion §16 and §29 — what the Phase 1 reference vault and rough
pipeline reuse from repositories the user owns, and what they deliberately do not.

Verdicts: **REUSE DIRECTLY** (used as-is, as code or data) · **PORT / ADAPT** (logic carried
into Continuum and adapted to its boundaries) · **KEEP EXTERNAL** (stays a separate tool;
Continuum reads its outputs at most) · **REIMPLEMENT CLEANLY** (same idea, new code, because
the original's shape conflicts with a Continuum invariant) · **NOT RELEVANT**.

---

## 1. `mauriciotrevinosa-cell/continuum-acquisition` (the acquisition engine)

Ownership: same GitHub owner as Continuum; public; **no LICENSE file** (all rights reserved
by default — reuse inside the owner's own projects only, which is the case here). It is a
personal tool run outside the Continuum runtime; its reports live in the personal data
directory, never in Git.

| Component | What it does | Reusable as-is? | Adapted? | Rewritten? | Why | Resulting Continuum module |
|---|---|---|---|---|---|---|
| `acq/vault_scan.py` — recorded SHA-256 in `vault-index.json` | read-only Vault walk; per-file size, mtime and cached SHA-256 | **REUSE DIRECTLY** (as data) | — | — | the engine already hashed hundreds of GB; re-hashing to name a reference would cost hours of I/O. Trusted only while size **and** mtime still match what the engine recorded; otherwise the file is re-hashed | `continuum_storage.sources.SourceAccess._hash` |
| `acq/util.py::sha256_file` | streaming file hash | no | — | **REIMPLEMENT CLEANLY** | Continuum's hashing is pure computation in `continuum_core` fed by the storage layer's hardened reader (ADR-0001: only storage opens files) | `continuum_core.content_hash_stream` via `SourceVaultReader.open_read` |
| `acq/vault_scan.py` — archive directory metadata (image entries, chapter folders) | lists archive members without extracting | no | **PORT / ADAPT** | — | reading order and chapter grouping were ported in Phase 0 into the media viewer; Phase 1 adds content-derived **entry-name** locators on top of that listing | `continuum_storage.media` (`_image_entries`, archive listing) + `continuum_storage.sources.normalized_entry` |
| `acq/layout.py`, `acq/coverage.py`, `acq/report.py` | expected vs actual Vault topology, coverage and queue reports | no | — | — | **KEEP EXTERNAL** — report-driven analysis of the whole library; Continuum only reads the documents (Phase 0 Library screens) | read through `continuum_storage.acquisition.AcquisitionStore` |
| `acq/catalog.py`, `acq/taxonomy.py` | the personal works catalogue and relation taxonomy | no | — | — | **KEEP EXTERNAL** — the catalogue is personal data describing *works*; Phase 1 catalogues *references* (pages, regions, frames, fan art) in PostgreSQL with its own tiered schema | `continuum_library` (independent schema, no coupling) |
| `acq/discover.py`, `acq/providers/*`, `acq/adapters/bibliographic.py`, `acq/http.py` | bibliographic discovery over public APIs | no | — | — | **KEEP EXTERNAL** — network access for acquisition planning; Phase 1 never fetches anything (links in the Reference Inbox are stored, not opened) | — |
| `acq/acquire.py`, `acq/adapters/web.py`, `acq/adapters/localfolder.py`, `acq/sources.py`, `acq/updates.py` | acquisition channels, source registry, update watch | no | — | — | **KEEP EXTERNAL** — acquisition and its legal/ToS policy stay in the engine; nothing in Phase 1 acquires media | — |
| `acq/ingest.py`, `intake_import.py`, `acq/prepare.py`, `acq/scaffold.py` | dry-run-by-default intake into the Vault; folder scaffolding | no | — | — | **KEEP EXTERNAL** — these are the only code paths that may write into the Vault, and they remain user-run and dry-run by default. Phase 1 intake (the Reference Inbox) writes only under `ContinuumData/library` | — |
| duplicate detection (hash comparisons across files) | finds duplicate files in the Vault | no | — | — | **NOT RELEVANT** — Continuum stores content-addressed derived bytes, so duplicates of its own artifacts cannot occur; it never deduplicates the Vault | — |

## 2. Other repositories the user owns

Checked by repository description and top-level contents for anything materially relevant
to reference cataloguing, image handling or rough generation. None is coupled in.

| Repository (kind) | Verdict | Why |
|---|---|---|
| Atlas (personal knowledge / dashboard) | **NOT RELEVANT** | no reference, image or generation code; the kickoff forbids Atlas coupling |
| aria-core (LLM routing with cloud fallback) | **NOT RELEVANT** | its fallback-to-cloud behaviour contradicts the FREE_LOCAL policy (no path to paid or remote providers) |
| docforge, council, interview-prep | **NOT RELEVANT** | document / conversation tooling |
| lensing-sim, black_hole, montecarlo, walkforward | **NOT RELEVANT** | simulations and finance analysis |
| pixel-agents | **NOT RELEVANT** | agent visualisation; no image pipeline to reuse |

## 3. Third-party code

| Component | Verdict | Where recorded |
|---|---|---|
| Pillow (image decode, crop, preview, mask, deterministic sketch) | new dependency, pinned `>=12.3,<13`; decode allowlist and pixel budget (F-51) | `docs/DEPENDENCIES.md`, `continuum_imaging` |
| ComfyUI, Remotion, any model weights | **not installed** (kickoff: no real ComfyUI/model installation yet) | provider contract `Capability.ROUGH_RENDER` is ready for an adapter |
