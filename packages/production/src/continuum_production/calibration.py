"""Production calibration chapters (M3): a non-canon visual sampler.

A calibration chapter re-materializes approved or creator-directed source
beats as isolated sampler pages. It is a production benchmark, never story
continuity and never canon.

The calibration document is consumed as data, not hardcoded: this module
parses a markdown document whose pages are ``## CAL-`` sections, each naming
its source document, source episode/page locator, source content, characters,
validation notes and (optionally) a wardrobe stage. Nothing here knows a
franchise, a project name or a character name.

Each page preserves, in its lineage and body:

* the CAL page identifier;
* the source episode/page locator;
* the source creative document and version;
* the page semantics (source content, validation notes);
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


@dataclass(frozen=True, slots=True)
class CalibrationPage:
    """One calibration page, parsed from the calibration document."""

    cal_id: str
    title: str
    source_document: str
    source_locator: str
    source_content: str
    characters: tuple[str, ...] = ()
    validation_notes: tuple[str, ...] = ()
    wardrobe_stage: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _clean(value: str) -> str:
    return value.strip().strip("`").strip()


def _episode_stage(source_locator: str) -> str | None:
    match = _SOURCE_LOCATOR.search(source_locator)
    if match is None:
        return None
    return f"E{int(match.group('episode'))}"


def parse_calibration(text: str) -> list[CalibrationPage]:
    """Parse a calibration markdown document into its pages, in document order.

    Generic: only the ``## CAL-`` structure and the ``**Field:**`` lines are
    interpreted. Unknown fields are preserved in ``extra`` so nothing is lost.
    """
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
                # "Source:" names the document and the episode/page locator.
                current["source_document"] = value.split("\u2014")[0].strip().strip("`")
                current["source_locator"] = value
                current["wardrobe_stage"] = _episode_stage(value)
            elif key == "source_content":
                current["source_content"] = value
            elif key == "characters":
                current["characters"] = [
                    c.strip().rstrip(".") for c in value.split(",") if c.strip()
                ]
            elif key == "wardrobe_stage":
                current["wardrobe_stage"] = value
            else:
                current["extra"][key] = value
            continue
        bullet = _BULLET.match(line)
        if bullet and current_field in {"primary_validation", "failure_examples"}:
            current["validation_notes"].append(bullet.group("text").strip().rstrip(";."))
        elif bullet and current_field == "characters":
            current["characters"].extend(
                c.strip().rstrip(".") for c in bullet.group("text").split(",") if c.strip()
            )
        elif bullet and current_field is not None:
            current["extra"].setdefault(current_field, []).append(bullet.group("text").strip())
    flush()
    return pages


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
    """A materialized-chapter-shaped body for a calibration chapter.

    The body reuses the page structure the production loop already consumes
    (``page_key``, ``directions``, ``characters``, ``intents``, ``lineage``),
    so calibration pages flow through the same bundle and review path while
    remaining a distinct, non-canon purpose.
    """
    known = set(character_names)
    sequence: list[dict[str, Any]] = []
    for index, page in enumerate(pages, start=1):
        directions = [page.source_content] if page.source_content else []
        present = [c for c in page.characters if c in known]
        everything = " ".join([page.title, page.source_content, *page.validation_notes])
        body = {
            "base_page": None,
            "label": page.title,
            "scene": "",
            "directions": directions,
            "dialogue": [],
            "constraints": [],
            "characters": present,
            "intents": page_intents(everything, 0, present),
            "chapter_end": False,
            "origin": "calibration",
            "integrated_page": index,
            "calibration": {
                "cal_id": page.cal_id,
                "source_document": page.source_document,
                "source_locator": page.source_locator,
                "wardrobe_stage": page.wardrobe_stage or _episode_stage(page.source_locator),
                "validation_notes": list(page.validation_notes),
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
