# ADR-0001 — Storage layout and source-vault immutability

- **Status:** Proposed — awaiting human approval (handoff §2 gate)
- **Date:** 2026-08-28
- **Supersedes:** Master Plan §3 (repo tree), §5 (vault conventions), §61 (v0.2 storage model)
- **Authoritative over:** all filesystem access in Continuum
- **Related findings:** F-02, F-03, F-04, F-08, F-13, F-15, F-16, F-33, F-36, F-40, F-51, F-74

---

## Context

`/source-vault` immutability is the product's foundational promise (§2.1, §108, §111). The Master Plan states it as a rule but provides no enforcement mechanism, and §3's repository tree actively works against it by placing the data roots inside the git working tree.

A rule enforced only by convention will not survive years of contributions, especially with coding agents involved. An agent asked to "clean up duplicate files in the library" will find `shutil.move` and use it. The enforcement therefore has to make the wrong thing *unrepresentable* rather than merely forbidden.

The primary development machine is Windows 11 with the project currently under OneDrive — two facts that change several details (E-6, §B.2 of the review).

---

## Decision

### 1. Eight roots, defined by §108, configured as absolute paths outside the repository

| Root | Writable | Backed up | Created at boot |
|---|---|---|---|
| `source_vault` | **No** | User's responsibility (originals) | No — must already exist |
| `library` | Yes | Yes | Yes |
| `projects` | Yes | Yes (**authoritative state**, not "exports") | Yes |
| `generated` | Yes | Yes | Yes |
| `jobs` | Yes | Metadata only | Lazily |
| `models` | Yes | No (large, re-downloadable) | Lazily |
| `cache` | Yes | **No** (disposable by definition) | Yes |
| `config` | Yes | Yes (excluding secrets) | Yes |

Roots are resolved from configuration at boot. **They are not directories in the repository** (F-03). The repository contains exactly one filesystem fixture: `fixtures/demo_vault/`, wholly synthetic.

Boot validation: every required root must resolve, exist or be creatable, and be writable (except `source_vault`, which must exist and must *not* be written). Failure is a startup error with a specific message naming the root, not a stack trace.

### 2. Source-vault immutability is enforced at five layers

**Layer 1 — Type separation (primary).** `SourceVaultReader` exposes `open_read`, `stat`, `iter_entries`, `exists`. It has no write, delete, rename, or mkdir method — not a disabled one, not one that raises. `DerivedStore` has full write capability, and its root table does not contain the vault root, so it cannot resolve a path into it.

**Layer 2 — One path resolver.** All filesystem access goes through `resolve_within(root, candidate)`:

1. Reject absolute paths, NUL bytes, and control characters.
2. Normalize → **fully resolve symlinks/junctions** → check containment against the realpath'd root. Containment is checked **after** resolution; checking first is the standard bypass.
3. After opening, re-verify by comparing `st_dev`/`st_ino` on the open file descriptor against the resolved target, closing the TOCTOU window. Use `O_NOFOLLOW` on the final component where available.

