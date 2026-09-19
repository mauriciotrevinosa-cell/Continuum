# Visual Knowledge / Manga Renderer — Pre-Claude Ready Status v0.1

**Status:** pre-implementation package complete  
**Branch:** `m3/critical-path`  
**Important:** Claude must still run a fresh `git pull --ff-only` before trusting this document.

## Completed before Claude

- Visual Knowledge vs House Style vs Scene Treatment vs Layered Construction separated.
- The Arrivals House Style documented as evolving, not a fixed four-manga percentage blend.
- chibi/super-deformed preserved as a non-urgent visual mode, not a second identity.
- layered construction stages and freeze/invalidation rules specified.
- Visual Knowledge item JSON schema created.
- storage/intake routing defined using existing Continuum roots.
- external manga/drawing dataset discovery pass completed.
- dataset licenses/rights re-verified against current web sources.
- ready-made manga analyzers identified so we do not train basic panel detection from scratch.
- Manga109-s identified as the primary fundamentals dataset to evaluate.
- MangaSegmentation identified as a strong mask/segmentation candidate.
- Manga109 panel-order-estimator identified as a ready-made RTL ordering baseline.
- DiffSensei/MangaZero captured as research references with explicit license/image-rights caveats.
- benchmark ladder defined from CAL-01 through CAL-17.
- Work test plan defined so credits are not spent on architecture discovery.
- preliminary code-integration map prepared from current Continuum implementation.
- Claude return handoff prepared with mandatory full-project reconnaissance before code.

## What is deliberately NOT done yet

- no copyrighted/gated dataset bytes downloaded into the repo;
- no Manga109-s access request accepted on the user's behalf;
- no LoRA trained;
- no new DB migration;
- no new parallel Visual Knowledge subsystem;
- no production provider hardwired to any newly found analyzer;
- no Work credits spent;
- no CAL render attempted with the new architecture.

These are intentional gates, not missing prep.

## First human/account action that may be needed

**Manga109-s is gated.**

If we decide to use it directly, the user must accept/apply through the official Hugging Face dataset page. Processing can take days.

This does **not** block coding the registry/importer/analyzer interface. It only blocks direct local experiments requiring the raw Manga109-s pages.

## Best no-wait path

Claude can begin implementation without waiting for Manga109-s access by using:
- current local Vault/intake fixtures;
- generated/synthetic fixtures;
- publicly available pretrained manga detector weights where their terms permit;
- existing Continuum deterministic fake/test providers.

The first vertical slice remains CAL-01 environment-only.

## Claude start sequence

1. `git status`
2. `git switch m3/critical-path`
3. `git pull --ff-only origin m3/critical-path`
4. `git rev-parse HEAD`
5. full-project reconnaissance;
6. read the Story Board and new Visual Knowledge package;
7. produce integration audit **before broad code changes**;
8. review audit;
9. implement CAL-01 vertical slice in small commits.

Detailed prompt:
[CLAUDE_RETURN_HANDOFF_v0.1.md](./CLAUDE_RETURN_HANDOFF_v0.1.md)

## Work start gate

Do not invoke Work until:
- code exists;
- local tests pass;
- a concrete workflow is expected to work.

Then begin with W01 / CAL-01.

Detailed test plan:
[WORK_TEST_PLAN_v0.1.md](./WORK_TEST_PLAN_v0.1.md)
