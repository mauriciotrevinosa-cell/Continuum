# PROJECT CONTINUUM
## Master Build Specification v0.3 — Local-First Living Multiverse Studio

**Status:** v0.3 consolidated architecture / implementation handoff  
**Primary goal:** Build a local-first creative system that can ingest user-supplied manga, anime, light novels, notes, art references, and original material into a structured universe library, then help create canon-aware continuations, alternate endings, crossovers, new stories, manga scripts, storyboards, and anime adaptation plans.

**v0.3 authority rule:** When an older section conflicts with a later v0.2 addendum or the v0.3 consolidation sections at the end of this document, the **latest section wins**. In particular, `/source-vault` is the canonical immutable source path, local/free operation is the default production profile, durable resumable jobs are a foundation invariant, and character/project continuity is never collapsed into source canon.

**v0.3 major additions:** durable Production Job Manager; hardware-agnostic execution; local/$0-first provider policy; Source Intelligence + Character Brain + Craft/Director Vault; Character Vault/Cast Pool semantics; Story Calendar and slow-burn pacing support; Civilization/Institution history; Visual Lab; production approval gates; recipe/manifests and remasterability; expanded Director UI; revised implementation order.

---

# 1. PRODUCT VISION

Project Continuum is not a generic fan-fiction chatbot.

It is a **personal fictional-universe studio** with five major capabilities:

1. **Library** — ingest and understand source material.
2. **Canon Engine** — represent characters, events, relationships, lore, timelines, power systems, mysteries, visual rules, and performance rules.
3. **Story Engine** — continue, branch, rewrite, merge, or reinvent universes while preserving continuity.
4. **Production Engine** — turn stories into chapters, manga scripts, page/panel plans, episode scripts, storyboards, shot lists, and eventually visual/audio assets.
5. **Director UI** — let the user control the project at every level instead of relying on giant prompts.

The long-term experience should feel like directing a private fictional studio.

---

# 2. CORE PRODUCT PRINCIPLES

## 2.1 Source material is immutable

Never modify files under `/source-vault`.

All extraction, metadata, embeddings, transcripts, thumbnails, indexes, and derived data go under `/library`, `/cache`, or the database.

## 2.2 Canon and generated continuity are separate

Imported source material represents canon.

Every user-created story is a **branch** from canon.

A generated chapter must never silently alter the source canon database.

## 2.3 Provenance everywhere

Every extracted fact should record where it came from when practical:

- series
- medium
- volume/chapter/episode
- page or timestamp
- source asset ID
- extraction confidence
- whether confirmed manually

The system must distinguish:

- explicit canon
- inferred canon
- user-defined canon
- generated continuity
- uncertain information

## 2.4 Human director remains in control

The system proposes.

The user approves, rejects, edits, branches, locks, or regenerates.

Do not silently rewrite major story decisions.

## 2.5 Model-agnostic architecture

Do not hard-wire the application to one LLM, image model, speech model, or embedding provider.

Use provider interfaces.

Example:

```python
class TextModelProvider:
    async def generate(...)
    async def generate_structured(...)

class EmbeddingProvider:
    async def embed_text(...)
    async def embed_image(...)

class ImageProvider:
    async def generate(...)
    async def edit(...)

class SpeechProvider:
    async def synthesize(...)
```

## 2.6 Local-first

The system should run locally with local media and a local database.

Cloud APIs are optional providers.

The user must be able to browse their library even if external AI providers are unavailable.

## 2.7 Reproducibility

Every generation should record:

- model/provider
- prompt template version
- retrieved context IDs
- temperature/settings when available
- user instruction
- parent draft/version
- timestamp
- output

This allows story versions to be compared and reproduced.

## 2.8 Rights-aware media generation

The tool can analyze user-supplied reference media for creative organization and private transformation.

For generated audio, distinguish between:

- generic/original synthetic character voices
- user-authorized custom voices
- third-party performer voice likenesses

Do not make exact third-party voice cloning the default pipeline. Keep voice generation behind a provider/authorization layer so authorized models can be plugged in later.

---

# 3. HIGH-LEVEL ARCHITECTURE

Use a monorepo.

```text
continuum/
├── apps/
│   ├── web/                  # Next.js / React director UI
│   └── api/                  # FastAPI application
│
├── packages/
│   ├── schemas/              # shared JSON schemas / types
│   ├── prompts/              # versioned prompt templates
│   ├── providers/            # LLM/image/audio provider abstractions
│   └── ui/                   # shared UI components
│
├── workers/
│   ├── ingest/
│   ├── media/
│   ├── extraction/
│   ├── embeddings/
│   └── generation/
│
├── source-vault/             # USER SOURCE MATERIAL — READ ONLY
│   ├── franchises/
│   └── original/
│
├── library/                  # derived persistent library artifacts
│   ├── franchises/
│   ├── indexes/
│   ├── thumbnails/
│   ├── transcripts/
│   ├── audio_segments/
│   └── visual_refs/
│
├── projects/                 # optional human-readable project exports
│
├── cache/                    # disposable generated cache
│
├── migrations/
├── scripts/
├── tests/
├── docker/
│
├── AGENTS.md
├── .env.example
├── docker-compose.yml
├── README.md
└── pyproject.toml
```

---

# 4. RECOMMENDED TECH STACK

## Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- component library such as shadcn/ui
- TanStack Query
- Zustand or equivalent lightweight local UI state
- React Flow for timeline / relationship / knowledge graphs
- a rich text editor only when needed; story content itself should remain structured

## Backend

- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy / SQLModel
- Alembic migrations
- PostgreSQL
- pgvector for initial vector search
- Redis for jobs/cache if background worker architecture is enabled
- a simple task queue first; Temporal can be considered later if workflows become complex

## Media

- FFmpeg
- ffprobe
- faster-whisper or provider abstraction for transcription
- optional Demucs-style source separation
- scene/shot boundary detection
- image thumbnail/keyframe extraction
- audio VAD / diarization via pluggable provider
- perceptual hashes for duplicate detection

## Storage

Start with filesystem + PostgreSQL.

Do not begin with an unnecessarily complex object store.

Add S3-compatible storage only when needed.

## Search

Use hybrid retrieval:

- PostgreSQL full-text search
- pgvector similarity search
- structured filters
- graph/entity relationships

Do NOT depend entirely on vectors.

---

# 5. SOURCE FOLDER CONVENTION

The app should support both a recommended layout and loose-file discovery.

Recommended:

```text
source-vault/
├── franchises/
│   ├── dandadan/
│   │   ├── franchise.yaml
│   │   ├── manga/
│   │   ├── anime/
│   │   ├── light_novel/
│   │   ├── subtitles/
│   │   ├── audio/
│   │   ├── databooks/
│   │   ├── character_refs/
│   │   ├── official_art/
│   │   └── notes/
│   │
│   └── frieren/
│       └── ...
│
└── original/
    ├── characters/
    ├── worlds/
    ├── concepts/
    ├── designs/
    └── notes/
```

`franchise.yaml` example:

```yaml
id: frieren
title: Frieren
aliases:
  - Sousou no Frieren
language:
  primary: ja
user_notes: ""
sources:
  manga: true
  anime: true
  light_novel: false
```

The scanner must also handle files without this metadata and ask the user to classify ambiguous files.

---

# 6. FILE TYPES TO SUPPORT

## MVP

- `.txt`
- `.md`
- `.pdf`
- `.epub`
- `.cbz`
- `.cbr` if practical
- `.jpg/.jpeg/.png/.webp`
- `.mp4/.mkv/.mov`
- `.mp3/.wav/.flac`
- `.srt/.ass/.vtt`

## Later

- archive packages
- structured subtitle formats
- Blu-ray extras
- art-book collections
- user-created screenplay formats

---

# 7. INGESTION PIPELINE

Each asset follows an idempotent pipeline.

```text
DISCOVER
  ↓
FINGERPRINT
  ↓
CLASSIFY
  ↓
EXTRACT
  ↓
SEGMENT
  ↓
ANALYZE
  ↓
EMBED
  ↓
ENTITY/LINK EXTRACTION
  ↓
VALIDATE
  ↓
INDEX
```

## 7.1 Discover

Watch `/source-vault` and allow a manual **Scan Library** button.

Record:

- absolute/relative path
- file size
- modified time
- MIME
- franchise guess
- media type guess

## 7.2 Fingerprint

Create:

- SHA-256
- optional perceptual hash for images/video frames

If file hash already exists, do not ingest twice.

## 7.3 Classify

Determine:

- franchise
- medium
- volume/chapter/episode if detectable
- language
- canonical status
- user notes

Anything uncertain gets a review flag.

## 7.4 Extract

### Manga / comics

Extract:

- page images
- available embedded text
- panel candidates later
- OCR only when needed
- dialogue balloons later
- visual embeddings
- page-level metadata

### Light novels / EPUB/PDF

Extract:

- chapters
- paragraphs
- headings
- illustrations
- footnotes if useful

### Anime

Extract:

- video metadata
- subtitle tracks
- audio tracks
- keyframes
- shot boundaries
- episode segments
- dialogue timestamps
- optional transcription
- optional audio separation
- optional speaker diarization

### Notes

Treat user notes as high-authority project/library annotations but keep them distinguishable from source canon.

---

# 8. MULTIMODAL ANIME PIPELINE

Anime should become synchronized scene records, not a pile of screenshots.

## 8.1 Episode model

```text
Episode
├── metadata
├── scenes
│   ├── shots
│   │   ├── keyframes
│   │   └── visual descriptors
│   ├── dialogue
│   ├── music cues
│   ├── sound events
│   └── characters present
└── timeline
```

## 8.2 Scene segmentation

Combine:

- subtitle timing gaps
- shot changes
- audio transitions
- optional LLM scene-boundary reasoning

A scene can span multiple shots.

## 8.3 Dialogue alignment

Store:

