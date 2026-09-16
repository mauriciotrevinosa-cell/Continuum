# Continuum — Current Chat Handoff

**Purpose:** Fast continuation context for a new ChatGPT conversation when the previous thread drifts or reaches its limit.
**Updated:** 2026-09-16
**Current implementation branch:** `m3/critical-path`

## 1. Product identity

```text
CONTINUUM = app / creative studio / engine
THE ARRIVALS = flagship project inside Continuum
```

Continuum must remain generic; The Arrivals is the current production target.

## 2. Working style / constraints

- Default language: Spanish.
- Prefer root-cause fixes over patches.
- Preserve meaningful work in Git.
- Keep commits small and auditable.
- Do not recommend Cline right now: the available ClinePass/free-model route was exhausted/unreliable in this session.
- Claude/Work are intended for later refinement, but current goal is to reach real visual production first.
- The GitHub connector available to ChatGPT in this project has been used to write commits directly to the repo. Do not incorrectly claim GitHub is read-only when write actions are available.

## 3. Current M3 goal

Reach a real, inspectable 16-page non-canon production calibration run for The Arrivals, then use visual review/correction to stabilize the pipeline before official manga production.

Target loop:

```text
load committed Chapter Test
→ resolve cast / wardrobe / environment / continuity
→ render candidate page
→ creator visually reviews
→ regenerate / correct
→ approve calibration
→ begin official manga
```

UI polish and deeper architecture cleanup are secondary until this loop works.

## 4. Chapter Test state

The dedicated Chapter Test UI exists in:

`The Arrivals → Manga production`

It shows:
- calibration package selector
- page backend selector
- `Start Chapter Test`

The package is the committed 16-page non-canon calibration chapter.

Important verified behavior:
- calibration uses its own run purpose (`CALIBRATION`)
- approved calibration pages do not join story continuity
- page-specific wardrobe stages are carried into production bundles
- Chapter Test is isolated from official canon continuity

Focused acceptance test was repaired and passed locally:

```text
uv run --no-sync pytest tests/acceptance/test_m3_calibration.py -q
.... [100%]
```

## 5. Current immediate runtime problem

The creator clicked `Start Chapter Test` in the UI and received:

```text
The request failed (500).
```

This is the immediate blocker to debug next.

Do not guess the cause. Reproduce the click while `continuum-api` is visible and inspect the API traceback.

## 6. ComfyUI state

The repo now contains implementation support for BOTH local and opportunistic free remote GPU ComfyUI.

### Endpoint configurator

Commit:
`988f64788008b86317be3e8b19f3283951214465`
`feat(m3): add ComfyUI endpoint configurator`

File:
`scripts/configure_comfy.py`

It writes only `CONTINUUM_COMFY_*` keys to local `.env` and supports:
- local URL
- remote URL
- checkpoint name/version/SHA/license/source
- timeout
- remote source-excerpt policy

### Local ComfyUI bootstrap

Commit:
`fc28f4094001239c90efef3d960b2632daea713d`
`feat(m3): add local ComfyUI bootstrap`

File:
`scripts/setup_comfy_local.ps1`

It can install ComfyUI, install `ComfyUI_IPAdapter_plus`, download a creator-selected checkpoint / IP-Adapter / CLIP Vision files, configure Continuum, and optionally start ComfyUI on `127.0.0.1:8188`.

### Free remote GPU bootstrap

Commit:
`f8a7a4eb8f78bf506a3c42d0c0557ecc0a3778e5`
`feat(m3): add opportunistic free-GPU ComfyUI bootstrap`

File:
`scripts/setup_comfy_free_gpu.py`

Primary intended use: an interactive free GPU notebook session such as Kaggle. It:
- requires an actual NVIDIA GPU runtime unless explicitly overridden
- installs ComfyUI and IP-Adapter node support
- downloads the selected model files
- starts ComfyUI
- exposes it via a temporary Cloudflare Quick Tunnel
- prints the exact Windows command for configuring `COMFY_REMOTE`

The remote session is intentionally opportunistic, not a permanent dependency.

### Important runtime truth

These scripts are committed, but the user's local machine / notebook still has to run them and provide real checkpoint URLs/metadata. Git cannot start the user's local GPU process or allocate a Kaggle/Colab GPU by itself.

The current UI previously showed:
- TEST reachable
- COMFY_LOCAL not configured
- COMFY_REMOTE not configured

## 7. Character Vault / duplicate state

A bad earlier test run polluted the real `continuum` DB with duplicate test characters (for example multiple `Frieren` entries with source `Invented Almanac`). These rows live in local PostgreSQL, not Git.

A safe audit / soft-retirement tool is now committed:

Commit:
`c89a5c9dbaabd150cec0df96fea15c5d87aa8780`
`fix(m3): add safe duplicate character retirement tool`

File:
`scripts/audit_character_duplicates.py`

It is dry-run by default and can retire only an exact source label inside duplicate-name groups. It does not delete Source Vault/reference bytes.

Suggested safe sequence later:

```powershell
cd C:\Continuum
uv run --no-sync python scripts/audit_character_duplicates.py
uv run --no-sync python scripts/audit_character_duplicates.py --retire-source-label "Invented Almanac"
# Only after reviewing the dry-run output:
uv run --no-sync python scripts/audit_character_duplicates.py --retire-source-label "Invented Almanac" --apply
```

Do not delete duplicates blindly.

## 8. Calibration cast / quick Character Vault bootstrap

