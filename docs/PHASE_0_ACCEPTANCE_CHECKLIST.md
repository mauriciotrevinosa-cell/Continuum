# Continuum Phase 0 — Acceptance Checklist

Use this checklist as a human-readable complement to automated tests. Automated tests remain authoritative for technical PASS/FAIL where available.

## Foundation gate

- [ ] `docs/FOUNDATION_APPROVAL.md` is present on the target branch.
- [ ] Claude followed `docs/CLAUDE_PHASE_0_START.md`.
- [ ] Phase 0 contains no Phase 1 feature implementation.

## Local environment

- [ ] Active repo is outside OneDrive/Dropbox/Google Drive/iCloud sync.
- [ ] Python 3.12 is available through `uv`.
- [ ] Node and `pnpm` are available.
- [ ] Docker Desktop/Engine can run PostgreSQL + pgvector.
- [ ] Data roots are outside the git repository.
- [ ] `.gitattributes` LF policy landed before substantive implementation code.

## Storage / Source Vault

- [ ] `SourceVaultReader` exposes no write/delete/rename/mkdir API.
- [ ] No diagnostic/test attempts a write inside Source Vault.
- [ ] Write-capable stores cannot resolve Source Vault as a destination.
- [ ] Traversal/symlink/junction escape tests pass.
- [ ] Windows-specific path tests have an explicit result.
- [ ] Content-addressed writes are atomic and idempotent.

## Durable jobs

- [ ] PostgreSQL is the sole durable job state store.
- [ ] Worker is a standalone process.
- [ ] UI/API restart does not cancel worker work.
- [ ] Lease/heartbeat/reaper recovers hard-killed workers.
- [ ] Pause/cancel use request flags and guarded transitions.
- [ ] `CANCELLING` state exists.
- [ ] Retry backoff and final-failure semantics are tested.
- [ ] Equivalent active enqueue requests dedupe.
- [ ] Forced unit re-execution is safe and creates no duplicate effect.
- [ ] Progress/checkpoints survive browser/API/worker lifecycle as required.

## API / security

- [ ] Phase 0 binds only to `127.0.0.1`.
- [ ] Non-loopback config is rejected.
- [ ] No endpoint accepts arbitrary filesystem paths.
- [ ] CORS is restricted.
- [ ] Secrets are redacted in logs and absent from committed config/DB.

## Providers

- [ ] No real AI SDK is required or shipped in Phase 0.
- [ ] Suite passes without cloud credentials.
- [ ] `FREE_LOCAL` cannot silently select remote/paid providers.
- [ ] Missing capability/model creates actionable BLOCKED state.
- [ ] Provider calls require data classification.

## Database / contracts

- [ ] Exactly six Phase 0 application tables exist.
- [ ] Alembic has one head.
- [ ] Clean migration succeeds.
- [ ] Documented downgrade/upgrade test succeeds or is honestly reported.
- [ ] OpenAPI-generated TypeScript client has no drift.
- [ ] No premature franchise/canon/project/visual/artifact tables exist.

## Reports and audit

- [ ] Claude produced `docs/PHASE_0_REPORT.md` with commands and evidence.
- [ ] Codex followed `docs/CODEX_PHASE_0_AUDIT.md`.
- [ ] Codex produced `docs/CODEX_PHASE_0_AUDIT_REPORT.md`.
- [ ] Any Windows-only checks not available to Codex were run separately on Windows.
- [ ] Final human/ChatGPT review found no unresolved blocker.

## Final recovery point

- [ ] Only after all required gates pass: create immutable tag `continuum-phase-0`.
- [ ] Do not move the tag later; corrections after the tag get new commits/tags.
