# Continuum — Acquisition Tooling v0.1

**Status:** Active personal-workflow documentation  
**Date:** 2026-09-10  
**Scope:** Mauricio's local acquisition helper workflow around `C:\ContinuumVault`

This document records the current external tooling and acquisition-state decisions discovered while filling Mauricio's personal Library. It is not runtime architecture and must not become generic seed data.

## Core separation

```text
C:\Continuum                = application repository
C:\ContinuumData            = derived/application data
C:\ContinuumVault           = raw personal source media
C:\ContinuumTools           = external helper tools
C:\ContinuumIntake          = acquisition staging/intake
```

The Vault remains outside Git and raw source media is not committed to the repository.

## HaruNeko status

HaruNeko is installed only as an **external acquisition helper**. It is not a Continuum runtime dependency.

Current local layout reported by the acquisition audit:

```text
C:\ContinuumTools\HaruNeko\installers\
C:\ContinuumTools\HaruNeko\app\
C:\ContinuumTools\HaruNeko\userdata\
C:\ContinuumIntake\HaruNeko\
```

The installed Electron shell is v44.1.1. User settings/bookmarks were moved to a stable `userdata` location so application updates do not silently replace them.

The user must manually set HaruNeko's download directory to:

```text
C:\ContinuumIntake\HaruNeko
```

HaruNeko output must not go directly into `C:\ContinuumVault`; intake is inspected/classified first.

## Acquisition tooling

Local helper tooling currently exists outside the repo under:

```text
C:\ContinuumTools\acquisition\
```

with personal acquisition state under:

```text
C:\ContinuumData\acquisition\
```

Reported generated data includes a work catalog, acquisition queue, Vault coverage report, and update-watch state.

The intake importer is intended to be non-destructive:

- never overwrite an existing raw file;
- preserve both files when names collide but contents differ;
- avoid unnecessary duplicate copies when content is byte-identical;
- leave existing Vault originals untouched;
- default to dry-run before applying imports.

These local tools are helper tooling only and are not yet Continuum Phase 1 runtime features.

## Current acquisition state from audit

The latest local audit reported:

- 48 source-family roots detected;
- 10 acquired works checked as complete by the local coverage tooling;
- no raw media changed by the HaruNeko/tooling setup session;
- no files imported yet through the new intake workflow;
- Tensura main manga acquired, with selected spin-offs still pending.

Coverage results are useful acquisition metadata but do not substitute for later Continuum Source Intelligence/provenance checks.

## Naming / catalog corrections

### That Time I Got Reincarnated as a Slime: Clayman's Revenge

Keep the English work name as:

```text
That Time I Got Reincarnated as a Slime: Clayman's Revenge
```

Kodansha/K MANGA uses **Clayman's Revenge** in English. Do not rename the documented work to `Clayman Revenge` merely because the Japanese title romanization contains `Clayman REVENGE`.

### Li'l Miss Vampire Can't Suck Right

Use the official Yen Press English spelling:

```text
Li'l Miss Vampire Can't Suck Right
```

The older `Lil'` spelling in personal documentation may be normalized later where convenient; this does not require destructive Vault renaming.

### My Ribdiculous Reincarnation

Do not treat this as a normal active manga-acquisition target yet.

As of this documentation date, a manga adaptation has been announced and a first manga chapter was included with the April 2026 new edition of the light novel, but there is not yet a normal ongoing manga source comparable to the other entries in the acquisition pass.

Therefore:

```text
manga acquisition status = BLOCKED / NOT NORMALLY AVAILABLE YET
```

The source family itself remains in Mauricio's Library acquisition pool. Light-novel/web-novel/anime handling belongs to the appropriate later source passes.

## Source legality / authorization boundary

External acquisition tools may only automate downloads where the user is authorized to obtain the material from the selected source.

Do not bypass DRM, authentication, paywalls, access controls, or anti-bot protections.

Source availability and acquisition authorization are separate from Continuum's ingestion architecture.

## Forward direction

The long-term product should own a first-class intake/update workflow roughly like:

```text
authorized source acquisition
→ intake
→ hash / inspect / classify
→ proposed destination
→ approval
→ immutable raw Vault import
→ Source Intelligence update
```

This document records the current external-helper workflow only. It does not pull Phase 1/3 functionality forward prematurely.
