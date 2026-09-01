# Continuum Phase 0 — Coordination / Current Gate

**Current project state:** foundation approved; Phase 0 implementation authorized; no Phase 0 implementation code should be assumed complete yet.

This file is the short operational index. It does not replace the architecture documents.

---

## Agent sequence

### 1. Claude — primary implementer

Start here:

`docs/CLAUDE_PHASE_0_START.md`

Claude implements Phase 0, runs the acceptance suite, writes `docs/PHASE_0_REPORT.md`, identifies the candidate commit SHA, and **stops**.

### 2. Codex — independent auditor

Start only after Claude has a Phase 0 candidate and report.

Start here:

`docs/CODEX_PHASE_0_AUDIT.md`

Codex re-runs/inspects independently, fixes only verified Phase 0 defects when appropriate, writes `docs/CODEX_PHASE_0_AUDIT_REPORT.md`, identifies the audited commit SHA, and **stops**.

### 3. Final human / ChatGPT review

Review:

- Claude's Phase 0 report;
- Codex's independent audit report;
- final diff/commit history;
- any Windows-only checks that could not run in the audit environment.

Only after this final gate may the immutable recovery tag `continuum-phase-0` be created.

---

## Architecture authority

Start with:

`docs/FOUNDATION_APPROVAL.md`

Then ADR-0001 through ADR-0006 and `docs/ARCHITECTURE_REVIEW.md`.

For phase numbering, Master Plan §109 is authoritative.

---

## Phase 0 is not a feature demo

A successful Phase 0 proves the foundations for later work:

- safe/read-only Source Vault boundary;
- durable background jobs;
- crash-safe resume and idempotent effects;
- worker independence from UI/API lifetime;
- PostgreSQL migrations and queue semantics;
- local/offline provider abstraction with fakes;
- safe configuration/logging;
- minimal status/jobs UI;
- reproducible acceptance tests.

It intentionally does **not** contain the Library scanner, Reader, Source Intelligence, Character Brain, Story Studio, Visual Lab, or generation engines.

---

## Local-machine prerequisites that agents must verify, not assume

- development working copy outside OneDrive/other sync folders;
- Docker Desktop available for PostgreSQL + pgvector only;
- Python 3.12 via `uv`;
- Node + `pnpm`;
- configured data roots outside the repository;
- Windows-specific path/security tests ultimately executed on Windows.

Missing future media/AI dependencies such as FFmpeg or model weights are not Phase 0 blockers.

---

## Current creative inventory note

The documentation-level franchise pool currently contains 43 franchises; the 42 original selector franchises were retained and My Dress-Up Darling was added post-selector. This is creative documentation only and must not become runtime seed data or franchise-specific Phase 0 logic.

See:

`docs/CONTINUUM_FRANCHISE_MASTER_POOL_v0.2.md`
