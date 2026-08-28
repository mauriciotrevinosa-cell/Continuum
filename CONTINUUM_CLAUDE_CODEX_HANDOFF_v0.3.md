# Continuum — Claude / Codex Step-by-Step Handoff v0.3

**Purpose:** Start Project Continuum safely and incrementally. This handoff is intentionally strict: architecture review first, then one milestone at a time, then independent audit.

**Authoritative product spec:** `PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md`

**Dependency research snapshot:** `CONTINUUM_GITHUB_REPO_SHORTLIST.md`

---

# 0. Files to prepare before any coding

Create a new folder/repository named `Continuum/` containing only:

```text
Continuum/
├── PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md
├── CONTINUUM_GITHUB_REPO_SHORTLIST.md
└── CONTINUUM_CLAUDE_CODEX_HANDOFF_v0.3.md
```

Initialize Git and make a documentation-only commit.

Suggested commit:

```text
chore: initialize Continuum architecture docs
```

Do **not** copy anime, manga, light novels, the character-selection JSON, local models, or other large/private source media into the repo at this stage.

---

# 1. CLAUDE FIRST — ARCHITECTURE REVIEW ONLY

Give Claude Code the repository and paste the following prompt **exactly as the first assignment**:

```text
Read PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md completely, including the v0.2 Living Story Vault addendum and the authoritative v0.3 consolidation sections.
Read CONTINUUM_GITHUB_REPO_SHORTLIST.md completely.
Read CONTINUUM_CLAUDE_CODEX_HANDOFF_v0.3.md.

DO NOT WRITE IMPLEMENTATION CODE YET.
DO NOT START PHASE 0 YET.

Act as the senior architecture reviewer for Project Continuum: a local-first, private Source Vault + living multiverse story/production studio.

The v0.3 consolidation rules are authoritative when older text conflicts with them.

Review specifically:
1. contradictions or stale v0.2 assumptions that remain after v0.3;
2. whether /source-vault immutability can be enforced structurally rather than by convention;
3. the data-model boundaries among source canon, SourceCanonSnapshot, Character Brain, ProjectCharacterState, Branch, Story Calendar, Change Graph and generated artifacts;
4. the durable Job / JobStep / JobCheckpoint model, including crash recovery, pause/resume, idempotency and dependency handling;
5. whether closing the UI can safely remain independent from background workers;
6. migration/recovery behavior when the project moves to a different PC or required models/providers are missing;
7. provider abstraction risks and how to keep FREE_LOCAL as the default without hardcoding one model;
8. artifact recipe/lineage requirements needed for selective rerender and future remastering;
9. Visual Lab data boundaries: visual identity vs provider-specific LoRA/model assets, outfit variants, moodboards and story-linked assignments;
10. source-intelligence/RAG/provenance architecture and how to avoid an unnecessary giant fine-tuning dependency;
11. security/privacy/path traversal/symlink/secrets risks;
12. licensing/dependency concerns from the GitHub shortlist;
13. over-engineered parts;
14. under-designed parts;
15. decisions that MUST be made before Phase 0 implementation;
16. features that must explicitly stay delayed.

Permanent constraints:
- Do not redesign Continuum into a generic chatbot.
- Do not hardcode any franchise, character, crossover plot, city, government or romance.
- Do not create a manga/anime download or scraping subsystem.
- Do not implement DRM circumvention.
- Do not make cloud APIs mandatory.
- Do not implement voice cloning, Visual Lab generation, anime generation, power synchronization or story-generation features in Phase 0.
- Prefer root-cause architecture fixes over patches.
- Keep the monorepo as simple as possible while preserving clean module boundaries.

Create ONLY documentation:
- docs/ARCHITECTURE_REVIEW.md
- docs/ADR/0001-storage-and-source-vault.md
- docs/ADR/0002-durable-jobs-and-worker-boundary.md
- docs/ADR/0003-database-and-versioned-state.md
- docs/ADR/0004-provider-and-privacy-contract.md
- docs/ADR/0005-artifact-recipes-and-lineage.md
- docs/ADR/0006-phase-0-scope.md

Also include:
- exact proposed Phase 0 monorepo tree;
- exact database entities needed in Phase 0 only;
- exact acceptance-test matrix matching Master Plan §110;
- explicit list of deferred entities/features that should NOT be implemented yet;
- open questions that genuinely block implementation.

STOP BEFORE IMPLEMENTATION.
```

---

# 2. STOP AND REVIEW CLAUDE'S ARCHITECTURE

Do not immediately tell Claude to build.

Bring these files back for review:

```text
docs/ARCHITECTURE_REVIEW.md
docs/ADR/0001-*.md ... 0006-*.md
```

Review them against the v0.3 spec. Pay particular attention to any attempt to:

- weaken source-vault read-only guarantees;
- make Redis/cloud infrastructure mandatory without need;
- mix project continuity into source canon;
- store important state only in memory;
- treat the UI as the owner of jobs;
- overbuild production/AI features before the library foundation;
- collapse Visual Lab identity into one image model;
- add franchise-specific fields to core schemas.

