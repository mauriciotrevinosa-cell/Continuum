# Phase 0 Report

**Status:** implementation complete; acceptance **incomplete**.
**Recommendation:** **DO NOT TAG** `continuum-phase-0` yet.
**Branch:** `phase-0/claude-implementation`
**Report date:** 2026-09-01
**Environment:** Windows 11 (10.0.26200), Python 3.12.10, Node v24.15.0, pnpm 9.15.4

---

## 1. Verdict, stated plainly

Every line of Phase 0 implementation scope from `docs/CLAUDE_PHASE_0_START.md`
§2–§3 is written, and every gate that *can* run on this machine is green:
**151 passed, 24 skipped, 0 failed**, with ruff, `mypy --strict`, four import
contracts, and the full web toolchain clean.

**Phase 0 is nevertheless not complete**, for one reason: **Docker Desktop is
not installed on this machine**, so seven of the fifteen §110 acceptance items
have never been executed. They are written, lint-clean and type-clean, but they
have not run.

Those seven are not incidental — they are the items that prove the thing this
phase exists to prove: that a job survives a crash and resumes without redoing
or corrupting work. Reporting them as PASS on the strength of code review would
defeat the purpose of having an acceptance matrix at all.

**Nothing in this document is marked PASS unless it actually executed here and
was observed green.**

---

## 2. Acceptance matrix — Master Plan §110

| # | Requirement | Result | Proving command | Evidence |
|---|---|---|---|---|
| 1 | Clean clone/install/migrations/boot | **NOT RUN** | `docker compose up -d db && uv run alembic upgrade head` | Blocked by **B-1**. Migration *renders* valid DDL offline (see 14). |
| 2 | Web UI can call API health | **PASS** | `uv run pytest tests/acceptance/test_110_02_health_and_api.py` | 25 passed. Plus a live end-to-end run: see §4. |
| 3 | Vault path resolved/normalised safely | **PASS** | `uv run pytest tests/acceptance/test_110_03_path_normalization.py` | 33 passed, incl. 400 Hypothesis-generated path inputs. |
| 4 | Traversal and symlink escape rejected | **PARTIAL** | `uv run pytest tests/acceptance/test_110_04_traversal.py` | 13 passed, **6 skipped**. See §5 — junction escape passes; symlink cases blocked by **B-3**. |
| 5 | App cannot write/delete/rename vault files | **PASS** | `uv run pytest tests/acceptance/test_110_05_vault_readonly.py` | 15 passed across four independent layers. |
| 6 | Synthetic durable job queued and processed | **NOT RUN** | `uv run pytest tests/acceptance/test_110_06_11_durable_jobs.py` | Blocked by **B-1**. |
| 7 | Progress persisted independently of the web page | **NOT RUN** | same | Blocked by **B-1**. |
| 8 | Closing/restarting the UI does not cancel the job | **NOT RUN** *(structurally true)* | same | Blocked by **B-1**. No API↔worker channel exists at all — see §6. |
| 9 | Graceful worker stop leaves the job resumable | **NOT RUN** | same | Blocked by **B-1**. |
| 10 | Restart resumes only unfinished units | **NOT RUN** | same | Blocked by **B-1**. **The load-bearing item** — see §7. |
| 11 | Failed job records structured error/retry state | **NOT RUN** | same | Blocked by **B-1**. |
| 12 | Providers work with fakes; no cloud credentials | **PASS** | `uv run pytest tests/acceptance/test_110_12_providers.py` | 24 passed offline with an empty `.env`. |
| 13 | Logs do not expose secrets | **PASS** | `uv run pytest tests/acceptance/test_110_02_health_and_api.py -k Secrets` | Included in the 25 above. |
| 14 | Migration strategy documented; clean migration tested | **PARTIAL** | `uv run pytest tests/acceptance/test_110_14_migrations.py` | 7 passed, **2 skipped** (round trip needs a database). |
| 15 | Required documents exist before tagging | **PASS** | `ls README.md AGENTS.md docs/DEPENDENCIES.md docs/PHASE_0_REPORT.md docs/ADR/` | All present as of this commit. |

**Tally: 6 PASS · 2 PARTIAL · 7 NOT RUN · 0 FAIL.**

### Additional invariant tests (architecture review §S.1)

| Invariant | Result | Count | Guards |
|---|---|---|---|
| Import boundary + layering | **PASS** | 4 | ADR-0001 Layer 3 |
| Job transition table | **PASS** | 24 | F-28, F-23 |
| No real franchise strings | **PASS** | 3 | A-05, D-18, F-10 |
| No model identifiers in app logic | **PASS** | 2 | ADR-0004 §4 |
| Exactly six tables / no premature domain tables | **PASS** | 2 | ADR-0006 §3 |

