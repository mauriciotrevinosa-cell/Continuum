# Continuum — Product / Project Model v0.1

**Status:** Approved product-direction amendment  
**Date:** 2026-09-10  
**Scope:** Product identity, Library/Vault ownership, project isolation, project sharing

## 1. Core separation

Continuum and The Arrivals are not the same thing.

```text
CONTINUUM = APP / CREATIVE STUDIO / ENGINE
THE ARRIVALS = ONE PROJECT CREATED INSIDE CONTINUUM
```

The Arrivals remains the flagship personal project and is not abandoned. It continues to use the creative direction documented under `docs/creative/`.

Continuum itself must remain project-agnostic. No runtime code, migrations, fixtures, Library logic, project creation flow, or UI shell may assume that The Arrivals exists or that a user wants a crossover.

## 2. Library is user-level, not project-level

A user's Library/Vault may contain any source material the user wants to preserve or work with, including franchises that are not used by The Arrivals or by any current project.

Examples:

- a franchise may exist only because the user likes it and wants it indexed;
- a user may create a single-franchise continuation or alternate ending;
- a user may create a crossover unrelated to The Arrivals;
- a user may add a new source later without forcing it into any existing story.

```text
USER VAULT / LIBRARY
        ↓
contains reusable source knowledge
        ↓
PROJECT A selects a subset
PROJECT B selects a different subset
PROJECT C may select only one franchise
```

Library membership never implies project membership.

## 3. Projects are isolated creative continuities

Each project owns its own:

- selected source set;
- source snapshots/cutoffs used by that project;
- project canon and overrides;
- branches;
- world state;
- timeline;
- relationships;
- character arrival/body/memory decisions;
- story plans and scripts;
- generated artifacts and approvals;
- project-specific corrections that should not silently rewrite Source Canon.

The same source character may therefore have different project states in different projects without conflict.

Example:

```text
Library: Chainsaw Man

Project: The Arrivals
→ uses selected characters and Continuum-specific continuity

Project: Chainsaw Man Alternate Ending
→ single-franchise branch with different project canon
```

## 4. The Arrivals remains special only as a project

The Arrivals remains an actively developed flagship project with its own MC/Avatar, worldbuilding, Otherworlder conflict, civilization progression, dynamic pillars, arrival logic, and long-form story direction.

Its importance must not leak into generic Continuum behavior.

A fresh Continuum installation should not open directly into The Arrivals and should not require its franchise pool.

A clean first-run experience should conceptually be:

```text
Continuum

[ Create Project ]
[ Import Project ]

Library
No sources registered yet
```

The Arrivals appears only when the user creates/imports/opens that project.

## 5. Multiple personal stories are a first-class use case

The user may keep sources in Continuum simply for personal interest and create additional independent projects at any time.

Examples include:

- changing the ending of one anime/manga;
- continuing a completed story;
- exploring a What If branch;
- creating a crossover with a completely different source set;
- keeping a source such as Chainsmoker Cat in the Library without involving it in The Arrivals;
- later adding a new franchise to an existing project and allowing that addition to materially change the project's world.

No project is required to use all Library sources.

## 6. Project sharing / import-export direction

Continuum should eventually support sharing projects between users/installations.

The target model is:

```text
Export Project
→ project state + canon decisions + branches + timelines + relationships
→ story documents / plans
→ project metadata and source dependency references
→ optionally user-created/generated artifacts where appropriate

Import Project
→ create an independent local copy
→ resolve referenced sources against recipient's own Library
→ clearly report missing source dependencies
→ never silently alter the sender's project
```

Raw commercial source media should not be assumed to travel inside a shared project package. A recipient can connect their own legitimately held copies of the required sources.

Project sharing should support independent forks: a recipient may import another person's project and create their own branch/version without changing the original.

## 7. Vault and portability implications

`C:\ContinuumVault` is the current user's physical acquisition Vault, not an app-global or mandatory franchise set.

The current 49-folder scaffold is Mauricio's personal acquisition structure. It must never become hardcoded seed data.

Another user may have:

- 0 franchises;
- 3 franchises;
- 49 different franchises;
- hundreds of sources.

Continuum should scan/register what actually exists and allow incremental additions later.

## 8. Phase implications

This amendment does not change the approved engineering phase order. It clarifies responsibilities inside those phases.

- Phase 1 Library/Vault: user-level reusable source catalog, independent of projects.
- Phase 2+ Reader/Source Intelligence: operate on Library sources without assuming any story.
- Phase 5 Character/Canon: preserve Source Canon separately from project use.
- Phase 6 Project/Branch/World: introduce isolated projects that select Library sources.
- Later project export/import/share: build on versioned project state and source dependency references.

The Arrivals content belongs in project data/creative documentation, never in generic application defaults.

## 9. Product invariant

```text
SOURCE EXISTS IN LIBRARY
    ≠ SOURCE IS USED BY A PROJECT

PROJECT USES A SOURCE
    ≠ SOURCE CANON IS REWRITTEN

THE ARRIVALS EXISTS
    ≠ CONTINUUM REQUIRES THE ARRIVALS
```

This separation is now the intended product model for Continuum.