Resolve architecture disagreements **before code exists**.

After approval, commit the ADRs.

Suggested commit:

```text
docs: approve Continuum foundation architecture
```

---

# 3. CLAUDE SECOND — IMPLEMENT PHASE 0 ONLY

After the architecture/ADRs are approved, paste:

```text
Read PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md and all approved ADRs.
Implement PHASE 0 ONLY as defined in Master Plan §109 and satisfy every acceptance test in §110.

Do not start Phase 1.

Permanent foundation rules:
- /source-vault is immutable through application storage logic;
- path normalization, traversal prevention and symlink escape protection must be tested;
- source canon and project continuity are separate layers;
- never hardcode a franchise/character/story premise;
- UI lifecycle and worker lifecycle are separate;
- long-running work uses durable Job / JobStep / JobCheckpoint records;
- progress/checkpoints must survive UI close and worker restart;
- use synthetic dummy jobs to prove resume/recovery before real media jobs exist;
- providers are behind interfaces and core boot requires no cloud API key;
- FREE_LOCAL is the default policy, but no specific AI model is hardcoded as mandatory;
- generated artifacts/recipes have clean extension points, but do not build production generation yet;
- prompt templates belong in versioned files when prompt infrastructure exists;
- no source downloading/scraping;
- no voice cloning;
- no Visual Lab generation;
- no anime/video generation;
- fix root causes, not symptoms;
- keep the Phase 0 implementation smaller than the future architecture.

Before declaring complete, run and document:
1. formatter/lint;
2. frontend typecheck/tests;
3. backend tests;
4. clean-database migrations;
5. local stack boot;
6. web → API health check;
7. source-vault path/traversal/symlink/write safety tests;
8. synthetic durable job queue test;
9. close/restart UI while worker job continues;
10. graceful worker stop and resume from checkpoint;
11. simulated retryable job failure and recovery;
12. no-cloud/no-paid-provider boot path;
13. secret redaction/log tests where applicable.

Create:
- AGENTS.md
- docs/DEPENDENCIES.md
- docs/PHASE_0_REPORT.md

PHASE_0_REPORT.md must map every Master Plan §110 acceptance item to PASS/FAIL plus the exact test/command proving it.

STOP AFTER PHASE 0.
```

---

# 4. CODEX — INDEPENDENT PHASE 0 AUDIT

Give Codex the same repository after Claude stops. Paste:

```text
Audit the existing Project Continuum Phase 0 implementation.

Read:
- PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md
- CONTINUUM_GITHUB_REPO_SHORTLIST.md
- all docs/ADR/*.md
- docs/ARCHITECTURE_REVIEW.md
- AGENTS.md
- docs/DEPENDENCIES.md
- docs/PHASE_0_REPORT.md

DO NOT ADD PRODUCT FEATURES.
DO NOT START PHASE 1.

Independently run the Phase 0 tests and verify Master Plan §110 item by item.

Look specifically for:
- source-vault path traversal or symlink escape;
- accidental write/delete/rename capability against source media;
- job state that exists only in process memory;
- completed work being repeated after restart;
- race conditions around pause/cancel/retry;
- UI shutdown accidentally cancelling worker work;
- broken migrations or non-clean bootstrap;
- hidden cloud/vendor coupling;
- credentials leaking to logs;
- frontend/backend contract drift;
- unnecessary Redis/microservice/infrastructure requirements;
- missing idempotency boundaries;
- incomplete error state/retry recording;
- future production or franchise-specific logic that leaked into Phase 0;
- missing tests for foundation invariants.

Fix ONLY verified Phase 0 defects or missing acceptance criteria.
Do not redesign already-approved architecture without documenting why a verified defect requires it.

Create docs/PHASE_0_CODEX_AUDIT.md with:
- findings;
- severity;
- files changed;
- tests run;
- before/after behavior;
- remaining risks;
- final PASS or FAIL recommendation.

STOP AFTER THE AUDIT.
```

---

# 5. CHECKPOINT PHASE 0

Only after Claude report + Codex audit + manual review are all satisfactory:

```bash
git status
git add .
git commit -m "feat: complete Continuum phase 0 foundation"
git tag continuum-phase-0
```

The tag is a recovery point. Do not move it later.

---

# 6. PHASE 1 — VAULT + LIBRARY MVP

Primary builder prompt:

```text
Implement PHASE 1 ONLY from PROJECT_CONTINUUM_MASTER_PLAN_v0.3.md.
Do not start Reader/Phase 2 or AI extraction.

Use synthetic test files only.

Acceptance scenario:
1. Configure /source-vault/franchises/demo/.
2. Add synthetic supported files.
3. Scan Library via a durable background job.
4. Assets are safely discovered, classified and fingerprinted.
5. Re-scan is idempotent and creates no duplicates.
6. Assets appear in the Library UI/API.
7. Original source files are byte-identical after every operation.
8. Removing an asset from Continuum removes derived/library records, not the source file.
9. Paths outside /source-vault are rejected.
10. Interrupted scan resumes/retries without repeating completed units unnecessarily.

No canon extraction.
No scraping/downloading.
No production generation.

Create docs/PHASE_1_REPORT.md and stop.
```