---

## 3. Quality gates — actual output

Every command below was run at this commit. The output is quoted verbatim.

| Gate | Command | Result |
|---|---|---|
| Lint | `uv run ruff check .` | `All checks passed!` |
| Format | `uv run ruff format --check .` | `93 files already formatted` |
| Types | `uv run mypy packages apps workers` | `Success: no issues found in 49 source files` (strict) |
| Import contracts | `uv run lint-imports` | `Contracts: 4 kept, 0 broken.` |
| Alembic head | `uv run alembic heads` | `0001_phase0 (head)` — exactly one |
| Python tests | `uv run pytest tests/` | `151 passed, 24 skipped` |
| Web lint | `pnpm lint` | `✔ No ESLint warnings or errors` |
| Web types | `pnpm typecheck` | `tsc --noEmit` exit 0 |
| Web build | `pnpm build:web` | exit 0, 4 routes compiled |

### Per-file test results

```text
test_110_02_health_and_api          25 passed    0 skipped
test_110_03_path_normalization      33 passed    0 skipped
test_110_04_traversal               13 passed    6 skipped
test_110_05_vault_readonly          15 passed    0 skipped
test_110_06_11_durable_jobs          1 passed   16 skipped
test_110_12_providers               24 passed    0 skipped
test_110_14_migrations               7 passed    2 skipped
test_import_boundaries               4 passed    0 skipped
test_job_state_machine              24 passed    0 skipped
test_no_franchise_strings            3 passed    0 skipped
test_no_model_literals               2 passed    0 skipped
--------------------------------------------------------
TOTAL                              151 passed   24 skipped   0 failed
```

Not run: `pnpm test`. Vitest is declared but **no frontend tests exist** in
Phase 0. Stating that plainly rather than reporting a vacuous pass.

---

## 4. §110.2 verified end-to-end, not just by unit test

The API was started and the web app was pointed at it. The rendered HTML at
`http://127.0.0.1:3000/` contained, from the live `/health` response:

| Probe | Found |
|---|---|
| `0.1.0-phase0` (version) | yes |
| `FREE_LOCAL` (profile) | yes |
| `fake.echo-text` (provider id) | yes |
| `127.0.0.1` (bind address) | yes |
| `not_verified` (vault protection) | yes |
| `read-only` (source_vault badge) | yes |
| `OneDrive` (sync warning) | yes |
| "API unreachable" banner | **absent** — it really reached the API |

`/jobs` returned HTTP 200 in the same run.

Two facts worth recording from that run. The **sync-folder detector (F-13) fired
correctly in real operation** against the fixture vault under OneDrive — the
detector working, not a bug, and precisely the condition OQ-2 requires resolved.
And the run used `CONTINUUM_API_PORT=8010` because port 8000 is occupied on this
machine (**B-4**).

---

## 5. §110.4 is PARTIAL — exactly what is and is not covered

