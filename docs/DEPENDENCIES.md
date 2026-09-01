# Dependencies

Every third-party dependency Continuum uses at Phase 0, why it is here, and its
licence. Per the permanent dependency rule in
`CONTINUUM_GITHUB_REPO_SHORTLIST.md`: verify licence and activity, pin a
version, wrap it behind an adapter, add a smoke/contract test, record it here.

**Verified:** 2026-09-01, against the resolved `uv.lock` and `pnpm-lock.yaml`.

---

## 1. The headline fact

**Phase 0 ships no AI SDK and downloads no model.** Not OpenAI, Anthropic,
Google, Cohere, Mistral, torch, transformers, faster-whisper, ctranslate2,
llama-cpp or ollama. Not one.

That is deliberate (D-12), and it is what makes acceptance test **§110.12**
("providers work with a no-op/local fake; no paid/cloud credentials are
required") verifiable *from this file* rather than by auditing code paths.

`tests/acceptance/test_110_12_providers.py::TestNoAiSdkIsInstalled` asserts each
of those eleven modules is absent from the environment. If someone adds one, the
suite fails.

The same applies to media tooling: **FFmpeg is not required, not invoked, and
not a Phase 0 dependency.** It arrives in Phase 2/4.

---

## 2. Python runtime dependencies

Python **3.12.10** (pinned, D-04 — the Phase 3+ ML stack lags new CPython
releases by 6–18 months, so 3.13/3.14 would force a downgrade later).

| Package | Version | Licence | Why |
|---|---|---|---|
| `fastapi` | 0.141.1 | MIT | The API application |
| `starlette` | 1.6.0 | BSD-3-Clause | FastAPI's ASGI foundation (transitive) |
| `uvicorn[standard]` | 0.52.4 | BSD-3-Clause | ASGI server |
| `pydantic` | 2.13.5 | MIT | API schemas, separate from ORM models (D-06) |
| `pydantic-settings` | 2.15.0 | MIT | Typed settings + `SecretStr` |
| `sqlalchemy` | 2.0.52 | MIT | ORM. Chosen over SQLModel: the database schema is the longest-lived asset here and must not be shaped by API convenience |
| `alembic` | 1.19.1 | MIT | Migrations, single head enforced |
| `mako` | 1.4.1 | MIT | Alembic's template engine (transitive) |
| `psycopg[binary]` | 3.3.5 | LGPL-3.0 | PostgreSQL driver |
| `greenlet` | 3.5.5 | MIT | SQLAlchemy async support (transitive) |

### A note on `psycopg` and the LGPL

`psycopg` 3 is LGPL-3.0. Continuum imports it as a library in a Python
application distributed as source, so the LGPL's relinking requirement is
satisfied trivially — a user can replace the installed `psycopg` at any time.
No source obligation attaches to Continuum's own code.

**This must be revisited if Continuum is ever shipped as a frozen binary** (a
PyInstaller bundle, or an Electron/Tauri desktop package with a bundled
interpreter), because static bundling changes the analysis. Recorded here so
that decision is not made accidentally.

---

## 3. Python development dependencies

| Package | Version | Licence | Why |
|---|---|---|---|
| `pytest` | 9.1.1 | MIT | Test runner |
| `pytest-timeout` | 2.4.0 | MIT | No test may hang CI indefinitely |
| `hypothesis` | 6.167.1 | MPL-2.0 | Property-based fuzzing of path inputs — 400 generated cases per run against `resolve_within` |
| `httpx` | 0.28.1 | BSD-3-Clause | `TestClient` transport |
| `ruff` | 0.16.5 | MIT | Lint + format |
| `mypy` | 2.3.1 | MIT | Strict type checking |
| `import-linter` | 2.14 | BSD-2-Clause | **Enforces ADR-0001 Layer 3** — the filesystem boundary and package layering |
| `grimp` | 3.16 | BSD-2-Clause | import-linter's graph builder (transitive) |
| `types-psycopg2` | 2.9.21 | Apache-2.0 | Type stubs |

MPL-2.0 (`hypothesis`) is file-level copyleft and a development dependency
only — it is never distributed with Continuum and no Continuum file derives
from it.

---

## 4. Node dependencies

| Package | Version | Licence | Why |
|---|---|---|---|
| `next` | 15.1.6 | MIT | Web framework |
| `react` / `react-dom` | 19.0.0 | MIT | UI |
| `typescript` | 5.7.3 | Apache-2.0 | Strict mode |
| `eslint` | **8.57.1** | MIT | See the pin note below |
| `eslint-config-next` | 15.1.6 | MIT | Next's lint rules |
| `openapi-typescript` | 7.5.2 | MIT | Generates the typed API client from OpenAPI (D-10); CI fails on drift |
| `vitest` | 3.0.4 | MIT | Declared for frontend tests; none written yet in Phase 0 |
| `@types/*` | — | MIT | Type definitions |

### Why ESLint is pinned to 8.57.1

`eslint-config-next` 15 patches ESLint's internals through `@rushstack/eslint-patch`,
which fails on ESLint 9 with *"Failed to patch ESLint because the calling module
was not recognized"*. Lint then silently produces nothing, which is worse than
failing. 8.57.1 is the combination Next actually supports. Revisit when
`eslint-config-next` ships genuine flat-config support.

---

## 5. External services and images

| Item | Version | Licence | Notes |
|---|---|---|---|
| `pgvector/pgvector` | `pg16` | PostgreSQL Licence | PostgreSQL + pgvector, **database only** (D-03). Uses a named Docker volume so no data directory lands under a cloud-sync folder. |

The pgvector extension is created by migration `0001_phase0` purely to prove the
database environment is the one Continuum expects. **No column in Phase 0 uses
a vector type** — `test_no_vector_column_exists_in_phase_0` asserts this.
Embeddings arrive in Phase 3 as model-versioned *rows* (F-47), never as a column
on a segment.

---

## 6. Model assets

**Empty. Continuum downloads, bundles and uses zero model weights at Phase 0.**

This section exists now because the dependency shortlist tracks *code* licences
carefully and *model weight* licences not at all (F-55) — and they are
independent. The weights Continuum will eventually want (Whisper, image-model
checkpoints, community LoRAs, TTS voices) carry their own terms, several of
them OpenRAIL-style, non-commercial, or carrying likeness restrictions that bear
directly on Master Plan §2.8 and §111.

When the first weight arrives (Phase 4, local transcription), record it here:

| Model | Source | Version / hash | Code licence | **Weights licence** | Redistribution permitted | Commercial use | Likeness / authorization constraint |
|---|---|---|---|---|---|---|---|
| *(none)* | | | | | | | |

Rules for that table:

- **Continuum never bundles weights it cannot redistribute.** It points at them,
  the user fetches them, and the licence note is carried in the
  `ProviderDescriptor` so the policy engine can see it.
- A permissive *code* licence says nothing about the *weights*. Record both.
- Anything touching third-party performer likeness stays behind an explicit
  authorization gate and is never a default pipeline (§2.8, §102).

---

## 7. Deliberately not used

Recorded so nobody re-litigates these by accident.

| Not used | Why |
|---|---|
| Redis, Celery, Temporal | PostgreSQL is the sole durable job store (D-02). Job state must live in the database of record; a second store adds a consistency problem for no benefit at single-user scale. |
| SQLite (as the queue) | No `FOR UPDATE SKIP LOCKED`. The queue would be built on a different concurrency model than it ships with, and §110.6–110.11 would be testing the wrong thing (OQ-1). |
| Neo4j / any graph database | PostgreSQL first. Relational edges are sufficient until measured need says otherwise (§52). |
| S3 / object storage | Filesystem + PostgreSQL. No infrastructure inflation. |
| Kubernetes, microservices | One worker process with pluggable handlers (F-59). Five deployables would be the microservice architecture §111 forbids. |
| Any auth library | Phase 0 is loopback-only with no authentication (A-03). Adding a dormant auth path invites someone to enable non-loopback binding without the security decision that must accompany it. |
| FFmpeg, PySceneDetect, pysubs2, PDF.js, epub.js | Phase 2/4 media dependencies. Not Phase 0 scope. |

---

## 8. GPL policy

**No code, code fragments, or line-by-line ports from GPL-licensed sources** may
enter Continuum (D-17).

- **Jellyfin** (GPL-2.0) — architectural and UX *reference only*, from reading
  documentation and observing behavior. Never copy.
- **Komga** (MIT) — reuse would be permissible with attribution, but its Kotlin
  stack does not match Continuum, so it is reference-only in practice too.
- **FFmpeg** — Continuum will invoke a **user-installed binary** via subprocess,
  creating no linking relationship. **Continuum does not distribute FFmpeg.** If
  a bundled build is ever considered, the licensing analysis must be redone:
  `--enable-gpl` and `--enable-nonfree` builds change the answer.

---

## 9. Adding a dependency

1. Check the licence — **and the model-weight licence separately** if weights
   are involved.
2. Check activity: last release, open critical issues, maintenance signals.
3. Pin an exact version in `pyproject.toml` or `apps/web/package.json`.
4. Wrap it behind an adapter. Application code should not import a vendor SDK
   directly — that is what `packages/providers` exists for.
5. Add a smoke or contract test that fails if the dependency's behavior changes.
6. **Add a row to this file**, including *why* the dependency is justified.
7. If it is an AI SDK, confirm it does not break §110.12 — and expect to justify
   why a fake would not have served.