Have the other coding agent independently audit Phase 1 before tagging/advancing.

---

# 7. PHASE 2 — READER / MEDIA CENTER MVP

Build only source consumption and annotation:

- CBZ/image-folder reader;
- PDF.js PDF reader;
- epub.js compatibility spike then EPUB/LN reader if accepted;
- local video player/range streaming;
- FFmpeg cache proxy only where browser compatibility requires it;
- subtitle normalization via pysubs2 where useful;
- progress/bookmarks/notes;
- stable source locators;
- Send to Project reference records.

Komga/Jellyfin remain architecture/UX references, not applications to copy wholesale.

No Canon/Character Brain extraction yet.

---

# 8. PHASE 3 — SOURCE INTELLIGENCE FOUNDATION

Only after the readers and stable source locators work:

- source segments;
- provenance;
- extraction job framework;
- full-text/vector/structured retrieval;
- review/correction loop;
- synthetic golden source corpus;
- structured claims with evidence.

Do not start by fine-tuning a giant model on the user's library.

The first quality gate is: given a synthetic source segment, Continuum can extract a known fact, cite its exact locator, preserve uncertainty, accept a user correction, and retrieve the corrected result later.

---

# 9. PHASE 4+ ORDER

Proceed one audited milestone at a time:

```text
Phase 4  Anime / Multimodal Intelligence
Phase 5  Character / Canon Intelligence + Character Brain
Phase 6  Project / Branch / World Studio
Phase 7  Story Planning + Calendar + Relationships + Civilization
Phase 8  Continuity + Change Graph
Phase 9  Canon Sync + Ripple / Retcon
Phase 10 Visual Lab
Phase 11 Script / Manga / Storyboard / Animatic
Phase 12 Local Image / Video / Audio Production
Phase 13+ Advanced Director / Automation / later power systems
```

Never skip directly to production because an exciting model becomes available. Providers are replaceable; the continuity/source/project foundation is the durable product.

---

# 10. CLAUDE / CODEX DIVISION OF LABOR

Default pattern:

**Claude:** architecture reviews, schema/ADR reasoning, cross-module invariants, difficult design changes.

**Codex:** implementation, tests, CI/debugging, isolated refactors, independent acceptance audits once boundaries are approved.

Either can do the other role when useful, but do not let two agents independently redesign the same core schema simultaneously.

Good later parallelization:

- PDF reader vs EPUB reader;
- subtitle parser vs CBZ manifest;
- separate provider adapters after contracts are locked;
- isolated UI screens using approved APIs.

Bad parallelization:

- multiple agents simultaneously redesigning Character/CanonClaim/Event/Branch/Job schemas;
- one agent changing migrations while another changes the same model without coordination.

---

# 11. PERMANENT MILESTONE LOOP

For every phase:

```text
INSPECT SPEC
→ PROPOSE / ADR IF NEEDED
→ REVIEW
→ IMPLEMENT ONE PHASE
→ RUN ACCEPTANCE TESTS
→ WRITE PHASE REPORT
→ INDEPENDENT AUDIT
→ FIX VERIFIED DEFECTS
→ COMMIT + TAG/CHECKPOINT
→ NEXT PHASE
```

Never use:

```text
"Here are all the docs; build the whole app."
```

---

# 12. CREATIVE DATA STAYS OUT OF ENGINE LOGIC

When creative work resumes, keep project-specific material under project/creative data, for example:

```text
creative/
├── PROJECT_PREMISE.md
├── CHARACTER_POOL.json
├── STORY_PRINCIPLES.md
├── STORY_ANCHORS.md
├── NO_GO_RULES.md
├── WORLD_IDEAS.md
└── RELATIONSHIP_IDEAS.md
```

The current character-selection export can later become input to the Character Vault importer, but should not be used as a core schema fixture.

A skipped/unanswered character is not automatically excluded. The project model supports APPROVED / OPTIONAL / UNREVIEWED_RESERVE / EXCLUDED separately from narrative roles.

---

# 13. FIRST THING TO SEND BACK AFTER CLAUDE

After Step 1, do **not** send code yet. Send back these files for review:

```text
docs/ARCHITECTURE_REVIEW.md
docs/ADR/0001-storage-and-source-vault.md
docs/ADR/0002-durable-jobs-and-worker-boundary.md
docs/ADR/0003-database-and-versioned-state.md
docs/ADR/0004-provider-and-privacy-contract.md
docs/ADR/0005-artifact-recipes-and-lineage.md
docs/ADR/0006-phase-0-scope.md
```

That is the next human review gate.