| Escape vector | Result | Note |
|---|---|---|
| `..` traversal (5 forms) | **PASS** | |
| Absolute path to a real outside file | **PASS** | |
| Drive-relative (`C:foo`), UNC, `\\?\` | **PASS** | |
| Alternate data stream (`file.txt:evil`) | **PASS** | |
| Trailing dot / trailing space | **PASS** | |
| Reserved device names (CON, NUL, COM1…) | **PASS** | Every name in the set |
| 8.3 short-name alias | **PASS** | |
| Case-insensitive containment | **PASS** | |
| **Directory junction to outside** | **PASS** | The realistic Windows vector — needs no privilege |
| Symlink to outside file | **SKIPPED** | **B-3** |
| Symlinked directory component | **SKIPPED** | **B-3** |
| Symlink staying inside the root (must be allowed) | **SKIPPED** | **B-3** |
| Vault iteration skips escaping links | **SKIPPED** | **B-3** |
| TOCTOU: path swapped after validation | **SKIPPED** | **B-3** |
| POSIX absolute path | **SKIPPED** | Not applicable on Windows; Linux CI covers it |

Per **OQ-6**, these skips are reported explicitly and are **not** counted as a
pass. The CI workflow runs the Python matrix on **both** `windows-latest` and
`ubuntu-latest` precisely because neither platform alone gives full coverage:
Windows has junctions, 8.3 names and ADS; Linux can create symlinks freely.

---

## 6. §110.8 is structurally true but still NOT RUN

The topology makes "closing the UI cannot cancel a job" true by construction:

```text
web ──HTTP──▶ api ──SQL──▶ postgres ◀──SQL── worker
```

There is **no API↔worker channel** — no RPC, no socket, no shared memory, and
the worker never imports `continuum_api` (asserted by a subprocess test that
imports the worker in a clean interpreter and checks `sys.modules`). The worker
is launched by `exec` as its own OS process, never as a child of the API or the
dev server.

That is an argument, not a measurement. **It is still marked NOT RUN**, because
the test that actually kills the API mid-job needs a database.

---

## 7. Why §110.10 matters more than the others

`test_forced_rerun_of_a_completed_unit_is_a_no_op` is the single most important
unexecuted test in this phase.

"Resumes only unfinished units" is trivially satisfiable by a handler that
simply never retries anything. What the invariant actually requires (ADR-0002
§2, F-22) is that re-running a **completed** unit is *safe* — because
at-least-once execution guarantees it will eventually happen, in the window
between an effect landing and its completion record committing.

The test forces every completed unit to execute again and asserts three things:
stored content is byte-identical, no duplicate `job_step` row appears, and every
unit reports `already_present=True` — i.e. the re-run recognised existing
content instead of writing a second file.

The implementation supports this: the synthetic handler's marker bytes contain
no timestamp, no random value and no attempt counter, so the content hash is
stable across runs, and `DerivedStore._land()` short-circuits when the
destination already exists.

**But it has not been executed.** Until it has, F-22 is designed-for, not proven.

---

## 8. Environment prerequisites — what the user must do

None of these are code defects. Each was inspected on this machine on
2026-09-01 and confirmed still outstanding.

### B-1 · Docker Desktop is not installed — **BLOCKS §110.1, 6–11, 14-roundtrip**

`docker --version` → not found. This needs administrator rights, a reboot, and a
one-time licence acceptance, so it was deliberately **not** performed:
`FOUNDATION_APPROVAL` §7 says setup must not silently change the user's
operating system.

```bash
winget install Docker.DockerDesktop
```

Reboot, launch Docker Desktop once to accept the licence, then:

```bash
docker compose up -d db && uv run alembic upgrade head && uv run pytest -q
```

Expected afterwards: the 16 currently-skipped durable-job tests and the 2
migration round-trip tests execute, moving items 1 and 6–11 off NOT RUN.

### B-2 · Repo and data roots are under OneDrive — **BLOCKS acceptance (OQ-2/D-19)**

`C:\Users\mauri\OneDrive\Desktop\Continnum`. The detector already flags this at
boot. Since the repository is fully pushed, relocating is non-destructive:

```bash
git clone https://github.com/mauriciotrevinosa-cell/Continuum.git C:/Continuum
```

Then work from `C:\Continuum` and set `CONTINUUM_DATA_HOME` to a non-synced path
such as `C:\ContinuumData`. This also fixes the `Continnum` → `Continuum`
spelling (D-19). **Do not delete the OneDrive copy until the clone is verified.**

### B-3 · Windows Developer Mode is off — **degrades §110.4**

Registry `AllowDevelopmentWithoutDevLicense` is unset, so `os.symlink` is denied
and 5 symlink tests skip.

Settings → System → For developers → **Developer Mode: On**. Then:

```bash
uv run pytest tests/acceptance/test_110_04_traversal.py -q -rs
```

This is optional if the Linux CI leg is accepted as coverage for symlinks; the
junction vector already passes here.

### B-4 · Port 8000 is occupied — cosmetic

Held by PID 6568 (`Manager`). Not a defect. Either stop that process or set
`CONTINUUM_API_PORT=8010` and `CONTINUUM_API_BASE=http://127.0.0.1:8010`.

---

## 9. Scope compliance

**No Phase 1+ feature was implemented.** No reader, scanner, media parsing,
`SourceAsset`/`SourceSegment` table, locator implementation, embedding, canon
extraction, Character Brain, Story Studio, relationship logic, powers, Visual
Lab, image/audio/video generation, cast review, or real AI provider exists.

Enforced mechanically, not by assertion:

- `test_no_premature_domain_tables` — 24 forbidden table names, none present.
- `test_exactly_six_application_tables` — exactly `job`, `job_step`,
  `job_checkpoint`, `job_dependency`, `job_event`, `worker`.
- `test_surface_is_limited_to_health_jobs_workers` — the OpenAPI spec contains
  exactly 12 routes and no others.
- `TestNoAiSdkIsInstalled` — 11 vendor SDKs asserted absent.

`docs/creative/THE_ARRIVALS_CREATIVE_DIRECTION_v0.1.md` was read and treated as
**future context only**, exactly as its §14 instructs. Nothing from it was
implemented. It lives in `docs/creative/`, which A-05 exempts from the
franchise-string rule; the engine itself remains franchise-agnostic.

