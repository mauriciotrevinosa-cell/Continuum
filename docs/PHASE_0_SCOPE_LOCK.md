# Continuum Phase 0 — Scope Lock

This file is intentionally short and exists to prevent agent scope drift.

## Allowed in Phase 0

Foundation only: monorepo/tooling, FastAPI health/jobs API, minimal Next.js status/jobs UI, PostgreSQL + pgvector extension, six durable job/worker tables, standalone worker, synthetic handlers, storage safety boundary, fake provider contracts/policy, config/logging/redaction, migrations, CI/tests, and required docs.

## Not allowed in Phase 0

No Reader, scanner, real media ingestion, SourceAsset/SourceSegment domain model, canon extraction, RAG/embeddings, Character Brain, Story Studio, projects/branches, Story Calendar, relationship engine, city/faction/civilization engine, Visual Lab, real AI providers, model downloads, image/TTS/video generation, desktop wrapper, auth/network sharing, or franchise-specific runtime logic.

## Rule

If a proposed change is useful only because a later phase might need it, do not add it unless ADR-0006 or `docs/FOUNDATION_APPROVAL.md` explicitly requires the field/boundary now to avoid an expensive migration.

The next feature phase begins only after the `continuum-phase-0` recovery tag has passed Claude implementation, Codex audit, and final human/ChatGPT review.
