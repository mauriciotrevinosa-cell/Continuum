# Phase 0 Agent Handoff — Read Me First

This file exists so a coding agent landing in the repository can find the correct starting point quickly.

## Claude

If you are Claude acting as the primary implementer, read:

`docs/CLAUDE_PHASE_0_START.md`

Do not begin Phase 1. Stop after the Phase 0 candidate, tests, and `docs/PHASE_0_REPORT.md`.

## Codex

If you are Codex acting as the independent auditor, do **not** start until Claude has produced a Phase 0 candidate and report. Then read:

`docs/CODEX_PHASE_0_AUDIT.md`

Audit independently, fix only verified Phase 0 defects, write `docs/CODEX_PHASE_0_AUDIT_REPORT.md`, and stop.

## Architecture approval

Both agents must treat:

`docs/FOUNDATION_APPROVAL.md`

as the highest-authority document for its explicit Phase 0 amendments, followed by ADR-0001 through ADR-0006 and the architecture review.

Operational status is summarized in:

`docs/PHASE_0_COORDINATION.md`