---

## 10. Deviations from the plan

Three, all recorded in commit messages. None changes an approved decision.

1. **`packages/config` added as a tenth package.** Architecture review §Q
   sketched settings inside `apps/api`, but the worker needs the same settings
   and must not import the API application — that would couple the two processes
   ADR-0002 §12 deliberately separates. Config now sits below both.
2. **Job enums live in `continuum_core`, not `continuum_db`.** The import-linter
   layering contract caught `continuum_providers` importing the database package
   solely to reach `BlockedReason`. They are domain primitives;
   `continuum_db.enums` remains a thin re-export. *The boundary test found this,
   not review* — which is the argument for having it.
3. **ESLint pinned to 8.57.1.** `eslint-config-next` 15 patches ESLint internals
   via `@rushstack/eslint-patch` and fails on ESLint 9, silently producing no
   lint output. 8.57.1 is the supported combination.

### ADR-0001 Layer 5 was overridden, correctly

ADR-0001 originally proposed probing vault read-only status by *attempting a
write*. `FOUNDATION_APPROVAL` **A-01** forbids that outright. The implementation
follows the approval: `probe_vault_readonly()` is purely observational, and on
Windows it reports `not_verified` rather than guessing — because ACL enforcement
cannot be observed without writing. `test_probe_does_not_write_to_the_vault`
snapshots the vault tree and asserts byte-identity after three probe calls.

---

## 11. Defects found and fixed during verification

| Defect | Impact | Fix |
|---|---|---|
| `/ready` hung for the OS TCP default when PostgreSQL was unreachable | A readiness probe that hangs is useless — it cannot help diagnose the outage it exists to report | Explicit 3s `connect_timeout`; now answers 503 in ~3s with remediation text |
| import-linter's filesystem contract followed **indirect** imports | Every consumer of `continuum_storage` counted as importing `pathlib`, making the contract unusable | Scoped to direct imports (`allow_indirect_imports = True`), which is what ADR-0001 Layer 3 actually specifies |
| UUIDv7 was not monotonic within a millisecond | "Time-ordered" was untestable and paging by id was non-deterministic | RFC 9562 §6.2 method-1 counter in `rand_a`; verified strictly increasing across 5,000 rapid mints and unique across 8 threads |

---

## 12. Candidate commit for the Codex audit

**Audit the HEAD of `phase-0/claude-implementation`.**

Resolve it with:

```bash
git rev-parse phase-0/claude-implementation
```

The candidate is the commit that adds this report — deliberately identified by
reference rather than by a literal hash, because a hash written *inside* the
commit it names cannot be correct. `git log --oneline -1` on that branch is the
authoritative answer, and the exact value is also recorded in
`docs/CLAUDE_SESSION_HANDOFF.md` §1 after the fact.

Branch: `phase-0/claude-implementation`
Remote: `https://github.com/mauriciotrevinosa-cell/Continuum`

The auditor should follow `docs/CODEX_PHASE_0_AUDIT.md` and is specifically
asked to:

1. **Install Docker and run the seven NOT RUN items.** That is the highest-value
   thing an independent audit can do here. If any of them fails, this phase is
   not done regardless of what else is green.
2. **Run the suite on Linux**, which exercises the 5 symlink cases this Windows
   machine cannot.
3. **Attack the vault boundary** rather than reading it — try to find any path
   through `DerivedStore`, the API, or a dynamic root lookup that writes into
   `source_vault`.
4. **Challenge the idempotency claim** (§7) with a real mid-unit kill, not the
   simulated force-rerun.
5. Verify no Phase 1 logic leaked in.

---

## 13. Definition of done — remaining

Per `docs/CLAUDE_PHASE_0_START.md` §6 and the acceptance checklist:

- [x] All implementation scope written
- [x] Lint, format, strict types, import contracts clean
- [x] Suite passes offline with an empty `.env`
- [x] `README.md`, `AGENTS.md`, `docs/DEPENDENCIES.md`, `docs/PHASE_0_REPORT.md`
- [ ] **§110.1, 6–11 executed** — needs **B-1**
- [ ] **§110.4 symlink cases executed** — needs **B-3** or the Linux CI leg
- [ ] **§110.14 round trip executed** — needs **B-1**
- [ ] Repo and data roots off cloud sync — needs **B-2**
- [ ] Codex independent audit (`docs/CODEX_PHASE_0_AUDIT.md`)
- [ ] Final human / ChatGPT review
- [ ] **Only then:** tag `continuum-phase-0`

**The tag has not been created and must not be created yet.**