- text
- language
- start/end timestamp
- speaker ID if known
- speaker candidates
- confidence
- emotion tags
- target/addressee if inferred
- source subtitle/transcript reference

## 8.4 Character voice/performance analysis

Build **performance profiles**, not just raw clips.

Possible attributes:

- speaking rate
- average utterance length
- pitch statistics
- energy
- pause behavior
- emotional intensity
- laugh/gasp/shout/whisper tags
- pronunciation notes
- interaction-specific tendencies

Store clips as references with timestamps.

Speaker identity must support manual correction.

The UI should let the user select a known character and confirm sample clips. Those become trusted anchors.

## 8.5 Visual analysis

For keyframes/scenes, derive:

- characters present
- costumes
- facial expressions
- pose
- location
- time of day
- shot type
- composition
- lighting
- color characteristics
- visual effects
- camera movement inference
- animation intensity

Do not pretend automated detection is always correct. Keep confidence scores and review queues.

---

# 9. CORE DATABASE ENTITIES

## Source layer

### Franchise
- id
- title
- aliases
- description

### SourceAsset
- id
- franchise_id
- type
- path
- checksum
- metadata
- ingest_status

### SourceSegment
Generic addressable source unit.

Examples:
- novel section
- manga page
- anime scene
- subtitle line
- audio clip

Fields:
- asset_id
- locator
- start/end
- text
- metadata
- embedding refs

---

# 10. CANON KNOWLEDGE MODEL

## Character

- canonical name
- aliases
- franchise
- age/time-dependent states
- appearance traits
- personality traits
- values
- motivations
- fears
- habits
- speech tendencies
- combat tendencies
- abilities
- important possessions
- source provenance

## CharacterVersion

A character changes through canon.

Example:

```text
Frieren@pre-Himmel
Frieren@Himmel-party
Frieren@current
Frieren@Project-Incursion-Chapter-34
```

Do not flatten a character into one timeless profile.

## Relationship

Use directed relationships.

```text
A -> B
trust
affection
fear
respect
resentment
dependency
romantic_interest
knowledge_depth
```

Include textual rationale + provenance.

## Location

- names
- hierarchy
- geography
- visual profile
- historical events
- controlling groups
- applicable rules

## Faction

- members
- goals
- ideology
- alliances
- conflicts

## Ability

- owner
- source power system
- mechanics
- costs
- limits
- counters
- observed feats
- uncertain claims

## PowerSystem

- energy/source
- acquisition
- activation
- cost
- scaling rules
- limitations
- interaction rules

## Item

- owner/history
- capabilities
- state
- location

## Event

- time/order
- participants
- location
- causes
- consequences
- facts revealed
- relationships changed
- source references

## CanonClaim

This is extremely important.

A CanonClaim is an atomic statement.

Example:

> Character A knows Character B survived Event C.

Fields:

- statement
- subject
- predicate
- object/value
- valid_from
- valid_to
- confidence
- status: explicit/inferred/user-defined
- provenance

This helps continuity validation.

---

# 11. TIMELINE ENGINE

Every franchise gets a canonical timeline.

Every project creates one or more branches.

```text
canon/frieren
        |
        +---- project/incursion/main
                   |
                   +---- alt/fern-destroys-artifact
                   |
                   +---- alt/okarun-takes-artifact
```

A branch references a parent event/state and stores only its changes.

Never duplicate entire universes for each branch.

---

# 12. PROJECT MODEL

A **Project** is a user-created story universe.

Fields:

- title
- description
- included franchises
- canon cutoff per franchise
- branch point
- story mode
- target format
- intended length
- rating/tone constraints
- canon strictness
- creative freedom
- visual strategy
- power-system strategy
- locked decisions
- user instructions

Story modes:

- Canon continuation
- Alternate ending
- Divergence
- What-if
- Crossover
- Fusion universe
- New story with selected existing characters
- Mostly original world with imported characters
- Fully original

---

# 13. STORY BIBLE

Each project has a generated but editable Story Bible.

Sections:

- premise
- themes
- tone
- rules
- cosmology
- crossover explanation
- timeline
- main cast
- supporting cast
- antagonists
- factions
- power interaction rules
- locations
- relationship map
- mystery ledger
- foreshadowing ledger
- unresolved threads
- visual bible
- performance bible
- prohibited outcomes
- locked canon facts

Every generated chapter queries this Bible.

---

# 14. STORY ENGINE — GENERATION HIERARCHY

Never jump directly from premise to 100 finished chapters.

Use hierarchy:

```text
PROJECT PREMISE
  ↓
SERIES/SAGA PLAN
  ↓
ARC PLAN
  ↓
CHAPTER PLAN
  ↓
SCENE PLAN
  ↓
DIALOGUE / ACTION DRAFT
  ↓
MANGA / SCREENPLAY FORMAT
  ↓
PRODUCTION PLAN
```

Each level can be:

- approved
- locked
- regenerated
- edited
- branched

---

# 15. SERIES PLANNER

Input:

- story bible
- target chapters
- target anime episodes if applicable
- desired ending
- must-have events
- forbidden events
- pacing preferences

Output:

```text
Saga 1 — Incursion
Chapters 1–18

Arc 1 — First Contact
Chapters 1–6

Arc 2 — False Explanation
Chapters 7–12

Arc 3 — Collapse
Chapters 13–18
```

Each arc contains:

- objective
- protagonist state
- antagonist pressure
- key revelations
- relationship developments
- setup/payoff obligations
- climax
- exit state

---

# 16. CHAPTER ENGINE

A chapter should be generated from a **Chapter Packet**.

Packet contents:

- approved arc goals
- current branch state
- character states
- relationship states
- who knows what
- unresolved threads
- relevant canon references
- relevant previous scenes
- foreshadowing obligations
- mystery constraints
- pacing target
- user instructions

Outputs:

1. chapter objective
2. beat sheet
3. scene list
4. continuity report
5. draft
6. post-chapter state delta

The user can approve the beat sheet before prose/script generation.

---

# 17. CHARACTER STATE ENGINE

Per project branch and chapter:

```text
CharacterState
- physical condition
- injuries
- location
- emotional state
- current goals
- beliefs
- secrets
- known information
- possessions
- active relationships
- current abilities
- status
```

Do not overwrite prior states.

Store deltas/events so history can be reconstructed.

---

# 18. KNOWLEDGE / SECRET ENGINE

Represent knowledge explicitly.

Example:

```text
Secret: Incursions are artificial.

Knows:
- Frieren
- Momo

Suspects:
- Fern

Does not know:
- Stark
- Okarun
```

Before generating dialogue, continuity validator checks whether a speaker is allowed to know each referenced fact.

---

# 19. RELATIONSHIP ENGINE

Relationships are directed and stateful.

Example metrics are optional and should support narrative notes:

```text
Frieren -> Fern
trust: 0.92
affection: 0.88
respect: 0.95
conflict: 0.10
```

Do not let numerical values replace narrative reasoning.

Each significant event can emit relationship deltas.

The UI should show a graph and history.

---

# 20. MYSTERY ENGINE

Each mystery:

- question
- actual answer
- characters who know
- audience knowledge target
- clue list
- red herrings
- planned reveal
- reveal dependencies

The planner uses it to avoid arbitrary late reveals.

---

# 21. FORESHADOWING ENGINE

A foreshadowing seed records:

- eventual payoff
- earliest allowed setup
- desired subtlety
- characters involved
- candidate insertion scenes
- how many reminders are acceptable
- status

The system should warn if a payoff occurs without enough setup or if foreshadowing is becoming too obvious.

---

# 22. CONTINUITY VALIDATOR

Run before a chapter becomes “approved”.

Checks:

- character cannot know unavailable information
- dead/missing character appears without explanation
- item location conflict
- unresolved injury ignored
- ability violates established rules
- timeline impossible
- relationship behavior contradicts locked development
- reveal happens too early
- contradiction with locked canon
- duplicate first meeting
- repeated revelation
- location/travel mismatch

Severity:

- ERROR
- WARNING
- STYLE NOTE

User may override a warning with rationale.

---

# 23. POWER SYSTEM MAPPER

Do not use simplistic numeric power levels as the sole mechanism.

Represent powers by dimensions:

- source
- activation
- cost
- range
- speed
- durability
- precision
- mental
- spiritual
- spatial
- temporal
- conceptual/reality
- known counters
- observed feats
- narrative constraints

For crossover projects, create **InteractionRules**.

Example:

```text
Rule:
Frieren-style mana can affect Dandadan spiritual entities.

Confidence:
User-defined / locked.

Exceptions:
...
```

The user can choose:

- systems remain separate
- partial interoperability
- common underlying origin
- story-engine proposal

---

# 24. RETRIEVAL ENGINE

Use multiple retrieval routes.

A generation query can retrieve:

1. structured canon facts
2. timeline state
3. character profiles
4. relationship state
5. recent project chapters
6. semantically similar source scenes
7. relevant visual scenes
8. performance references
9. user notes

Rank by:

- project relevance
- branch validity
- character relevance
- recency
- provenance quality
- semantic score

Do not dump huge quantities of source text into prompts.

Retrieve compact facts and short source snippets only when needed.

---

# 25. STYLE / NARRATIVE DNA

Do not model style as “copy Author X”.

Extract high-level traits:

- pacing
- scene length
- dialogue density
- humor cadence
- emotional explicitness
- flashback frequency
- action-to-dialogue ratio
- mystery density
- chapter cliffhanger frequency
- tonal transitions
- narration distance
- recurring scene structures

Allow a project mix:

```text
Narrative Profile
- contemplative fantasy: 35
- supernatural chaos: 30
- original mythology: 20
- character comedy: 15
```

These are creative controls, not claims of exact stylistic imitation.

---

# 26. VISUAL BIBLE

For each franchise/era/character, model high-level visual characteristics:

- proportions
- silhouette
- costume vocabulary
- line characteristics
- background density
- lighting tendencies
- color tendencies
- effects language
- expression range
- shot/composition patterns
- animation intensity
- typography/card conventions

