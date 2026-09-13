# Continuum

A local-first, private **Source Vault + living multiverse story studio**.

Continuum ingests source material you already own, builds a structured universe
library from it, and helps create canon-aware continuations — without ever
modifying your source files, without requiring a cloud account, and without
losing work when a machine crashes.

> **Current state: Phase 0 (foundation) — not feature-complete, not tagged.**
> There is no library, reader, canon engine, story generator or image
> generation yet. Phase 0 exists to make the *invariants* real: an immutable
> Source Vault, durable crash-safe jobs, replaceable local providers, and a
> minimal API/UI over them. See [`docs/PHASE_0_REPORT.md`](docs/PHASE_0_REPORT.md)
> for exactly what has and has not been verified.

---

## Requirements

| | Version | Notes |
|---|---|---|
| **Python** | **3.12** | Pinned (D-04). Not 3.13/3.14: the Phase 3+ ML stack lags new CPython by 6–18 months. |
| **uv** | ≥ 0.5 | Manages the Python workspace. |
| **Node** | ≥ 20 | |
| **pnpm** | 9.15.4 | `npm install -g pnpm@9.15.4` |
| **Docker Desktop** | any current | **PostgreSQL + pgvector only** (D-03). App processes run natively. |

FFmpeg and any AI model are **not** required and **not** used in Phase 0.

---

## Setup

```bash
uv sync --python 3.12
```

```bash
pnpm install
```

```bash
cp .env.example .env
```

Then edit `.env` and set at minimum `CONTINUUM_DATA_HOME`.

### Where your data lives

The eight storage roots live **outside this repository** (D-01) and outside any
cloud-sync folder (OQ-2). `git clean -xdf` must never be able to delete your
source library, and OneDrive/Dropbox must never be able to present a
placeholder file that `stat()`s as real but blocks on read.

```text
source-vault/   YOUR media. READ-ONLY to Continuum. Never written, ever.
library/        derived source intelligence
projects/       authoritative project state
generated/      generated artifacts and exports
jobs/           optional human-readable job manifests
models/         optional local model assets
cache/          disposable
config/         non-secret config and profiles
```

Only `source_vault` is read-only, and it is absent from the writable-root table
by construction — a write into it is not blocked, it is unreachable.

---

## Running the stack

Three processes, deliberately separate. **The worker is a service, never a
child of the API or the web server** — that is what makes "closing the UI does
not cancel work" structurally true rather than a promise.

```bash
docker compose up -d db
```

```bash
uv run alembic upgrade head
```

Then, in three separate terminals:

```bash
uv run continuum-api
```

```bash
uv run continuum-worker
```

```bash
pnpm dev:web
```

Or, on Windows, all of it at once:

```bash
pwsh scripts/dev.ps1
```

| Service | Address |
|---|---|
| Web | http://127.0.0.1:3000 |
| API health | http://127.0.0.1:8000/health |
| API readiness | http://127.0.0.1:8000/ready |
| PostgreSQL | `127.0.0.1:5433` |

**If port 8000 is already in use** (it is on the primary dev machine), set
`CONTINUUM_API_PORT=8010` and `CONTINUUM_API_BASE=http://127.0.0.1:8010`. The
web app reads the API address at request time, so no rebuild is needed.

The API binds to **`127.0.0.1` only**. Phase 0 has no authentication, so a
non-loopback bind is rejected by configuration validation, and there is
deliberately no dormant "bind to LAN if auth exists" path (A-03).

---

## Try the durable job system

This is the point of Phase 0. Enqueue a synthetic job:

```bash
curl -X POST http://127.0.0.1:8000/jobs -H "content-type: application/json" -d "{\"job_type\":\"synthetic.counted_work\",\"payload\":{\"units\":20,\"unit_delay_ms\":500}}"
```

Watch it at http://127.0.0.1:3000/jobs, then try these:

- **Close the browser.** Progress keeps advancing — it lives in the database.
- **Stop the API** (Ctrl+C). The worker keeps going; it has no channel to the API.
- **Kill the worker** (`taskkill /F`). Within one lease period another worker
  reclaims the job and resumes **only the unfinished units**. Completed units
  are not redone, and re-running one would be a byte-identical no-op anyway.
- **Drain it gracefully** instead: `POST /workers/{id}/drain`. The worker
  finishes its current unit, persists, and returns the job to the queue.

Prove the blocked path, which must never silently reach for paid compute:

```bash
curl -X POST http://127.0.0.1:8000/jobs -H "content-type: application/json" -d "{\"job_type\":\"synthetic.blocked_capability\"}"
```

It parks as `BLOCKED(MISSING_PROVIDER)` with an actionable remediation payload.

---

## Testing

```bash
uv run pytest -q
```

Without a database, the durable-job suite **skips** and says so, naming the
command that fixes it. Skips are never counted as passes.

Full gate set, exactly as CI runs it:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy packages apps workers && uv run lint-imports && uv run pytest -q
```

```bash
pnpm lint && pnpm typecheck && pnpm build:web
```

Two environment notes that change results:

- **Symlink tests** need Windows Developer Mode (Settings → System → For
  developers). Without it, 5 tests skip; the Linux CI leg covers them. The
  *junction* escape test — the Windows vector needing no privilege — always runs.
- **Database tests** need `docker compose up -d db`.

---

## Repository layout

```text
apps/api        FastAPI: health, jobs, workers
apps/web        Next.js: status, jobs list, job detail
packages/core   domain primitives; no I/O, no framework
packages/config typed settings and boot validation
packages/observability   JSON logging, correlation ids, secret redaction
packages/storage         THE ONLY module permitted filesystem access
packages/db     SQLAlchemy models + Alembic migrations
packages/jobs   state machine, queue, leases, checkpoints, execution
packages/providers       contracts, policy, deterministic fakes
workers/runner  the standalone worker process
fixtures/demo_vault      synthetic test vault; no real franchise content
tests/          acceptance (§110) and invariant suites
```

---

## Documentation

| Read this | For |
|---|---|
| [`docs/FOUNDATION_APPROVAL.md`](docs/FOUNDATION_APPROVAL.md) | **Highest authority** for Phase 0 amendments |
| [`docs/ADR/`](docs/ADR/) | The six accepted architecture decisions |
| [`docs/ARCHITECTURE_REVIEW.md`](docs/ARCHITECTURE_REVIEW.md) | 74 findings and their rationale |
| [`docs/PHASE_0_REPORT.md`](docs/PHASE_0_REPORT.md) | What is actually verified, and what is not |
| [`AGENTS.md`](AGENTS.md) | Rules for anyone (human or agent) writing code here |
| [`PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md`](PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md) | The product specification |

Phase numbering follows Master Plan **§109 only**. Older numbering in §43 and
§86 is historical and must not be used in code, commits, tags or issues.

---

## What Continuum will not do

- Modify, delete or rename anything under `source-vault` — there is no override,
  no force flag, and no admin mode.
- Download, scrape or circumvent DRM on any source material.
- Require a cloud account or a paid API for core use.
- Silently switch to a paid or remote provider.
- Send verbatim source excerpts to a remote provider.
- Canonize a major story decision without explicit approval.