A committed operational roster now exists for the full calibration cast:

Commit:
`8743a4d1bf5ce440ae20a76e2d02798d6670625a`
`story: add The Arrivals calibration cast roster`

File:
`docs/creative/THE_ARRIVALS_CALIBRATION_CAST_v0.1.json`

It includes:
- Core 9: Frieren, Fern, Mau, Bocchi, Yuta, Rimuru, Maomao, Momo, Anko
- G3: Mikasa, Okarun, Umaru, Kita, Coco, Qifrey, Wakana, Marin
- antagonist: Sukuna
- source labels / aliases
- calibration page mappings
- existing profile IDs for known Frieren/Fern/Mau profiles

A conservative bootstrap script exists:

Commit:
`6554df7b258ffaa2c71c0d4b7c1d4be1a6750e98`
`feat(m3): add calibration cast bootstrap`

File:
`scripts/bootstrap_calibration_cast.py`

It creates only missing Character Vault profile shells and refuses ambiguous duplicates. It does NOT auto-approve visual references, outfits, candidates, or Production Models.

A lightweight calibration character pack is also committed and currently expanded:

Latest commit before this handoff:
`3008e1372c72ed8fa13ed3c96aa2a50707e05e85`
`docs: expand character vault calibration pack for chapter test`

File:
`docs/creative/characters/THE_ARRIVALS_CHARACTER_VAULT_CALIBRATION_PACK_v0.1.md`

This is deliberately minimum viable grounding for testing, not the final character-quality pass. Claude/Work can later refine actual Vault evidence and Production Models.

## 9. Known real Character Vault quality

Do not confuse profile existence with strong visual grounding.

Known historical state:
- Mau has the strongest real profile among current core characters.
- Frieren has limited confirmed evidence (historically one strong anchor plus many candidates).
- Fern is sparse.
- many other calibration characters may have shells but weak/no reviewed visual evidence.

The Source Vault is local and is not stored in Git, so Git can carry roster/configuration/design docs but cannot magically contain all local media evidence.

## 10. Creative state that must remain visible

The Arrivals project now has an `Ideas & future beats` view for approved/provisional ideas that are important but not yet episode-locked.

Preserved future direction includes:
- Mau/Frieren endgame romance
- Himmel teaches Frieren what love means; Mau is her first consciously recognized romantic love
- Sukuna impales/kills Mau during the major S2 arc under a false-binary choice
- Second Chance / divine reanchor direction
- Yuta completes recovery with RCT over roughly two days
- Frieren remains by Mau and later confesses after he wakes
- kiss / reciprocation
- post-revival argument/promise about not deciding alone / no secrets
- Hollow Purple secrecy / one-use reconstruction direction

Do not force these beats into fixed episode numbers unless explicitly locked later.

## 11. Local startup routine

Docker Desktop must be open first because PostgreSQL runs there.

Then use three terminals:

### API
```powershell
cd C:\Continuum
uv run --no-sync continuum-api
```

### Worker
```powershell
cd C:\Continuum
uv run --no-sync continuum-worker
```

### Web
```powershell
cd C:\Continuum\apps\web
corepack pnpm build
corepack pnpm exec next start -p 3001
```

Open:

`http://127.0.0.1:3001`

Avoid intentionally using the old `C:\Continuum-Phase0-Final\.venv`; `uv run` from `C:\Continuum` should target the project environment.

## 12. Git state / continuation rule

Implementation branch:

`m3/critical-path`

Before local testing in a new chat/session:

```powershell
cd C:\Continuum
git status
git pull origin m3/critical-path
```

Creative project source branch previously used by The Arrivals UI:

`creative/s1-season-board-v0.1`

The UI may require `Resync from Git` for project creative docs after creative-branch changes.

## 13. Immediate next actions

Do these in order; do not wander into broad refactors first.

1. Pull latest `m3/critical-path`.
2. Reproduce the `Start Chapter Test` 500 and capture the API traceback.
3. Fix only the real 500 root cause; commit/push the fix.
4. Run duplicate-character audit and safely retire known `Invented Almanac` pollution after reviewing dry run.
5. Run calibration-cast bootstrap dry run; create only genuinely missing shells.
6. Configure one real Comfy backend:
   - local if usable, and/or
   - free remote GPU session (Kaggle-style) using the committed bootstrap.
7. Restart API/worker and verify backend becomes READY in Manga production.
8. Start the 16-page Chapter Test and inspect READY/BLOCKED page logic.
9. Generate real visual candidates and iterate page by page.
10. Only after calibration is visually credible, begin official manga production.

## 14. Suggested first message for the next ChatGPT conversation

> Continue Continuum from `docs/CONTINUUM_CHAT_HANDOFF_CURRENT.md` on branch `m3/critical-path`. Read that file first and verify the current remote HEAD before changing anything. We are at M3 Chapter Test calibration. The UI exists, calibration acceptance tests passed, Comfy local + opportunistic free-GPU bootstrap scripts and Character Vault/duplicate tools are already committed. The immediate blocker is that clicking **Start Chapter Test** returned HTTP 500. Do not repeat old setup advice, do not recommend Cline, and do not redesign unrelated UI. First inspect the repo/current branch, then help me reproduce and fix the 500 from the API traceback. After that, clean known `Invented Almanac` duplicate characters safely, bootstrap any missing calibration cast shells, configure a real Comfy backend, and run the 16-page visual Chapter Test. Preserve fixes in Git with small auditable commits.
