# Synthetic image fixtures

| File | What it is | How it was made |
|---|---|---|
| `synthetic-gradient.heic` | a 96 × 64 HEVC-coded HEIC still: a horizontal colour gradient with a white rectangle. Invented content, 1,232 bytes, SHA-256 `383893524908673794162468cb41fbc46401c545dc81dd582aa1896513ac68d3` | encoded once with `pillow-heif` 1.1.1 (libheif 1.20.2, x265 encoder) in a throwaway environment outside the repository. The encoder is **not** a Continuum dependency; Continuum only decodes, with `pi-heif` |

Hostile variants (corrupt payloads, oversized dimensions, missing decoder) are derived from this file inside the tests at run time and are never committed.
