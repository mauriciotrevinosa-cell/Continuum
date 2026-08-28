# Continuum — GitHub Repository Shortlist
Research snapshot: 2026-08-27

Do not clone these wholesale. Classify each as a dependency/tool/reference and verify license/version before use.

| Repository | Use | Decision |
|---|---|---|
| https://github.com/pgvector/pgvector | Vector similarity search inside PostgreSQL | DEPENDENCY |
| https://github.com/mozilla/pdf.js | Browser PDF reader | DEPENDENCY |
| https://github.com/futurepress/epub.js | EPUB/light-novel reader | DEPENDENCY after compatibility test |
| https://github.com/Breakthrough/PySceneDetect | Anime/video shot and scene-cut detection | DEPENDENCY |
| https://github.com/SYSTRAN/faster-whisper | Local transcription candidate | DEPENDENCY behind provider |
| https://github.com/m-bain/whisperX | Word timestamps/alignment/diarization | OPTIONAL DEPENDENCY |
| https://github.com/tkarabela/pysubs2 | Subtitle parsing/normalization | DEPENDENCY |
| https://github.com/xyflow/xyflow | Relationship, ripple, divergence and dependency graphs | DEPENDENCY |
| https://github.com/Leaflet/Leaflet | Fictional-world map prototype | DEPENDENCY candidate |
| https://github.com/FFmpeg/FFmpeg | Media probing/extraction/proxy/transcode | EXTERNAL TOOL; use binary |
| https://github.com/gotson/komga | Comic/manga/eBook library UX/API patterns | REFERENCE ONLY initially |
| https://github.com/jellyfin/jellyfin | Local video streaming/transcode/subtitle patterns | REFERENCE ONLY initially |
| https://github.com/facebookresearch/demucs | Source separation research | OPTIONAL/LATER; archived |

## Recommended immediate stack

**Reader:** custom Continuum UI + PDF.js + epub.js + our own CBZ image manifest/reader. Study Komga; do not import the entire Kotlin application.

**Anime:** browser player + local range streaming; FFmpeg/ffprobe for media metadata and browser-compatible cache proxies; PySceneDetect for candidate shot boundaries; pysubs2 for subtitles.

**Speech:** faster-whisper as the first local transcription provider. Add WhisperX only when word alignment/diarization provides measurable value.

**Search:** PostgreSQL full text + structured filters + pgvector. Do not add a separate vector database until measured requirements justify it.

**Graphs/UI:** xyflow is an excellent match for Relationship Graph, Knowledge Graph, Divergence Map, Canon Ripple Graph and Change Graph.

**World Map:** prototype Leaflet using a simple/image coordinate system. Hide it behind a map component so it can be replaced later.

## License cautions

- Komga: MIT — still use as reference first because its full stack does not match Continuum.
- Jellyfin: GPL-2.0 — study architecture/UX; do not casually copy code into Continuum without a licensing decision.
- PDF.js: Apache-2.0.
- epub.js: BSD-2-Clause in package metadata.
- PySceneDetect: BSD-3-Clause.
- faster-whisper: MIT.
- WhisperX: BSD-2-Clause.
- pysubs2: MIT.
- xyflow: MIT.
- Leaflet: BSD-2-Clause.
- FFmpeg: licensing depends on build/configuration; invoke installed binaries and document the distribution choice.
- Demucs: MIT but archived.

## Repos we are intentionally NOT prioritizing

- manga scraping/download managers — Continuum is a user-supplied private vault;
- full media-server forks — too much unrelated code;
- graph databases — PostgreSQL first;
- voice-cloning stacks — not foundation work;
- “one click anime” generators — production comes after continuity/memory.

## Permanent dependency rule

Before an agent adds anything: verify current license and activity, pin/test a version, wrap it in a small adapter, add a smoke/contract test, and record it in `docs/DEPENDENCIES.md`.