Windows cases each carrying a required test: junctions/reparse points, 8.3 short names, alternate data streams, UNC and `\\?\` prefixes, case-insensitivity, reserved device names (`CON`, `NUL`, `COM1`…), trailing dots and spaces, drive-relative paths (`C:foo`). Property-based fuzzing over path inputs in addition to the enumerated cases.

**Layer 3 — Import-boundary enforcement in CI.** No module outside `packages/storage` may import `os`, `shutil`, `pathlib`, `aiofiles`, `zipfile`, or `tempfile` for filesystem work, or call bare `open()`. Enforced by `import-linter` contracts plus an AST check. Hard CI failure. This is the layer that prevents drift over years.

**Layer 4 — Derived writes are content-addressed.** All derived and generated files are written to `<root>/<sha256[0:2]>/<sha256><ext>`, with the human-meaningful name held in the database. **No user-supplied string ever reaches a write path.** Writes are: temp file in the destination directory → fsync → atomic rename.

This is a root-cause fix rather than a guard: write-side path traversal and zip-slip become structurally impossible rather than defended against, and crash-safety plus deduplication plus safe job re-runs (ADR-0002) all fall out of the same convention.

**Layer 5 — OS-level hardening, offered and verified but not required.** `scripts/harden_vault` applies a deny-write ACE (Windows `icacls`) or a read-only mount / unprivileged runtime user (POSIX). A startup probe attempts one write into the vault, reports whether the OS refused, and removes the file if it unexpectedly succeeded. The result appears on `/health` as `vault_os_readonly: true|false` — a **health signal, not a boot failure**, because many users cannot change permissions.

### 3. There is no escape hatch (F-15)

No `--force`, no "advanced: allow vault writes" setting, no admin endpoint, no environment variable. Reorganizing or deleting source media is the user's job, in their file manager. Any future request for vault-write capability is a change to this ADR, reviewed as such.

### 4. `franchise.yaml` is read-only input (F-02)

It is parsed during scan and seeds database records. Continuum never writes it. All app-managed franchise metadata lives in the database and `/library`. UI edits to franchise metadata update the database; the file is untouched. If the user edits the file, a re-scan reconciles it, surfacing conflicts rather than overwriting user edits in either direction.

### 5. Vault identity lives in config, never in the vault (F-16)

Detecting "this is not the vault this project was built against" uses a `root_key` declared in `/config` plus a non-authoritative fingerprint (hash over sorted top-level entry names and sizes), computed at boot and used only to warn. **No marker file is ever written into the vault.**

### 6. Asset identity is the content hash; paths are observations (F-08, F-74)

An asset is identified by `content_hash`. `(root_key, relative_path)` is recorded as an *observation* with a timestamp, and an asset may have several. Moving or renaming a file adds/updates an observation; it does not create an asset. Duplicating a file adds a second observation to one asset. Editing a file in place produces a new asset and marks the old one's observation stale.

A file that is absent transitions the asset to `OFFLINE` with `last_seen_at`. **It is never deleted** (F-33) — a user opening the project on a laptop without the vault attached must still browse the library, read notes, and inspect derived records. Re-attaching restores `ONLINE` by hash, not by path.

### 7. Cloud-sync folders are detected and warned about (F-13)

At boot, each configured root is checked against known sync-provider locations (OneDrive, Dropbox, Google Drive, iCloud). A match produces a prominent warning. Rationale: placeholder ("files on demand") entries `stat()` as real files but block for minutes or fail on read, and sync conflict copies (`file-PCNAME.ext`) appear to a scanner as new assets. Both failure modes are extremely hard to diagnose from their symptoms.

The database data directory and the git repository must also not live under a sync folder.

### 8. Archive handling is pre-committed now, implemented in Phase 1/2 (F-51)

Never write files using archive entry names (Layer 4 makes this structural). Reject absolute or `..`-containing entry names, symlink entries, and entries exceeding configured caps on uncompressed size, compression ratio, and entry count.

All media and archive parsing runs **in the worker process, never in the API**, with timeouts and memory caps. A parser crash is a job failure, not an application failure.

### 9. Backup and export design (§109's Phase 0 ADR deliverable) (F-36)

**Consistency ordering:** quiesce workers (drain flag, ADR-0002) → dump the database → snapshot the filesystem roots → write `backup_manifest` recording the dump id, per-root content hashes, the Alembic schema revision, and the application version.

**Restore verification** reports dangling references rather than failing on them. Because artifacts are content-addressed, a *missing* file is detectable and a *silently changed* file is impossible — most of backup integrity is delivered by the storage convention rather than by the backup tool.

**Scope:** `library`, `projects`, `generated`, `config` (minus secrets), and the database. `cache` is never backed up. `source_vault` is the user's own responsibility and is only referenced by hash. `models` are referenced by hash and download location, not copied.

**Project/Studio Export Package** (§108, future): database subset + `projects` + `generated` + a manifest naming required source assets (hash, size, human label) and required models. On import, missing dependencies become `BLOCKED` jobs and `OFFLINE` assets, never errors.

**Phase 0 builds:** this ADR, the content-hash helper, root resolution, and the atomic-write primitive. **Not** a backup product.

---

## Consequences

**Positive**

- Vault writes are unrepresentable in the type system, not merely forbidden by policy.
- Write-side traversal and zip-slip are eliminated by construction rather than defended against.
- Machine migration works: identity is content, not path.
- Crash-safety, deduplication, and idempotent job re-runs come free from one storage convention.
- The FK/import boundary rules are mechanically testable, so the guarantee survives future contributors.

**Negative / accepted costs**

- Content-addressed paths are not human-browsable. Accepted: the database holds names, and a `resolve name → path` CLI helper covers debugging.
- Two storage types means slightly more ceremony for callers. That ceremony is the point.
- The import-linter boundary costs roughly a day to set up and will occasionally be annoying. Accepted.
- Content hashing large video files is slow. Mitigated by hashing as a durable, resumable job with progress (ADR-0002), never inline in a request.

---

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Convention plus code review | Does not survive years or agent contributors; it is the current state and it is what this ADR replaces. |
| A single `Storage` class with a `readonly` flag | One wrong boolean, and the guarantee is gone. Flags are not boundaries. |
| OS-level read-only as the *primary* mechanism | Cannot be required of every user or environment; excellent as defense in depth (Layer 5). |
| Marker file for vault identity | It is a vault write. Rejected on the invariant it was meant to protect. |
| Path-based asset identity | Breaks on every file move, rename, and machine migration — all of which are normal user behavior. |
| Keeping data roots in the repo with `.gitignore` | One `git clean -xdf` destroys the user's source library. `.gitignore` is a backstop, never a mechanism. |

---

## Verification

Acceptance tests §110.3, §110.4, §110.5, §110.14; review §S and §S.1. Specifically:

- `SourceVaultReader` write-method absence asserted by introspection.
- `DerivedStore` rejects any vault-resolving root.
- Traversal/symlink/junction/ADS/8.3/UNC/device-name/TOCTOU cases, each an individual test.
- `import-linter` contract proving no filesystem I/O outside `packages/storage`.
- Sync-folder detection warning test.
- OS read-only probe surfaced on `/health`.
