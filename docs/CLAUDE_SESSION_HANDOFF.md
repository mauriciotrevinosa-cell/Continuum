# Claude Session Handoff — Phase 0 implementation

**Written because:** Claude usage reached ~94% of the session limit. Handoff created
per `docs/CLAUDE_CREDIT_HANDOFF_PROTOCOL.md` **before** being cut off, not after.

**Phase 0 is NOT complete.** Do not tag `continuum-phase-0`. The remaining work is
documentation plus one environment prerequisite, both listed precisely below.

---

## 1. Current state

| | |
|---|---|
| **Branch** | `phase-0/claude-implementation` |
| **HEAD** | `dfcad4b307458e9a357155c343b4fd45637275ba` |
| **HEAD subject** | `ci: add cross-platform workflow, dev scripts and OpenAPI client` |
| **Working tree** | **clean** — nothing uncommitted, nothing stashed |
| **Phase 1 started?** | **No.** Confirmed explicitly in §8. |

Ten commits landed this session, each independently green:

```text
dfcad4b  ci: add cross-platform workflow, dev scripts and OpenAPI client
d169310  feat: add phase 0 web shell and API console entrypoints
a50d156  test: add durable job acceptance suite (110.6-110.11)
9ab11e2  feat: add phase 0 API surface, standalone worker and synthetic handlers
4c74524  refactor: move job domain enums from continuum_db to continuum_core
b031574  feat: add local provider contracts, policy and deterministic fakes
121f5a5  feat: add durable job database model and state machine
163535a  feat: add safe storage foundation
eb782ec  chore: bootstrap Continuum phase 0 monorepo
a6386a5  chore: add gitattributes LF policy before implementation code
```

---

## 2. What was being worked on when the limit hit

Writing the four required Phase 0 documents (runbook §5). **None of them exist yet.**
No code was in flight — the last commit closed cleanly before this handoff.

---

## 3. Fully complete

All implementation scope from `docs/CLAUDE_PHASE_0_START.md` §2–§3.

**Monorepo / tooling** — `uv` workspace pinned to **Python 3.12** (D-04) with nine
member packages; `pnpm` workspace; `docker-compose.yml` for the **database only**
(D-03) using a named volume so no PostgreSQL data directory lands under OneDrive;
`.gitattributes` landed **before** any implementation code (D-20).

**Storage (ADR-0001, all five layers)** — `SourceVaultReader` with no mutating member
at all; `resolve_within()` validating then realpath-resolving then containing, with
`same_file_as()` closing the TOCTOU window; import-boundary enforcement (4 contracts +
an AST walk); content-addressed writes (temp → fsync → atomic rename); and a
**non-mutating** vault probe per **A-01** — it reports `not_verified` on Windows rather
than proving hardening by writing.

**Durable jobs (ADR-0002)** — six tables exactly; guarded transition table that raises;
pause/cancel as request flags; leases + heartbeat + reaper on the **database clock**;
`job_step` unit idempotency; checkpoints; dependency DAG that **blocks** rather than
cancels dependents; dedupe via partial unique index; `run_after` + full-jitter backoff;
append-only `job_event`; `resource_class`; `hardware_signature` as a plain string.

**Providers (ADR-0004)** — required `DataClass` with no default; privacy filtered
*before* cost; **no code path from `FREE_LOCAL` to PAID/REMOTE**; fakes only, zero AI
SDKs installed.

**API** — 12 routes, loopback-only enforced by config validation, no filesystem path
parameter anywhere, CORS restricted, correlation ids propagated.

**Worker** — standalone process, no channel to the API, signal **and** DB drain flag.

**Web** — three screens (status, jobs, job detail), no placeholder navigation.

**CI** — Python matrix on ubuntu **and** windows; a step that **fails the build if the
durable-job suite skips**; a separate offline/no-credential job; OpenAPI→TS drift check.

---

## 4. Partially complete / not started

| Item | State | Notes |
|---|---|---|
| `README.md` | **Not written** | Runbook §5 requires exact commands that have actually been run. Most are captured in §6 below — reuse them verbatim. |
| `AGENTS.md` | **Not written** | Permanent engineering constraints for future agents. |
| `docs/DEPENDENCIES.md` | **Not written** | Must include an explicit **empty** Model Assets section (F-55). |
| `docs/PHASE_0_REPORT.md` | **Not written** | Must carry the §110 matrix with PASS / FAIL / NOT-RUN and the exact proving command. Draft status is in §5. |
| Database-dependent acceptance items | **Written, never executed** | Blocked on Docker — see §7. |

---

## 5. Acceptance matrix — honest status

`PASS` means executed and green on this machine. `NOT RUN` means never executed here.
**Nothing below is marked PASS on the strength of code inspection alone.**