A crossover project can define visual behavior per universe.

Example:

```text
When characters first cross universes:
- preserve native design language
- adapt environment rendering
- gradually introduce hybrid effects
```

---

# 27. MANGA PRODUCTION MODE

Story chapter -> manga package.

Outputs:

## Chapter metadata
- title
- page target
- pacing target

## Page plan

```text
Page 1
Splash / establishing

Page 2
Panel 1 ...
Panel 2 ...
Panel 3 ...
```

## Panel schema

- panel number
- shot
- characters
- pose/expression
- action
- environment
- camera
- dialogue
- SFX
- visual emphasis
- continuity references

Later, panel plans can feed image generation.

---

# 28. ANIME ADAPTATION ENGINE

Do not use a fixed chapters-per-episode ratio.

Estimate runtime by scene content.

Consider:

- dialogue volume
- action
- establishing shots
- emotional pauses
- transformations
- recaps
- OP/ED
- anime-original extensions

Episode output:

```text
Episode 07
Target runtime: 23:40

00:00 Cold open
01:25 OP
02:55 Scene A
...
22:10 ED
```

Adaptation presets:

- faithful
- cinematic
- fast
- expanded
- director cut

Track chapter coverage.

---

# 29. STORYBOARD / SHOT ENGINE

For animated adaptation:

Scene -> shots.

Each shot:

- duration target
- framing
- camera angle
- camera movement
- characters
- blocking
- expression
- background
- dialogue
- SFX
- music cue
- transition
- keyframe notes

This becomes the bridge into future image/video tools.

---

# 30. AUDIO / PERFORMANCE ENGINE

Separate **performance direction** from **voice synthesis**.

Performance profile:

- cadence
- intensity
- pause patterns
- emotional tendencies
- interaction-specific behavior
- example source timestamps

Generated line direction:

```text
Character: ...
Emotion: quiet concern
Intensity: 0.22
Tempo: slow
Subtext: ...
Speaking to: ...
Reference performance tags: ...
```

Voice provider layer can later synthesize with an original/authorized voice.

---

# 31. MUSIC / SFX LAYER — LATER

Index:

- scene mood
- music start/end
- instrumentation descriptors
- intensity
- silence use
- recurring motifs
- SFX classes

For generated episodes, initially output **music direction**, not copyrighted soundtrack reproduction.

---

# 32. DIRECTOR UI

Primary navigation:

```text
Library
Projects
Characters
Worlds
Timeline
Studio
Jobs
Settings
```

## Library

- franchise cards
- ingestion status
- assets
- characters
- episodes
- chapters
- scenes
- review queue

## Project dashboard

- story bible
- cast
- timeline
- arcs
- chapters
- mysteries
- relationships
- production

## Director

Chat-like interface plus structured controls.

Commands can include:

- “Make the next three chapters more tense.”
- “Do not change Fern’s subplot.”
- “Give me four possible cliffhangers.”
- “Use option 3 and recalculate downstream consequences.”
- “Branch before Chapter 24.”
- “Show what breaks if Character X survives.”

The AI should return proposed changes as diffs where possible.

---

# 33. LIBRARY UI

Franchise detail should show something like:

```text
FRIEREN

Assets              210
Characters           48
Locations            96
Indexed scenes     6,281
Relationships       174
Abilities           213
Canon claims      8,920
Voice profiles       31
Review items         42
```

Everything should be clickable.

---

# 34. REVIEW QUEUE

Automation will make mistakes.

Create one unified queue for uncertain extraction:

- unknown speaker
- uncertain character match
- contradictory canon claim
- ambiguous episode/chapter metadata
- low-confidence OCR
- duplicate character/entity
- timeline ambiguity

User correction becomes training/context for future extraction.

---

# 35. STORY VERSION CONTROL

Conceptually Git-like, but do not require users to know Git.

Actions:

- checkpoint
- branch
- compare
- restore
- merge selected decisions
- lock event

Example:

```text
main
└── chapter-38
    ├── fern-destroys-artifact
    ├── okarun-takes-artifact
    └── artifact-activates
```

Show consequences of each branch before committing when practical.

---

# 36. BUTTERFLY EFFECT / CONSEQUENCE ANALYZER

Input:

> “Himmel survives.”

Output categories:

- immediate contradictions
- character-development consequences
- relationship consequences
- plot motivations lost
- future events invalidated
- new opportunities
- uncertainty

Allow:

**Create Branch From This Change**

Then generate a proposed revised timeline.

---

# 37. PROVIDER LAYER

Configuration example:

```yaml
providers:
  text:
    planning: openai
    drafting: anthropic
    extraction: openai
  embeddings:
    text: local_or_cloud
    image: local_or_cloud
  transcription:
    provider: local
  image:
    provider: configured
  speech:
    provider: configured
```

The product must work if only one text provider is configured.

---

# 38. PROMPT SYSTEM

Never scatter giant prompt strings across the codebase.

Store versioned prompts:

```text
packages/prompts/
├── extract_character_v1.md
├── extract_event_v1.md
├── chapter_plan_v1.md
├── continuity_review_v1.md
├── narrative_dna_v1.md
└── scene_draft_v1.md
```

Structured outputs must use Pydantic/JSON schemas.

Persist prompt version with every run.

---

# 39. OBSERVABILITY

Create a generation log UI.

Each run:

- task
- provider
- model
- duration
- token/usage data when provided
- retrieved records
- prompt version
- parse success
- retry count
- cost estimate when available
- user rating

This becomes essential once thousands of extraction jobs exist.

---

# 40. SECURITY / PRIVACY

- source-vault is read-only from application logic
- path allowlist
- prevent arbitrary filesystem traversal
- API keys only in environment or secure local credential store
- redact keys from logs
- provider upload must be explicit/configurable
- support “local-only franchise” flag
- generated files stored separately

---

# 41. BACKUPS

Backup:

- PostgreSQL
- project metadata
- user corrections
- story branches
- prompt configs

Do not need to back up disposable caches if the original source still exists.

---

# 42. TESTING STRATEGY

## Unit tests

- parsers
- provenance
- timeline math
- branch state
- relationship deltas
- provider adapters
- schema validation

## Integration

- ingest sample EPUB
- ingest sample CBZ
- ingest sample MP4 + subtitle
- rerun ingestion idempotently
- generate structured character record
- branch story and verify canon untouched

## Golden tests

Maintain tiny synthetic fictional source material created specifically for tests.

Do not base automated tests on a real copyrighted franchise.

Test that known facts are extracted and continuity errors are caught.

---

# 43. DEVELOPMENT PHASES

## PHASE 0 — Foundation

Goal: bootable monorepo.

Build:

- repository
- Docker/dev environment
- FastAPI
- Next.js
- PostgreSQL + pgvector
- migrations
- provider interfaces
- config system
- health checks
- basic tests
- CI
- AGENTS.md

Exit criteria:

- one command starts app/database
- frontend can call backend
- test suite passes

---

## PHASE 1 — Library MVP

Goal: ingest files and browse them.

Build:

- source scanner
- hashing/idempotency
- franchise CRUD
- asset classifier
- text/EPUB/PDF extraction
- CBZ pages
- video metadata
- subtitle parsing
- asset browser
- job status UI

Exit:

Add a franchise folder -> scan -> assets appear in UI.

---

## PHASE 2 — Canon Extraction MVP

Goal: turn source text into structured entities.

Build:

- characters
- events
- locations
- abilities
- relationships
- canon claims
- provenance
- confidence
- entity merge/review UI
- text embedding/search

Exit:

Select a franchise and ask:
“What does Character X know at this point?”
The answer is grounded in indexed source data.

---

## PHASE 3 — Anime Intelligence

Goal: searchable scenes.

Build:

- FFmpeg worker
- keyframes
- shot boundaries
- subtitles/transcripts
- scene segmentation
- clip timeline
- character tagging
- speaker manual anchors
- performance statistics
- visual scene embeddings

Exit:

Search:
“quiet conversation between A and B”
and retrieve matching episode scenes.

---

## PHASE 4 — Project + Branch Engine

Goal: create alternate continuity safely.

Build:

- Project
- canon cutoff
- Branch
- story bible
- character project states
- timeline
- user locks
- checkpoint/branch UI

Exit:

Create “Continuation after canon” without modifying canon records.

---

## PHASE 5 — Story Planner

Goal: produce coherent long-form plans.

Build:

- premise generator
- saga planner
- arc planner
- chapter planner
- must-have / forbidden constraints
- length target
- approval workflow

Exit:

User can request a 60-chapter project and receive structured arcs/chapter objectives without drafting all chapters.

---

## PHASE 6 — Continuity Brain

Goal: long-term consistency.

Build:

- knowledge engine
- secrets
- character states
- relationship deltas
- mysteries
- foreshadowing
- continuity validator
- post-chapter state extraction

Exit:

Intentional test errors are caught automatically.

---

## PHASE 7 — Manga Studio

Goal: story -> manga production package.

Build:

- chapter draft
- manga script
- page planner
- panel planner
- dialogue placement notes
- visual references retrieval
- exports to Markdown/JSON/PDF later

Exit:

Approved chapter can become a full page/panel script.

---

## PHASE 8 — Anime Studio

Goal: manga/story -> episode package.

Build:

- runtime estimator
- episode mapping
- screenplay
- shot list
- storyboard spec
- performance direction
- music/SFX direction

Exit:

A selected arc can produce a coherent episode season plan.

---

## PHASE 9 — Generative Visual Layer

Goal: concept and storyboard assets.

Build provider interfaces for:

- character concepts
- environments
- covers
- keyframes
- panel roughs
- storyboard frames

Critical:
store provenance, prompt, seed/settings when available, and approved reference IDs.

Focus first on **storyboards/concept images**, not final animation.

---

## PHASE 10 — Audio Layer

Goal: scratch performances and production direction.

Build:

- line-by-line performance direction
- original/authorized speech provider
- scene audio assembly
- temporary SFX/music placeholders
- timing sync

