"""Production calibration chapters (M3): a non-canon visual sampler.

A calibration chapter re-materializes approved or creator-directed source
beats as isolated sampler pages. It is a production benchmark, never story
continuity and never canon.

The calibration document is consumed as data, not hardcoded: this module
parses a markdown document whose pages are ``## CAL-`` sections, each naming
its source document, source episode/page locator, source content, characters,
production locks, failure examples and (optionally) a wardrobe stage. Nothing
here knows a franchise, a project name or a character name.

Each page preserves, in its lineage and body:

* the CAL page identifier;
* the source episode/page locator;
* the source creative document and version;
* the page semantics (source content, production locks and failure examples);
* the characters present;
* the environment tags;
* the wardrobe stage (derived from the source locator's episode);
* render provenance and review/version lineage (via the existing attempt rows).

The chapter is a production sampler, not chronological canon: pages are
ordered by their CAL identifier, never treated as story continuity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from continuum_core import canonical_json_hash

from continuum_production.materialize import page_intents

__all__ = [
    "CALIBRATION_SCHEMA",
    "CalibrationPage",
    "parse_calibration",
]

CALIBRATION_SCHEMA = "continuum.calibration-chapter/1"

_CAL_HEADING = re.compile(r"^##\s+(?P<id>CAL-\d+)\s*[\u2014\u2013-]\s*(?P<title>.+?)\s*$")
_FIELD = re.compile(r"^\*\*(?P<key>[^*:]+):\*\*\s*(?P<value>.*)$")
_BULLET = re.compile(r"^\s*-\s+(?P<text>.+?)\s*$")
_SOURCE_LOCATOR = re.compile(r"E(?P<episode>\d+)\s+Page\s+(?P<page>\d+)", re.I)
_STRUCTURAL_MOJIBAKE = {
    "ΓÇö": "—",
    "ΓÇô": "\u2013",
    "â€”": "—",
    "â€“": "\u2013",
}


@dataclass(frozen=True, slots=True)
class CalibrationPage:
    """One calibration page, parsed from the calibration document."""

    cal_id: str
    title: str
    source_document: str
    source_locator: str
    source_content: str
    characters: tuple[str, ...] = ()
    #: Backward-compatible union of positive validation and failure notes.
    validation_notes: tuple[str, ...] = ()
    #: Positive visual requirements. These become render directions.
    primary_validation: tuple[str, ...] = ()
    #: Things the renderer must avoid. These become page constraints.
    failure_examples: tuple[str, ...] = ()
    wardrobe_stage: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _clean(value: str) -> str:
    return value.strip().strip("`").strip()


def _normalize_structure(text: str) -> str:
    """Repair known mojibake only where it affects markdown structure.

    Some committed creative documents originated as UTF-8 punctuation that was
    decoded through a legacy code page before being stored as UTF-16. The
    resulting text contains tokens such as ``ΓÇö`` instead of an em dash.
    Normalize only those separator tokens; creative prose otherwise stays byte-
    for-byte meaningful to the parser.
    """
    for broken, repaired in _STRUCTURAL_MOJIBAKE.items():
        text = text.replace(broken, repaired)
    return text


def _episode_stage(source_locator: str) -> str | None:
    match = _SOURCE_LOCATOR.search(source_locator)
    if match is None:
        return None
    return f"E{int(match.group('episode'))}"


def _characters(value: str) -> list[str]:
    """Parse a ``**Characters:**`` value into proper-name tokens.

    A value may be a plain comma list (``Mau, Frieren``) or a labelled list
    (``current G1 + G2 household: Frieren, Mau, ...``). Only the part after a
    label colon is a name; a trailing period is dropped. Lower-case prose such
    as ``one ordinary hostile creature`` describes scene content, not a stable
    character identity, so it is intentionally excluded from the cast field.
    """
    names: list[str] = []
    for token in value.split(","):
        token = token.strip().rstrip(".")
        if not token:
            continue
        if ":" in token:
            token = token.rsplit(":", 1)[1].strip().rstrip(".")
        if token and not token[0].islower():
            names.append(token)
    return names


def _append_extra_bullet(extra: dict[str, Any], key: str, value: str) -> None:
    """Preserve unknown fields whether markdown uses inline text, bullets, or both."""
    existing = extra.get(key)
    if isinstance(existing, list):
        existing.append(value)
    elif existing in (None, ""):
        extra[key] = [value]
    else:
        extra[key] = [existing, value]


def _append_note(current: dict[str, Any], key: str, value: str) -> None:
    text = value.strip().rstrip(";.")
    if not text:
        return
    current[key].append(text)
    current["validation_notes"].append(text)


def parse_calibration(text: str) -> list[CalibrationPage]:
    """Parse a calibration markdown document into its pages, in document order.

    Generic: only the ``## CAL-`` structure and the ``**Field:**`` lines are
    interpreted. Unknown fields are preserved in ``extra`` so nothing is lost.
    """
    text = _normalize_structure(text)
    pages: list[CalibrationPage] = []
    current: dict[str, Any] | None = None
    current_field: str | None = None

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        pages.append(
            CalibrationPage(
                cal_id=current["cal_id"],
                title=current["title"],
                source_document=current.get("source_document", ""),
                source_locator=current.get("source_locator", ""),
                source_content=current.get("source_content", ""),
                characters=tuple(current.get("characters", ())),
                validation_notes=tuple(current.get("validation_notes", ())),
                primary_validation=tuple(current.get("primary_validation", ())),
                failure_examples=tuple(current.get("failure_examples", ())),
                wardrobe_stage=current.get("wardrobe_stage"),
                extra=dict(current.get("extra", {})),
            )
        )
        current = None

    for line in text.splitlines():
        heading = _CAL_HEADING.match(line)
        if heading:
            flush()
            current = {
                "cal_id": heading.group("id"),
                "title": heading.group("title").strip(),
                "characters": [],
                "validation_notes": [],
                "primary_validation": [],
                "failure_examples": [],
                "extra": {},
            }
            current_field = None
            continue
        if current is None:
            continue
        if line.strip() == "---":
            continue
        field = _FIELD.match(line)
        if field:
            key = field.group("key").strip().lower().replace(" ", "_")
            value = _clean(field.group("value"))
            current_field = key
            if key == "source":
                current["source_document"] = value.split("—")[0].strip().strip("`")
                current["source_locator"] = value
                current["wardrobe_stage"] = _episode_stage(value)
            elif key == "source_content":
                current["source_content"] = value
            elif key == "characters":
                current["characters"] = _characters(value)
            elif key == "wardrobe_stage":
                current["wardrobe_stage"] = value.rstrip(".,;:").strip() or None
            elif key in {"primary_validation", "failure_examples"}:
                _append_note(current, key, value)
            else:
                current["extra"][key] = value
            continue
        bullet = _BULLET.match(line)
        if bullet and current_field in {"primary_validation", "failure_examples"}:
            _append_note(current, current_field, bullet.group("text"))
        elif bullet and current_field == "characters":
            current["characters"].extend(_characters(bullet.group("text")))
        elif bullet and current_field is not None:
            _append_extra_bullet(
                current["extra"], current_field, bullet.group("text").strip()
            )
    flush()
    return pages


def _production_directions(page: CalibrationPage) -> list[str]:
    """Materialize every creator-authored positive lock that should guide pixels."""
    directions: list[str] = []
    if page.source_content:
        directions.append(page.source_content)
    directions.extend(f"MUST SHOW: {note}." for note in page.primary_validation)

    # Structured calibration fields that describe page construction, wardrobe
    # or required visual truth are not metadata-only: they must reach the image
    # model. Preserve their markdown labels so the instruction remains legible.
    routed_keys = ("page_construction", "required", "wardrobe", "override")
    for key, value in page.extra.items():
        if not any(token in key for token in routed_keys):
            continue
        label = key.replace("_", " ").upper()
        values = value if isinstance(value, list) else [value]
        for item in values:
            text = str(item).strip()
            if text:
                directions.append(f"{label}: {text}")
    return directions


def calibration_body(
    project_key: str,
    episode: str,
    chapter: int,
    document_id: str,
    document_version: str | None,
    document_hash: str,
    pages: list[CalibrationPage],
    character_names: tuple[str, ...],
) -> dict[str, Any]:
    """A materialized-chapter-shaped body for a calibration chapter."""
    known = set(character_names)
    sequence: list[dict[str, Any]] = []
    for index, page in enumerate(pages, start=1):
        directions = _production_directions(page)
        constraints = [f"DO NOT: {note}." for note in page.failure_examples]
        declared = list(page.characters)
        missing_profiles = [name for name in declared if name not in known]
        everything = " ".join([page.title, *directions, *constraints])
        body = {
            "base_page": None,
            "label": page.title,
            "scene": "",
            "directions": directions,
            "dialogue": [],
            "constraints": constraints,
            "characters": declared,
            "intents": page_intents(everything, 0, declared),
            "chapter_end": False,
            "origin": "calibration",
            "integrated_page": index,
            "calibration": {
                "cal_id": page.cal_id,
                "source_document": page.source_document,
                "source_locator": page.source_locator,
                "wardrobe_stage": page.wardrobe_stage or _episode_stage(page.source_locator),
                "validation_notes": list(page.validation_notes),
                "primary_validation": list(page.primary_validation),
                "failure_examples": list(page.failure_examples),
                "missing_character_profiles": missing_profiles,
                "extra": page.extra,
            },
            "lineage": {
                "document_id": document_id,
                "version": document_version,
                "content_hash": document_hash,
                "cal_id": page.cal_id,
            },
        }
        body["page_key"] = f"cal-{index:03d}"
        body["page_hash"] = canonical_json_hash(
            {k: v for k, v in body.items() if k not in {"page_key", "page_hash"}}
        )
        sequence.append(body)

    characters = sorted({name for page in sequence for name in page["characters"]})
    result = {
        "schema": CALIBRATION_SCHEMA,
        "project_key": project_key,
        "episode": episode,
        "chapter": chapter,
        "chapter_cut": {"chapter": chapter, "first_page": 1, "last_page": len(sequence)},
        "allocation": {},
        "page_count": len(sequence),
        "integrated_numbering_provisional": False,
        "characters": characters,
        "pages": sequence,
        "insertions": {"placed_in_chapter": [], "unplaced": []},
        "sources": {
            "panel_script": {
                "document_id": document_id,
                "version": document_version,
                "content_hash": document_hash,
            },
            "overlay": None,
            "beats": [],
            "context": [],
        },
        "decisions": [],
        "warnings": [],
    }
    result["hash"] = canonical_json_hash(result)
    return result
