# Continuum — Product / Project Model v0.2

**Status:** Approved product-direction amendment  
**Date:** 2026-09-10  
**Supersedes:** `CONTINUUM_PRODUCT_PROJECT_MODEL_v0.1.md`

## 1. Core identity

Continuum and The Arrivals are permanently separate concepts:

```text
CONTINUUM = APP / CREATIVE STUDIO / ENGINE
THE ARRIVALS = ONE PROJECT CREATED INSIDE CONTINUUM
```

The Arrivals remains the flagship personal project and continues to be developed. This separation does **not** reduce its importance. It prevents Continuum from becoming hardcoded around one story.

A clean Continuum installation must work with zero knowledge of The Arrivals.

## 2. User-level Library, project-level continuity

The Library/Vault belongs to the user, not to any single project.

```text
USER LIBRARY
├── Frieren
├── Chainsaw Man
├── Chainsmoker Cat
└── anything else the user wants

PROJECTS
├── The Arrivals              -> selects some Library sources
├── Chainsaw Man Rewrite      -> may select one source
├── What If Project           -> selects another subset
└── Original Project          -> may use no franchise source at all
```

A source can exist in the Library simply because the user likes it. Library membership never implies inclusion in The Arrivals.

## 3. Project isolation

Each project owns its own:

- selected source set;
- source snapshots/cutoffs;
- project canon and overrides;
- branches;
- world state;
- timeline;
- relationships;
- character arrival/body/memory decisions;
- story plans, scripts and generated artifacts;
- project-specific corrections and approvals.

The same source character may therefore have different states in multiple projects without conflict.

Source Canon remains separate and must never be silently rewritten by project decisions.

## 4. The Arrivals is flagship, not default

The Arrivals remains a major project with its own MC/Avatar, Otherworlder conflict, dynamic worldbuilding pillars, civilization progression, arrival logic, power systems and long-form story direction.

Its data and creative decisions belong inside project-level data/documentation only.

A first-run Continuum experience should conceptually look like:

```text
Continuum

[ Create Project ]
[ Import Project ]

Library
No sources registered yet
```

The Arrivals appears only if the user creates/imports/opens it.

## 5. Multiple personal stories are first-class

Continuum must support projects such as:

- continuing one anime/manga after its ending;
- rewriting one disliked ending;
- exploring a What If branch;
- creating a crossover unrelated to The Arrivals;
- keeping a franchise in the Library with no project attached;
- adding a new franchise to a later season of an existing project and allowing that addition to materially change the world.

No project is required to use all Library sources.

## 6. Friends, messaging and project sharing direction

A future Continuum social layer should support optional account-based connections between users while preserving the local-first core.

Target UX concepts:

```text
Friends
├── Cousin
├── Friend A
└── Friend B

Chats
├── Cousin
└── Friend A

Shared with Me
├── Project from Cousin
└── What If from Friend A
```

Users should be able to:

- add/accept friends;
- chat directly inside Continuum;
- send a project or project snapshot to a friend;
- receive projects in `Shared with Me`;
- preview project metadata before importing;
- save/import a shared project as an independent local copy;
- fork or branch from a received project without modifying the sender's original;
- optionally send later project updates as new versions instead of silently overwriting a recipient's copy.

Project sharing should be designed as collaboration between independent local continuities, not as one mutable global database.

## 7. Shared project package model

A shared/exported project should conceptually contain:

```text
project metadata
project canon / overrides
branches
world state
timeline
relationships
character states
story documents / plans
source dependency references
user-created/generated artifacts where appropriate
```

Raw commercial source media must **not** be assumed to travel inside the project package. A recipient resolves source dependencies against their own Library.

Example:

```text
Mauricio sends: The Arrivals
        ↓
Cousin opens Shared with Me
        ↓
Continuum reports:
  31 source dependencies resolved
  7 source dependencies missing
        ↓
Cousin may still save/import the project
        ↓
Cousin creates their own branch/copy
```

## 8. Sharing permissions and safety direction

The future social layer should distinguish at least:

```text
VIEW / PREVIEW
SEND COPY
ALLOW FORK
COLLABORATE (future, if implemented)
```

Receiving a project must never grant access to unrelated local files, the sender's entire Library, or the sender's machine.

A shared project should expose only intentionally packaged project data and dependency references.

## 9. Local-first remains the default

Friends/chat/sharing are optional network features layered on top of a local-first application.

Continuum should remain useful when:

- offline;
- used by one person only;
- no account/social feature is configured;
- the user never shares a project.

The core creative workflow, Library, Reader, Source Intelligence and local project work must not require a permanent online service merely because social features exist.

## 10. Vault implications

`C:\ContinuumVault` is the current user's personal source-acquisition Vault, not a default global dataset.

The current 49-franchise scaffold is Mauricio's personal Library acquisition structure. It must never become seed data or runtime assumptions.

Another user may have 0, 3, 50 or hundreds of sources.

Continuum must discover/register what actually exists and support incremental additions.

## 11. Phase implications

This product separation clarifies, but does not discard, the approved engineering phase sequence.

- Phase 1: user-level Library/Vault.
- Phase 2+: Reader/Source Intelligence operate on Library sources independent of any story.
- Phase 5: Source Canon remains distinct from project use.
- Phase 6: isolated Projects/Branches/Worlds select from the Library.
- Later phases: project import/export/share.
- Friends/chat/Shared with Me are future product features and must not be allowed to derail foundational local functionality.

## 12. Product invariants

```text
SOURCE EXISTS IN LIBRARY
    != SOURCE IS USED BY A PROJECT

PROJECT USES A SOURCE
    != SOURCE CANON IS REWRITTEN

THE ARRIVALS EXISTS
    != CONTINUUM REQUIRES THE ARRIVALS

PROJECT IS SHARED
    != RAW SOURCE MEDIA IS SHARED

SOCIAL FEATURES EXIST
    != CONTINUUM REQUIRES THE CLOUD
```

This is the intended product model going forward.