Do not tightly couple story logic to any one voice service.

---

## PHASE 11 — Animatic

Goal: playable rough episode.

Combine:

- storyboard frames
- camera moves
- dialogue audio
- timing
- captions
- temporary music/SFX

Export a rough video/animatic.

This is a much more achievable stepping stone than attempting full final-quality animation immediately.

---

## PHASE 12 — Advanced Automation

Later:

- automated downstream consequence regeneration
- project health checks
- parallel story simulations
- branch comparison
- “what if” batch generation
- multi-agent extraction
- advanced visual consistency
- animation provider integrations
- localization
- collaborative projects

---

# 44. MVP DEFINITION

Do NOT call the entire giant vision “MVP”.

The first useful MVP is:

1. Add a franchise to `/source-vault`.
2. Scan it.
3. Read manga/LN text + subtitles.
4. Build searchable characters/events/relationships.
5. Create a project branching from canon.
6. Generate a story bible.
7. Generate an arc plan.
8. Generate one chapter.
9. Run continuity validation.
10. Store the chapter as a versioned project state.

Everything else comes after this loop works reliably.

---

# 45. FIRST DEMO

Use an ORIGINAL tiny synthetic franchise created in `/fixtures/demo_universe`.

Contents:

- 3 characters
- 2 chapters of text
- 1 fake episode transcript
- 2 locations
- 1 power system
- 1 secret

Demo flow:

1. ingest
2. inspect characters
3. search source
4. create continuation
5. generate 5-chapter arc
6. write Chapter 1
7. reveal a deliberate contradiction
8. continuity validator catches it
9. branch Chapter 1 into alternate choice

Only after this passes should real large libraries be tested.

---

# 46. CODING RULES FOR THE AGENT

1. Read this entire specification before implementation.
2. Begin with Phase 0 only.
3. Do not prematurely implement animation or voice cloning.
4. Keep source immutable.
5. All extracted/generated facts require provenance fields.
6. Use strict schemas for AI outputs.
7. All provider-specific code belongs behind interfaces.
8. No silent destructive migrations.
9. Add tests with every feature.
10. Keep functions/modules reasonably small.
11. Prefer boring reliable infrastructure over clever abstractions.
12. No hardcoded franchise names.
13. No prompts inline in business logic.
14. Every long-running operation is a resumable job.
15. Ingestion is idempotent.
16. Store uncertainty/confidence rather than inventing certainty.
17. User edits/locks override model suggestions.
18. Canon records and project records are separate.
19. Do not implement a feature unless its acceptance criteria can be tested.
20. Commit in small coherent milestones.

---

# 47. INITIAL API SURFACE

Possible first endpoints:

```text
GET    /health

GET    /franchises
POST   /franchises
GET    /franchises/{id}

POST   /library/scan
GET    /jobs
GET    /jobs/{id}

GET    /assets
GET    /assets/{id}

GET    /characters
GET    /characters/{id}

GET    /events
GET    /relationships

POST   /search

GET    /projects
POST   /projects
GET    /projects/{id}

POST   /projects/{id}/branches
POST   /projects/{id}/story-bible
POST   /projects/{id}/plan
```

Do not build all endpoints in Phase 0.

---

# 48. IMPORTANT UI SCREENS

## Setup
- source path
- library path
- provider keys/status
- database status

## Library
- franchises
- assets
- search
- review queue

## Franchise
- overview
- timeline
- characters
- relationships
- world
- sources
- anime scenes

## Project
- overview
- story bible
- cast
- timeline
- arcs
- chapters
- relationships
- mysteries
- production

## Director
- conversation
- proposed changes
- retrieved references
- approve/edit/branch buttons

---

# 49. DATA QUALITY RULES

Never merge two entities solely because names are similar.

Use:

- aliases
- source adjacency
- franchise
- visual match
- explicit user confirmation

Every autogenerated fact needs a confidence value.

Low-confidence facts should not become “locked canon” automatically.

Contradictory claims may coexist until resolved.

Example:

```text
Claim A: Event happened before X.
Claim B: Event happened after X.

Status: chronology conflict
```

---

# 50. COST CONTROL

Extraction of a huge library can be expensive if every page/frame is sent to frontier models.

Use tiers:

## Tier 0
local deterministic processing

## Tier 1
small/local model classification

## Tier 2
cheap cloud model structured extraction

## Tier 3
frontier model only for hard ambiguity / creative reasoning

Cache every result by input hash + prompt version + model.

Never regenerate unchanged extraction automatically.

---

# 51. PERFORMANCE

Large franchises may contain:

- thousands of pages
- hundreds of episodes
- millions of text tokens
- tens of thousands of scenes

Therefore:

- batch ingestion
- resumable jobs
- incremental indexing
- pagination
- background processing
- thumbnail generation
- lazy media loading

Never require whole-franchise context in memory.

---

# 52. FUTURE GRAPH DATABASE

Start in PostgreSQL.

Only introduce Neo4j or another graph database if measured complexity/search requirements justify it.

The relational model can represent edges initially.

Avoid infrastructure inflation.

---

# 53. EXPORTS

Eventually support:

- project backup bundle
- story bible Markdown
- chapter Markdown
- manga script Markdown/PDF
- episode screenplay
- JSON production package
- storyboard image sequence
- animatic MP4

Exported data must include project/branch/version identifiers.

---

# 54. PRODUCT TERMINOLOGY

Recommended internal vocabulary:

- **Library** — imported fictional knowledge
- **Franchise** — one source universe/IP
- **Asset** — imported file
- **Canon** — extracted source continuity
- **Project** — a new creative work
- **Branch** — alternate project continuity
- **Story Bible** — project rules
- **Director** — user-facing creative control
- **Studio** — production tools
- **Claim** — atomic knowledge statement
- **State** — character/world condition at a point
- **Lock** — user-approved rule that AI cannot silently change

---

# 55. SUCCESS METRICS

The system is successful when:

- adding a new source franchise does not require code changes
- a 100-chapter project does not lose early continuity
- the user can inspect why the AI believes a canon fact
- the user can branch without destroying prior work
- corrections improve future outputs
- story generation can switch providers
- manga/anime production layers consume the same story state
- the system can explain continuity conflicts before generating bad scenes

---

# 56. WHAT NOT TO BUILD FIRST

Do not begin with:

- final-quality animation
- exact third-party voice cloning
- custom foundation-model training
- huge microservice architecture
- Kubernetes
- graph database
- mobile app
- automatic publishing
- multiplayer
- full autonomous “make me an anime” button

Build the **knowledge + continuity + story loop** first.

If that foundation is weak, every visual/audio feature will amplify bad continuity.

---

# 57. FIRST 20 IMPLEMENTATION ISSUES

Create these as GitHub issues/milestones.

1. Bootstrap monorepo
2. Devcontainer/Docker Compose
3. PostgreSQL + pgvector
4. FastAPI health/config
5. Next.js shell
6. Shared API schema generation
7. Source/library path configuration
8. Asset database model
9. Recursive source scanner
10. SHA-256/idempotent ingestion
11. Franchise model/UI
12. Background job model
13. TXT/MD extractor
14. EPUB extractor
15. PDF extractor
16. CBZ extractor
17. subtitle parser
18. video metadata extractor
19. asset browser UI
20. synthetic demo-universe fixture + integration test

Then start Phase 2.

---

# 58. AGENT HANDOFF PROMPT

Copy everything below into the coding agent together with this specification.

---

You are the lead engineer for **Project Continuum**, a local-first personal multiverse story studio.

Read the complete `PROJECT_CONTINUUM_MASTER_PLAN.md` before changing code.

Your job is to build the project incrementally and permanently, not produce a disposable prototype.

## Operating rules

- Treat `/source-vault` as read-only.
- Never hardcode any particular anime/manga/franchise.
- Separate imported canon from generated project continuity.
- All extracted claims need provenance and confidence.
- All AI model calls must go through provider interfaces.
- All structured model responses must validate against schemas.
- Store prompt templates as versioned files.
- Make ingestion idempotent and resumable.
- Add tests as you implement features.
- Prefer root-cause solutions over patches.
- Do not prematurely build animation, final image generation, or voice cloning.
- Use Git commits/checkpoints frequently.
- Never delete or overwrite user source material.
- If the specification has ambiguity, choose the simplest architecture that preserves future extensibility and document the decision.

## First assignment

Implement **Phase 0 — Foundation only**.

Before coding:

1. Inspect the current repository.
2. Write a short implementation plan.
3. Identify any contradictions in the specification.
4. Propose the exact initial monorepo tree.
5. Then implement it.

Phase 0 acceptance criteria:

- Next.js/TypeScript web app boots.
- FastAPI/Python API boots.
- PostgreSQL + pgvector is available in local development.
- frontend can call `/health`.
- database migrations run.
- provider interfaces exist but contain no unnecessary vendor coupling.
- configuration loads from `.env` with a safe `.env.example`.
- CI runs lint/typecheck/tests.
- a synthetic fixture directory exists for future integration tests.
- `README.md` contains exact setup/start/test commands.
- `AGENTS.md` captures the permanent engineering constraints.
- all tests pass.

Do not start Phase 1 until Phase 0 is working and reviewed.

At completion, report:

- files created/changed
- architecture decisions
- commands run
- test results
- known limitations
- recommended Phase 1 issues

---

# 59. RECOMMENDED WORKFLOW WITH A CODING AGENT

Do not paste:

> “Build this entire thing.”

Use the master specification, then work phase by phase.

For each phase:

1. Agent inspects current repository.
2. Agent proposes exact implementation.
3. Agent implements one coherent milestone.
4. Agent runs tests.
5. Review diff.
6. Commit.
7. Continue.

Use separate branches/worktrees for safely parallelizable items only.

Example:

```text
main
├── feature/library-scanner
├── feature/epub-extractor
└── feature/asset-browser
```

Do not parallelize two agents that are redesigning the same database models at the same time.