| §110 | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Clean install / migrations / boot | **NOT RUN** | Needs Docker (§7). Migration renders valid DDL offline. |
| 2 | Web can call API health | **PASS** | End-to-end: page rendered live version, `FREE_LOCAL`, fake provider ids, loopback host, vault status, OneDrive warning. |
| 3 | Root/path normalisation | **PASS** | `tests/acceptance/test_110_03_path_normalization.py`, incl. 400 Hypothesis cases. |
| 4 | Traversal / symlink / junction escape | **PARTIAL PASS** | Junction escape (the privilege-free Windows vector) passes. **5 symlink tests SKIPPED** — this machine denies `os.symlink` without Developer Mode. Linux CI covers them. |
| 5 | Vault cannot be modified | **PASS** | 15 tests across four layers, incl. byte-identical tree snapshot after boot and probe. |
| 6 | Synthetic job roundtrip | **NOT RUN** | Needs Docker. |
| 7 | Progress independent of UI | **NOT RUN** | Needs Docker. |
| 8 | UI restart does not cancel work | **NOT RUN** (structurally true) | No API↔worker channel exists; subprocess test written. |
| 9 | Graceful drain leaves resumable state | **NOT RUN** | Needs Docker. |
| 10 | Resume only unfinished units | **NOT RUN** | Needs Docker. **The load-bearing test.** |
| 11 | Structured error / retry / lease expiry | **NOT RUN** | Needs Docker. |
| 12 | Providers need no cloud credentials | **PASS** | 24 tests offline; asserts openai/anthropic/torch/etc. are all absent. |
| 13 | Logs redact secrets | **PASS** | Config dump + exception at DEBUG; pattern **and** exact-value redaction. |
| 14 | Migrations clean, single head | **PARTIAL PASS** | 6 of 8 pass with no database (single head, 7 CREATE TABLE, pgvector present, no vector column, all 5 critical constraints). Round trip **NOT RUN**. |
| 15 | Required documents exist | **FAIL** | Four documents missing (§4). |

**Local totals:** 151 passed, 24 skipped, 0 failed. ruff clean; 87 files formatted;
mypy **strict** clean on 49 files; 4/4 import contracts; web typecheck/lint/build clean.

---

## 6. Exact commands the next agent should run first

```bash
cd C:/Users/mauri/OneDrive/Desktop/Continnum && git log --oneline -1
```

```bash
uv sync --python 3.12 && uv run pytest -q
```

Expected: `151 passed, 24 skipped`. Then, to reproduce every gate:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy packages apps workers && uv run lint-imports
```

Web gates (needs `$env:APPDATA\npm` on PATH for pnpm):

```bash
pnpm install && pnpm lint && pnpm typecheck && pnpm build:web
```

Once Docker exists, the whole point of the phase becomes testable:

```bash
docker compose up -d db && uv run alembic upgrade head && uv run pytest -q
```

---

## 7. Blockers — environment, not code

**B-1 · Docker Desktop is not installed. (BLOCKING §110.1, 6–11, 14-roundtrip.)**
This is an OS-level install needing admin rights and a reboot, so it was deliberately
not performed — `FOUNDATION_APPROVAL` §7 says setup must not silently change the user's
machine. `winget install Docker.DockerDesktop`, reboot, launch once to accept the
licence, then run the command above. **This is an environment prerequisite, not a code
defect.**

**B-2 · Repo and data roots are under OneDrive. (BLOCKING acceptance per OQ-2 / D-19.)**
The sync-folder detector fired correctly during a real API boot, which is the
detector working, not a bug. Acceptance still requires moving to non-synced local
storage and correcting the `Continnum` → `Continuum` spelling. Since the repo is fully
pushed, `git clone` to `C:\Continuum` is non-destructive.

**B-3 · Windows symlink creation denied. (Degrades §110.4.)**
Enable Developer Mode (Settings → System → For developers) to run the 5 skipped
symlink tests locally, or rely on the Linux CI leg. Junction escape — the vector that
needs no privilege — already passes here.

**B-4 · Port 8000 is occupied by another process (PID 6568).**
Not a defect. The end-to-end run used `CONTINUUM_API_PORT=8010`. Document this in
README rather than changing the default.

---

## 8. Confirmations

- **No Phase 1 work was started.** No reader, scanner, media parsing, SourceAsset /
  SourceSegment table, locator implementation, embedding, canon extraction, Character
  Brain, Story Studio, Visual Lab, or real AI provider exists. Enforced by
  `test_no_premature_domain_tables` (24 forbidden table names) and
  `test_surface_is_limited_to_health_jobs_workers`.
- **`continuum-phase-0` tag was NOT created.** Codex audit and human review come first.
- **No test was weakened or deleted** to make anything pass.
- **No failing test is being hidden.** Every skip prints its reason and the command
  that would un-skip it.

---

## 9. Deviations from the plan worth reviewing

1. **`packages/config` was added** as a tenth package. Architecture review §Q sketched
   settings inside `apps/api`, but the worker needs the same settings and must not
   import the API application — that would couple the two processes ADR-0002 §12
   separates. Config now sits below both.
2. **Job enums live in `continuum_core`, not `continuum_db`.** The import-linter
   layering contract caught `continuum_providers` importing the database package purely
   to reach `BlockedReason`. They are domain primitives; `continuum_db.enums` remains a
   thin re-export.
3. **ESLint pinned to 8.57.1.** `eslint-config-next` 15 patches ESLint internals and
   breaks on ESLint 9. This is the combination Next actually supports.

None of these change an approved decision; all three are recorded in commit messages.

---

## 10. Two defects found and fixed while verifying

- **`/ready` hung** for the OS TCP default when PostgreSQL was unreachable. A readiness
  probe that hangs is useless — now answers 503 in ~3s with remediation.
- **The import-linter filesystem contract followed indirect imports**, so every consumer
  of `continuum_storage` counted as importing `pathlib`. Scoped to direct imports, which
  is what ADR-0001 Layer 3 actually specifies.

---

## 11. Recommended next step

Write the four documents in §4 — the only remaining implementation-side work — then
resolve **B-1** and re-run the suite so §110.1 and 6–11 move off `NOT RUN`. Only after
that does the Codex audit (`docs/CODEX_PHASE_0_AUDIT.md`) have a complete candidate to
audit.

The Phase 0 candidate commit for audit, once the documents land, will be the commit
that adds them. **As of this handoff the candidate is not yet complete.**