---

# 60. LONG-TERM END STATE

The full pipeline is:

```text
USER SOURCE MATERIAL
        ↓
MULTIMODAL INGESTION
        ↓
CANON + PROVENANCE DATABASE
        ↓
TIMELINE / CHARACTER / RELATIONSHIP / KNOWLEDGE GRAPH
        ↓
PROJECT BRANCH
        ↓
STORY BIBLE
        ↓
SAGA / ARC / CHAPTER ENGINE
        ↓
CONTINUITY VALIDATION
        ↓
MANGA SCRIPT / SCREENPLAY
        ↓
PAGE / PANEL / SHOT PLANNING
        ↓
VISUAL + PERFORMANCE DIRECTION
        ↓
STORYBOARD
        ↓
SCRATCH AUDIO
        ↓
ANIMATIC
        ↓
FUTURE GENERATIVE PRODUCTION LAYERS
```

The foundation is the library and continuity engine.

Everything else should consume that same canonical/project state.

---

# FINAL ENGINEERING DIRECTIVE

Optimize for a system that can grow for years.

The first version does not need to be visually spectacular.

It needs to be:

- understandable
- inspectable
- correct
- recoverable
- extensible
- provider-agnostic
- continuity-aware
- safe with source material

If the underlying fictional-memory system becomes excellent, the manga, anime, storyboard, image, and audio layers become increasingly powerful instead of increasingly chaotic.

---

# V0.2 ADDENDUM — LIVING STORY VAULT

This addendum supersedes any earlier implication that Continuum is mainly a one-shot story generator. Continuum is a **private personal source vault + living story studio**. The user's project continuity is the creative center. Ongoing manga/anime/light-novel canon can be imported later as structured deltas and selectively allowed to influence future character development and arcs.

## 61. Storage model

```text
/source-vault/   # original user-provided media; READ ONLY
/library/        # indexes, metadata, transcripts, thumbnails
/projects/       # story projects, branches, bibles, state
/generated/      # generated manga/storyboards/animatics/exports
/cache/          # disposable derived media
```

Rules: never modify source-vault files; removing an item from Continuum removes derived records by default, not originals; no scraping/piracy/download subsystem; no DRM circumvention; allow per-franchise `LOCAL_ONLY`; cloud providers only receive source fragments when policy/config allows.

## 62. Library Mode and Studio Mode

**Library Mode:** read manga/comics, read EPUB/LN/PDF, watch anime/video, subtitles, progress, bookmarks, notes, collections, source search, characters, timeline, manga↔anime links.

**Studio Mode:** Idea Box, World Studio, map, arrivals, story projects, story bibles, arcs, chapters, branches, canon sync, ripples, manga scripts, storyboards, anime adaptation and generated exports.

Any source page/paragraph/scene/timestamp can be sent directly into a project as a reference.

## 63. Reader / Media Center

Manga reader: CBZ, ZIP images, PDF, image folders; single/double page, RTL/LTR, zoom, fullscreen, progress, bookmarks, notes. CBZ backend exposes a safe page manifest and cached page images without changing the archive.

PDF reader: use a browser renderer such as PDF.js; persist page/progress/bookmarks/annotations.

EPUB/LN reader: chapter navigation, pagination/continuous mode, theme/font controls, highlights, notes and stable source locators.

Anime player: local range requests, subtitles, watch progress, scene markers, bookmarks, notes, Send to Project. If codec/container is browser-incompatible, create a browser-compatible proxy/transcode under `/cache` using FFmpeg; never alter source media.

Smart actions: Add Note, Add to Collection, Send to Project, Mark Important, Open Character, Show on Timeline, Show on Map, Find Similar, Compare With Project State.

## 64. Adaptation links

Support confirmed/suggested links among manga pages, anime timestamps and novel sections. Preserve each medium as a separate source representation.

## 65. Idea Box

Every project and arc has a free-form Idea Box. AI may parse candidate world/events/relationships, but the original note is preserved and no idea becomes project canon automatically.

Statuses: IDEA, EXPERIMENT, APPROVED, LOCKED, DISCARDED.

## 66. World Studio + interactive map

World model covers geography, regions, cities, landmarks, cultures, factions, history, cosmology, travel, power systems, incursions/portals, politics, threats and mysteries.

Map MVP: import/create base map image, pan/zoom, markers, routes, character positions, factions, portals/incursions and event markers. Map markers link to Location IDs. Support timeline-dependent location states so the same city can be intact in Chapter 1 and destroyed/rebuilt later.

Track character travel and location so continuity validation can flag impossible appearances.

## 67. Arrival Engine

Each imported character/group records origin franchise, source snapshot, departure point, arrival mechanism, arrival location/time and cosmology rule. Permit physical transfer, branching, duplication, temporal displacement or custom rules. Do not impose one multiverse explanation.

## 68. Story build modes + planning horizon

Modes: Complete Story, Saga by Saga, Arc by Arc, Chapter by Chapter, Sandbox. Default recommendation for ongoing franchises: **Arc by Arc**.

Planning horizon: DETAILED (next arc), ROUGH (following arcs), FOG OF WAR (beyond). This avoids locking 100 future chapters before ongoing source series finish new arcs.

## 69. Canon snapshots

Never overwrite prior source understanding. Each franchise has versioned `SourceCanonSnapshot` records containing source cutoff, assets, claims and known arc boundaries. Projects record which snapshot they began from and compare it with newer snapshots.

## 70. Source Character vs Project Character

Never store one global character truth. Maintain source states by canon snapshot and project states by branch/chapter. Intentional divergence is first-class.

Example:
```text
SOURCE OKARUN: memory normal, Ability X unlocked
PROJECT OKARUN: memory lost, Ability X pending integration
```

## 71. Character Canon Sync

Per imported character: LIVE, CURATED (default), FROZEN.

New canon deltas are typed: POWER, LIMITATION, PERSONALITY, MEMORY, RELATIONSHIP, KNOWLEDGE, BACKSTORY, DESIGN, STATUS, WORLD_CONNECTION, RETROACTIVE_REVEAL.

## 72. Arc Sync

Ongoing source arcs can be WATCHING, COMPLETE, REVIEWED, INTEGRATED. Optional `AUTO_WAIT_FOR_ARC_END=true`: index new chapters while an official arc is running but wait for completion before major integration analysis.

Canon Update Inbox shows completed source arcs and only deltas relevant to characters used by the project.

## 73. Retroactive revelation vs future development

Distinguish a new revelation that was already true before divergence from a development that happens later. Retroactive options: adopt retroactively, reveal now, transform, ignore, branch. Future developments can be queued without rewriting past chapters.

## 74. Canon import modes and delay

For each major delta: PRESERVE, ADAPT, ECHO, RECONCILE, REPLACE, BRANCH, DELAY, IGNORE.

Assimilation timing: immediately, next chapter, next arc, after storyline, after N chapters, project date, manual release, never. New abilities should normally be earned/discovered inside the project instead of appearing as a silent database toggle.

## 75. Ripple Engine

Changes produce dependency analysis and two outputs: CONFLICTS and OPPORTUNITIES.

Severity: 0 none, 1 cosmetic, 2 scene, 3 chapter, 4 arc, 5 saga, 6 fundamental break.

Example: new ability → old fight premise breaks → villain strategy changes → another character may survive → later relationship beat changes.

## 76. Change Graph

Major planned/generated elements record dependencies (events, relationship states, abilities, locations, secrets). When one element changes, Continuum identifies affected descendants rather than regenerating the whole project.

## 77. Arc Mutation

Preserve approved work whenever possible. If A→B→C→D→E and C becomes invalid, prefer A→B→NEW C→ADAPTED D→E if E remains valid.

## 78. Story Anchors + No-Go Rules

Anchors are outcomes/scenes the user wants protected. No-Go rules are prohibited developments. Ripple adaptation works around both unless the user explicitly unlocks them.

## 79. Retcon Manager + Reconciliation Arcs

User-created retcons get impact analysis and MINIMAL, FULL, HIDDEN/REVEAL or BRANCH modes. Large mismatches between source canon and project continuity may become optional Reconciliation Arcs rather than errors.

## 80. Character simulation systems

Character Agency Engine tracks goals, fears, beliefs, needs, plans and obstacles and can answer “what would everyone do if the plot did nothing?”

Character Chemistry Playground creates non-canon relationship experiments.

Sandbox scenes do not change project state until promoted to canon.

Why Engine explains how a relationship/belief/state developed from earlier events.

Character Memory stores subjective interpretations of the same event.

## 81. Long-story health systems

Consequence Memory keeps major events affecting politics, locations and characters later. Emotional Continuity warns about implausible abrupt tone/state changes. Promise/Payoff Tracker tracks expectations. Repetition Detector flags repeated plot devices. Narrative Health Dashboard is diagnostic, not an objective score. Theme Engine checks whether arcs connect to project themes.

## 82. Spoiler boundary

Track `indexed_through` separately from `user_read_through`. When spoiler protection is on, UI/generation cannot reveal or use later source material without permission.

## 83. State of the Universe + Control Center

One-click recap includes world state, current arc/chapter, character locations, relationships, mysteries, promises, threats, pending canon updates, anchors, no-go rules and open decisions.

## 84. Generated project reader

Generated stories can be consumed as Story, Manga Script, Manga Pages, Anime Script, Storyboard or Timeline. Export generated project material as Markdown/PDF/CBZ/images/scripts/JSON packages. Generated panels remain editable and versioned.

## 85. Updated implementation order

```text
1 Foundation + vault safety
2 Vault/library scan
3 Reader/media access
4 Canon extraction/provenance
5 Project/branch/world studio
6 Story planning
7 Change Graph + continuity
8 Arc/Character Canon Sync
9 Ripple/Retcon/Arc Mutation
10 Character simulation
11 Manga/anime production
12 Visual/audio/animatic layers
```

## 86. Updated phases

Phase 0: foundation, explicit storage semantics, path-safety tests, provider privacy config, dependency inventory.

Phase 1: Vault + Library MVP — scan, hash, classify, browse; source read-only enforcement.

Phase 2: Reader MVP — CBZ/images, PDF.js, epub.js, progress/bookmarks/notes, basic video/subtitles, Send to Project.

Phase 3: Canon Extraction.

Phase 4: Anime Intelligence — FFmpeg, subtitles, PySceneDetect, keyframes, transcription/alignment.

Phase 5: Project + World Studio — Idea Box, Story Bible, map, arrivals, anchors/no-go rules, planning horizon.

Phase 6: Story Planning — saga/arc/chapter, arc-by-arc workflow, sandbox.

Phase 7: Continuity + Change Graph.

Phase 8: Live Canon / Arc Sync — snapshots, deltas, update inbox, spoilers, import modes/delays.

Phase 9: Ripple / Retcon — mutation, reconciliation, branch comparison.

Phase 10+: production layers.

## 87. GitHub dependency strategy

External projects are classified DEPENDENCY, EXTERNAL TOOL, REFERENCE ONLY or OPTIONAL/LATER. Do not clone everything into the monorepo. Verify license/activity/version, wrap dependencies behind adapters, add contract tests and document in `docs/DEPENDENCIES.md`.

Current shortlist:

- `pgvector/pgvector` — DEPENDENCY: vector search in PostgreSQL.
- `mozilla/pdf.js` — DEPENDENCY: browser PDF reader.
- `futurepress/epub.js` — DEPENDENCY: EPUB reader after compatibility spike.
- `Breakthrough/PySceneDetect` — DEPENDENCY: shot/cut detection.
- `SYSTRAN/faster-whisper` — DEPENDENCY candidate: local transcription provider.
- `m-bain/whisperX` — OPTIONAL: word alignment/diarization if needed.
- `tkarabela/pysubs2` — DEPENDENCY: subtitle parsing.
- `xyflow/xyflow` — DEPENDENCY: relationship/ripple/change graphs.
- `Leaflet/Leaflet` — DEPENDENCY candidate: fictional map prototype.
- `FFmpeg/FFmpeg` — EXTERNAL TOOL: ffmpeg/ffprobe binaries; do not vendor source.
- `gotson/komga` — REFERENCE ONLY: comic/manga/eBook library UX and architecture.
- `jellyfin/jellyfin` — REFERENCE ONLY: local media streaming/transcoding/subtitle architecture; GPL code requires care.
- `facebookresearch/demucs` — OPTIONAL/LATER; useful but repository is archived.

## 88. Revised end-to-end demo

Use synthetic test media: ingest demo CBZ → read/bookmark/note → Send to Project → extract known demo canon → generate five-chapter continuation → inject deliberate continuity conflict → add synthetic new source arc → detect Canon Delta → delay to next project arc → Ripple Engine finds affected planned chapter → Arc Mutation preserves unaffected content.

## 89. Final v0.2 principle

**New source canon never silently overwrites our story. It becomes new information about the characters and their origins. Continuum shows what changed, what it could affect, and what story opportunities it creates. The user decides when and how it enters.**

**The Source Vault is also a usable personal library: read, watch, annotate, search and send exact source references into creative projects.**

---

# V0.3 CONSOLIDATION — AUTHORITATIVE PRODUCT AND ENGINEERING RULES

This section records the decisions made after v0.2 and is authoritative when it conflicts with older wording. It is intentionally written as **product requirements**, not as hardcoded story content. Continuum must support the user's creative project without baking any specific franchise, city, romance, plot, or crossover premise into the engine.

# 90. V0.3 OPERATING PROFILE — LOCAL, FREE-FIRST, HARDWARE-AGNOSTIC

Continuum is designed for **$0 recurring AI/API cost as the default**, even if local generation takes much longer.

The hierarchy is:

1. **FREE / LOCAL** — default. Local deterministic tools and local models. Slow is acceptable.
2. **HYBRID / OPTIONAL** — user may explicitly enable a paid or cloud provider for a difficult task.
3. **SHOWCASE / OPTIONAL** — higher-cost or higher-compute path for selected shots/episodes, never required for core functionality.

Rules:

- The application must remain useful with **no cloud AI account configured**.
- Hardware determines throughput and available provider choices, not the project data model.
- Never design a project so that changing GPU/PC invalidates project state.
- Providers expose capability metadata (text/image/video/audio/embedding, memory requirements when known, local/cloud, license notes, privacy class).
- The scheduler may choose a compatible local provider, but never silently switch to a paid provider.
- Cache by stable input hash + model/provider/version + recipe version.
- Do not regenerate unchanged work automatically.
- Prefer a slower free render to a recurring paid dependency when quality is acceptable.

**Non-goal:** benchmarking the user's current PC as a prerequisite to architecture. Runtime telemetry can learn throughput after real jobs run.

# 91. DURABLE PRODUCTION JOB MANAGER — FOUNDATION INVARIANT

All long-running work is represented as a durable job. This includes ingestion, hashing, thumbnails, transcription, embeddings, canon extraction, image generation, audio generation, video generation, upscaling, compositing, exports, backups, and future remaster tasks.

The UI is a client of the job system; it is **not** the owner of job state.

## 91.1 Required job states

At minimum:

- `QUEUED`
- `BLOCKED`
- `RUNNING`
- `PAUSING`
- `PAUSED`
- `SUCCEEDED`
- `FAILED_RETRYABLE`
- `FAILED_FINAL`
- `CANCELLED`

A job may contain durable child steps and checkpoints.

## 91.2 Durable fields

Each job should record, as applicable:

- job ID and type
- project/franchise/source references
- status and priority
- created/started/updated/completed timestamps
- current step and total steps
- units completed / units total
- checkpoint payload or checkpoint locator
- input hashes
- provider/model/recipe versions
- output artifact IDs
- dependency job IDs
- retry count / last error / error history
- elapsed active time
- rolling throughput estimate
- ETA estimate + confidence / `estimating` state
- resource hints when useful
- cancellation/pause request flags

## 91.3 Checkpoint policy

Checkpoint at the smallest practical durable unit:

- manga ingestion: page/chapter/batch
- anime analysis: scene/shot/batch
- subtitles/transcription: segment/batch
- embeddings: batch
- voice: line or dialogue block
- image generation: every accepted/generated asset
- animation: shot, clip, or model-supported checkpoint
- upscale/interpolation: frame batch
- export: section/chapter/shot bundle when practical

A multi-hour task must never depend on one final write at the end.

## 91.4 Shutdown and restart behavior

- Closing the **web/UI** must not cancel worker jobs.
- The desktop wrapper, if used later, offers `Keep working in background` or `Pause and exit`.
- Graceful worker shutdown persists a checkpoint and transitions work to a resumable state.
- Unexpected process termination must leave enough durable state to recover completed units and retry only incomplete units.
- Full PC shutdown stops compute but does not erase work.
- On restart, the scheduler reconstructs runnable jobs from the database.

## 91.5 Hardware migration

A project can move to another computer by restoring/copying persistent project data and required source/model assets.

If a queued job references a missing model/provider, mark it `BLOCKED` with a clear remediation action. Do not discard the recipe or completed outputs.

## 91.6 ETA learning

ETA is based on observed job telemetry, not a one-time benchmark requirement. The first units may show `Estimating…`; after enough samples, use rolling speed by job type/model/resolution/hardware signature when useful.

Changing hardware automatically establishes a new throughput profile.

# 92. PRODUCTION RECIPES, ARTIFACT LINEAGE, AND REMASTERABILITY

Every generated production artifact must have a reproducible **recipe/manifest** where practical.

For a shot this may include:

- story/episode/scene/shot IDs
- approved script revision
- character state snapshot IDs
- outfit/design variant IDs
- reference asset IDs
- model/provider/version
- adapters/LoRAs/control modules
- seed(s)
- prompt/template package versions
- input image/audio/video IDs
- generation settings
- post-processing chain
- parent artifact/version
- approval state

This makes it possible to:

- compare revisions;
- regenerate only one broken shot;
- migrate providers;
- preserve accepted creative decisions;
- remaster old episodes later with newer hardware/models without rewriting the story.

The system must distinguish **creative decisions** from **render implementation**. A future remaster may replace pixels while preserving script, shot design, timing, continuity, and approved performance intent.

# 93. SOURCE INTELLIGENCE PIPELINE

Continuum should not treat “training one giant model on all source media” as the primary architecture.

The default architecture is:

```text
Immutable Source Vault
        ↓
Deterministic / media parsing
        ↓
Typed source segments + provenance
        ↓
Structured extraction + embeddings/indexes
        ↓
Canon / Character / Craft knowledge records
        ↓
Context retrieval for the current task
        ↓
Writer / planner / critic / production providers
        ↓
Review + project-state updates only after approval rules
```

## 93.1 Source representations remain separate

Do not flatten manga, anime, light novel, databook, subtitles, interviews, artbooks, production notes, and user notes into one undifferentiated truth.

Maintain medium/source representation so Continuum can say, for example:

- explicit in manga;
- adapted differently in anime;
- internal thought available only in LN;
- director/craft commentary about intent;
- user interpretation or project rule.

## 93.2 Retrieval over giant fine-tuning

For text/story intelligence, prefer structured retrieval + RAG + targeted critics over expensive monolithic fine-tuning.

Fine-tuning/adapters are optional later when measured tests show a benefit. They must not become the sole repository of canon knowledge because they are harder to update, cite, correct, branch, or remove.

## 93.3 Provenance is user-visible

Important claims and extracted behaviors should link back to source locators when available. A user must be able to inspect why Continuum believes a fact or behavior rule.

## 93.4 Source Intelligence quality loop

Support:

1. extract candidate fact/behavior/craft rule;
2. attach provenance and confidence;
3. detect contradictions;
4. queue uncertain/high-impact items for review;
5. record user correction;
6. prefer corrected/locked knowledge in future retrieval;
7. never rewrite immutable source records because the project diverged.

# 94. CHARACTER BRAIN

A `Character Brain` is structured knowledge used to simulate/write one character. It is not one opaque prompt and not a replacement for source provenance.

Possible components:

- identity and source versions
- decision model: goals, priorities, fears, needs, beliefs
- speech model: register, sentence patterns, naming conventions, silence, recurring mannerisms
- emotional model: how emotion is expressed or concealed
- relationship model: subjective relationship state, not just symmetric labels
- comedy model
- conflict/argument model
- combat/problem-solving tendencies
- knowledge and secrets by time/snapshot
- moral/behavior boundaries
- growth constraints and plausible change paths
- visual/performance notes
- evidence links and confidence

Character behavior can evolve inside a project. The Character Brain therefore has **Source Brain** material and **Project Character State** material; project growth never overwrites source history.

# 95. CRAFT / DIRECTOR VAULT

Continuum should be able to learn **craft principles** from user-supplied or legally accessible production material such as director notes, interviews, making-of material, artbooks, animation notes, and source-vs-adaptation comparisons.

Examples of extracted craft knowledge:

- camera/framing grammar
- pacing and pause use
- comedy timing
- romance staging
- action staging
- acting/body-language principles
- color/lighting intent
- background storytelling
- edit rhythm
- sound/music intent
- adaptation choices between media

Store the principle and evidence, not merely trivia.

A project may choose a craft profile for a scene/episode, but the engine should avoid direct style imitation as a hidden default. The goal is controllable creative direction using learned principles.

# 96. CHARACTER VAULT / CAST POOL SEMANTICS

Character selection is independent from main-character status.

The project must support at least these **selection states**:

- `APPROVED` — user wants the character available/present in the project.
- `OPTIONAL` — usable when the story finds a good reason; lower default priority.
- `UNREVIEWED_RESERVE` — skipped/not answered; not rejected and may be brought in later.
- `EXCLUDED` — user prefers not to use/import unless explicitly changed later.

Separately, a project can assign a **narrative presence role**, for example:

- `CORE`
- `ACTIVE_SUPPORT`
- `RECURRING`
- `OCCASIONAL`
- `CAMEO_BACKGROUND`
- `RESERVE`

A character can be `APPROVED + RECURRING`; approval does not imply protagonist.

Project notes attached to a franchise/character are first-class **Story Intent / Creative Notes**, preserved verbatim and versioned. They are not silently converted into canon facts.

The engine should support group arrival and individual arrival independently. A franchise is not an indivisible import unit; characters can have different source snapshots, departure times, arrival times, memories, and companions.

# 97. STORY CALENDAR, PACING, AND EPISODE SEMANTICS

Continuum must support long-form stories where **world growth, relationships, and daily life count as progress even when the central plot does not move**.

An episode/chapter may have one or more focus tags:

- `MAIN`
- `WORLD`
- `RELATIONSHIP`
- `CHARACTER`
- `CIVILIZATION`
- `SIDE_STORY`
- `DOWNTIME`
- `LORE_MYSTERY`
- `COMEDY`
- `EXPERIMENTAL`

Separately, importance can be:

- `ESSENTIAL`
- `IMPORTANT`
- `EXTRA`
- `SPECIAL_OVA`

These tags support alternate viewing/reading routes without calling all non-main-plot material “filler.”

## 97.1 Story Calendar

Track project time precisely enough to answer:

- when characters arrived;
- how long they have known each other;
- where they were on a date;
- how long construction/research/travel took;
- whether relationship progression is plausible;
- whether two scenes can happen in the stated order.

Support hours/days/weeks/months/years, but **never force large time skips** as a shortcut. Slow-burn day/week-scale progression must be natural to author.

## 97.2 Relationship timeline

Relationship milestones can be attached to dates/chapters/episodes: first meeting, mission, private conversation, conflict, reconciliation, confession, etc. The system may suggest pacing but does not force milestones.

# 98. WORLD, CIVILIZATION, INSTITUTION, AND FACTION HISTORY

World Studio must support a setting that evolves incrementally rather than appearing fully built.

Track historical states for:

- settlements/cities/districts
- roads, ports, transit, utilities
- housing
- food/agriculture/storage
- hospitals/medicine
- schools/academies
- research/technology/magic institutions
- commerce/currency/logistics
- defense/policing/emergency response
- laws/governance
- diplomacy/embassies
- festivals/civic culture
- factions/coalitions

A new institution should be linkable to the problem/event that caused it to exist. This allows a reader to inspect **how the world was built**.

## 98.1 Factions and governance

Support temporary coalitions and durable institutions without assuming every disagreement is violent. Factions may form around leadership philosophy, science, magic, defense, origin-world loyalties, economics, or specific issues. They can merge, dissolve, split, or become official institutions.

Governance is data-driven/project-defined. Do not hardcode monarchy, council, democracy, or any specific leader.

# 99. RELATIONSHIP STUDIO / CHARACTER CONNECTION ENGINE

Support relationship exploration as a first-class creative workflow.

Capabilities:

- relationship graph with directionality and subjective states;
- friendship/romance/family/rivalry/mentor/team relations;
- Chemistry Playground in non-canon sandbox;
- scene experiments between arbitrary characters;
- Why Engine that traces relationship development to prior events;
- promotion of approved sandbox outcomes into a branch/project only by explicit action;
- no automatic major romance/couple canonization.

Relationship episodes may be `IMPORTANT` even when they do not advance the central plot.

# 100. CONTINUUM VISUAL LAB

Visual Lab is a core Studio module for creative exploration and production preparation.

It must support **reference, exploration, variant management, approval, and story linkage** rather than acting as a one-shot image prompt box.

## 100.1 Character Closet

Per Project Character / Character Version:

- canon/reference outfits
- Continuum-original outfits
- casual/formal/combat/work/school/travel/festival/seasonal variants
- accessories
- hair/appearance variants
- palette notes
- design constraints
- recurrent vs one-episode use

## 100.2 Moodboard / Inspiration Vault

Store user-supplied inspiration assets and notes with tags and source metadata.

A reference can be labeled by intended use such as:

- silhouette
- palette
- material
- pose
- camera
- expression
- architecture
- lighting
- general mood

Do not assume the user wants literal copying of a reference.

## 100.3 Design Preview

Support generation/editing/variation workflows for:

- outfits
- expressions
- poses
- turnarounds
- hair/accessories
- character sheets
- visual style experiments
- location/prop concepts

The user should be able to compare variants side-by-side.

## 100.4 Design status

At minimum:

- `IDEA`
- `EXPERIMENT`
- `IN_REVIEW`
- `APPROVED`
- `LOCKED`
- `DISCARDED`
- `WHAT_IF`

An approved design may be scoped to a project, arc, episode, scene, season, climate, location, or date range.

## 100.5 Story-linked outfit metadata

Outfit/design records may include:

- character ID
- project/branch
- arc/episode/scene
- start/end project time
- occasion
- climate/location
- giver/designer/in-world origin
- emotional/story meaning
- frequency/reuse policy
- production asset versions

## 100.6 Visual identity vs render model

Do not define a character by one model checkpoint or LoRA. Maintain a model-independent visual identity/reference package, then attach provider-specific adapters as replaceable production implementations.

# 101. PRODUCTION PIPELINE — QUALITY BEFORE VOLUME

Do not optimize for “episodes per day.” Optimize for accepted quality per unit of compute.

Default production path:

```text
Story/episode plan
→ script
→ canon/character/continuity review
→ storyboard
→ low-cost animatic
→ human/AI review
→ approved keyframes/assets
→ shot animation only where needed
→ voice/performance
→ compositing/edit
→ upscale/finalization
→ QC
→ export
```

Permanent rule:

> **Never spend expensive/slow compute on a downstream asset while an upstream cheap decision is still unapproved.**

## 101.1 Shot-level quality tiers

A single episode can mix cheap and expensive techniques. For example:

- still/held shot + camera movement
- mouth/eye/body micro-animation
- reusable cycles
- composited effects
- image-to-video shot
- complex action generation

Do not require every second of an episode to be fully regenerated video.

## 101.2 Production profiles

Profiles define policy, not canon:

- `FREE_LOCAL`
- `BALANCED_LOCAL`
- `HYBRID_OPTIONAL`
- `SHOWCASE_OPTIONAL`

Each profile can choose providers/resolution/pass counts/quality checks while preserving the same story/shot recipes.

# 102. AUDIO / PERFORMANCE PRINCIPLE

Separate **character performance knowledge** from **voice synthesis implementation**.

Performance knowledge may include cadence, pauses, energy, emotional restraint, pronunciation, and interaction patterns derived from permitted source analysis.

Voice providers are replaceable. Exact third-party performer likeness cloning is not the default and remains subject to authorization/rights/provider policy.

Temporary/preview voices can be used for animatics before final audio is approved.

# 103. STORY DIRECTOR, AUTONOMY, AND APPROVAL GATES

Continuum may proactively propose next scenes, world problems, relationship opportunities, consequences, and production tasks. It can perform bounded autonomous planning inside a sandbox or approved arc.

However, explicit approval is required by default for high-impact operations such as:

- promoting a sandbox event into project canon;
- major relationship canonization/breakup;
- character death/permanent removal;
- fundamental power-system rewrite;
- destructive retcon;
- merging branches;
- replacing a locked Story Anchor;
- changing an `EXCLUDED` character to active use;
- switching to a paid/cloud provider when local-free policy is active.

Approval gates should be configurable but never silently bypassed.

# 104. WHAT IF LAB, BRANCH ARCHIVE, AND SAFE EXPERIMENTATION

What If / sandbox work is consequence-free until explicitly promoted.

Support:

- temporary branches;
- alternate relationship tests;
- alternate outfit/style tests;
- combat/power-balance experiments;
- alternate arrival scenarios;
- branch comparison;
- archive/restore;
- promote selected results without copying unrelated sandbox changes.

Future World Shards/Echoes/Convergence mechanics may build on branches and arrivals, but v0.3 intentionally does **not** lock one cosmology explanation into the engine.

# 105. POWER BALANCE / SYNCHRONIZATION — LATER SYSTEM CONTRACT

Power-system unification is deliberately later than Character/Source/Story foundations.

Continuum should reserve an extension point for project-defined power import/balance policies.

One planned concept is `Synchronization Level`, where 100% means full reconstruction/access to a character's imported source-snapshot abilities, **not a permanent power ceiling**. Project-earned growth can stack afterward.

Do not implement this in Phase 0–3 unless required for schema extensibility.

# 106. NEW / EXPANDED DATA ENTITIES

The following concepts should be modeled explicitly or have a clear extension path. Exact schema is subject to architecture review/ADRs.

- `Job`
- `JobStep`
- `JobDependency`
- `JobCheckpoint`
- `HardwareExecutionProfile` / telemetry record
- `GenerationRecipe`
- `Artifact`
- `ArtifactVersion`
- `ArtifactLineage`
- `CharacterBrain`
- `CharacterBrainRule/Evidence`
- `CraftPrinciple`
- `CraftEvidence`
- `CastSelection`
- `NarrativePresenceRole`
- `StoryIntentNote`
- `StoryCalendarEvent`
- `EpisodeFocusTag`
- `EpisodeImportance`
- `Institution`
- `InstitutionState`
- `InfrastructureAsset`
- `FactionState`
- `GovernanceState`
- `RelationshipMilestone`
- `VisualDesign`
- `VisualDesignVariant`
- `Moodboard`
- `MoodboardReference`
- `OutfitAssignment`
- `ProductionProfile`
- `ApprovalGate`

Avoid schema proliferation when an existing generic entity/version/state model can represent these cleanly. The architecture review must decide what deserves a table/entity vs typed JSON/edge/state record.

# 107. DIRECTOR UI — V0.3 TARGET SCREENS

In addition to Library/Project/Director screens, plan for:

- **Home / State of the Universe**
- **Production Queue** — jobs, progress, ETA, current step, pause/resume/cancel/reorder
- **Character Vault** — source/project character, selection state, narrative role, notes
- **Character Brain Inspector** — evidence, behavior rules, corrections
- **Relationship Studio**
- **Story Calendar**
- **World / Civilization Studio** — historical states + institution evolution
- **Visual Lab** — closet, moodboards, variants, comparison, approval
- **Craft / Director Vault**
- **Canon Update Inbox**
- **What If Lab**
- **Branch Archive / Compare**
- **Review Queue**
- **Provider / Production Profiles**
- **System / Storage / Backup / Recovery**

Do not build all of these in the foundation milestone. Phase 0 should create clean routing/component boundaries and job/status primitives without fake feature-complete screens.

# 108. STORAGE / BACKUP / RECOVERY — V0.3

Persistent data categories:

```text
/source-vault/     immutable user source media
/library/          derived persistent source intelligence
/projects/         project state, branches, bibles, creative data
/generated/        approved/generated artifacts and exports
/jobs/             optional human-readable job manifests/log exports
/models/           optional user-managed local model assets/cache references
/cache/            disposable derived/generated cache
/config/           non-secret config and profiles
```

Database holds authoritative structured state. Large media stays on filesystem with stable IDs/hashes/paths.

Backup policy must cover:

- database/migrations metadata
- project state/branches
- user corrections/locks
- Character Brain corrections
- Story Intent notes
- Visual Lab approvals/metadata
- generation recipes/manifests
- job state/checkpoint metadata necessary for safe recovery
- provider/profile config excluding secrets

Disposable caches may be rebuilt.

Add a future **Project/Studio Export Package** that can migrate a project to another machine with manifests identifying required source/model assets and missing dependencies.

# 109. REVISED DEVELOPMENT PHASES — AUTHORITATIVE V0.3 ORDER

The old numbered phases remain historical context. Use this order for implementation unless an ADR explicitly changes it.

## PHASE 0 — Foundation + Durable Execution

Build only:

- monorepo/dev environment
- FastAPI + web shell
- database + migrations
- canonical storage configuration (`/source-vault`, `/library`, `/projects`, `/generated`, `/cache`)
- strict source-vault path/read-only guard
- provider interfaces + local/cloud/privacy metadata contracts
- **durable Job/JobStep/JobCheckpoint skeleton**
- background worker boundary separated from UI
- graceful pause/restart/recovery contract using synthetic dummy jobs
- health/readiness endpoints
- config/secrets boundaries
- logging/observability primitives
- backup/export design ADR (not full backup product)
- tests + CI + AGENTS.md + dependency inventory

No media reader, canon extraction, story generation, Visual Lab, voice cloning, or animation generation.

## PHASE 1 — Vault + Library MVP

- safe scan/discover/hash/classify
- idempotent re-scan
- derived metadata records
- browse/filter/search basics
- delete derived records without touching originals
- durable scan jobs

## PHASE 2 — Reader / Media Center MVP

- CBZ/image folders
- PDF
- EPUB/LN
- local video/range/proxy as needed
- subtitles
- progress/bookmarks/notes
- Send to Project references

## PHASE 3 — Source Intelligence Foundation

- stable source segments/locators
- provenance
- hybrid retrieval/indexes
- structured extraction framework
- correction/review loop
- synthetic/golden corpus
- no giant-model fine-tune requirement

## PHASE 4 — Anime / Multimodal Intelligence

- FFmpeg probing/extraction
- subtitles/alignment
- scene/shot detection
- keyframes
- local transcription provider
- performance/visual analysis records
- adaptation links
- Craft/Director evidence ingestion

## PHASE 5 — Character / Canon Intelligence

- Character Brain MVP
- relationships/knowledge/memory
- canon snapshots and character versions
- user correction/lock flow
- Character Vault import/selection semantics

## PHASE 6 — Project / Branch / World Studio

- project canon layer
- Idea Box
- arrivals
- world/location/faction/institution state
- anchors/no-go rules
- Story Intent notes
- project/branch versioning

## PHASE 7 — Story Planning / Calendar / Relationships

- saga/arc/episode/chapter planner
- focus + importance tags
- Story Calendar
- Relationship Studio / milestones
- civilization/infrastructure planning
- sandbox planning

## PHASE 8 — Continuity + Change Graph

- continuity validator
- character state constraints
- location/travel constraints
- dependency/change graph
- promise/payoff and consequence memory basics

## PHASE 9 — Canon Sync + Ripple / Retcon

- new source snapshots/deltas
- Arc/Character Canon Sync
- spoiler boundary
- import modes/delay
- Ripple analysis
- retcon/reconciliation/arc mutation

## PHASE 10 — Visual Lab

- moodboards/references
- Character Closet
- visual variants/status/approval
- story-linked outfit assignments
- provider-agnostic image generation/editing adapters
- recipe/lineage integration

## PHASE 11 — Script / Manga / Storyboard / Animatic

- episode scripts
- manga page/panel planning
- storyboard/shot engine
- temporary audio
- animatic assembly
- approval gates before expensive render

## PHASE 12 — Local Image / Video / Audio Production

- local-first replaceable providers
- shot-level production profiles
- resumable render jobs
- voice/performance layer
- compositing/upscale/final QC
- manifests/remaster support

## PHASE 13+ — Advanced Director / Automation

- bounded autonomous Story Director
- advanced scheduling
- What If promotion tools
- quality/repetition/theme dashboards
- power synchronization/balance systems
- Shards/Convergence only after story needs justify them

# 110. PHASE 0 NON-NEGOTIABLE ACCEPTANCE TESTS

Before Phase 1 begins, demonstrate with synthetic data only:

1. Clean clone/install/migrations/boot succeeds using documented commands.
2. Web UI can call API health endpoint.
3. Configured `/source-vault` path is resolved/normalized safely.
4. Path traversal and symlink escape attempts are rejected.
5. Application code cannot write/delete/rename source-vault files through its storage abstraction.
6. A synthetic durable job can be queued and processed by a worker.
7. Job progress is persisted independently of the web page.
8. Closing/restarting the web UI does not cancel the worker job.
9. Gracefully stopping the worker leaves the job resumable from its last durable checkpoint.
10. Restarting the worker resumes/retries only unfinished synthetic units rather than restarting completed units.
11. A failed job records structured error/retry state.
12. Provider interfaces work with a no-op/local fake provider; no paid/cloud credentials are required.
13. Logs do not expose secrets.
14. Migration downgrade/upgrade strategy is documented and clean-database migration is tested.
15. `docs/DEPENDENCIES.md`, `docs/ARCHITECTURE_REVIEW.md`, ADRs, and `docs/PHASE_0_REPORT.md` exist before the phase is tagged complete.

# 111. V0.3 “DO NOT BUILD FIRST” LIST

Do not let architectural enthusiasm pull these into Phase 0:

- franchise-specific schemas/logic
- actual copyrighted test fixtures
- automated source downloading/scraping
- DRM bypass
- one giant source-trained LLM
- exact third-party voice cloning
- full anime episode generation
- final power-unification system
- giant graph database migration
- autonomous story canon changes
- hardcoded city/governance/crossover story premise
- microservices for modules that can be clean monorepo packages/workers
- cloud requirement for core library use

# 112. V0.3 ENGINEERING DIRECTIVE

Continuum must be able to become a very large creative studio **without requiring the foundation to know the final story**.

Build stable primitives first:

**immutable sources → durable jobs → provenance → versioned state → branches → approvals → replaceable providers → reproducible artifacts.**

Then layer intelligence and creative tools on top.

A slower local system that preserves work and produces one carefully reviewed episode is preferable to a faster system that loses state, depends on recurring paid services, or generates large volumes of inconsistent material.

The user's creative freedom is a product requirement: characters, relationships, cities, institutions, outfits, visual variants, story pacing, and world structure are project data — not assumptions hardcoded into the engine.

