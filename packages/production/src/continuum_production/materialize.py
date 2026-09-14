"""Chapter materialization: the executable input for page-by-page manga production.

M2 resolves which committed documents an episode is built from. This module
turns them into one concrete, deterministic chapter:

* the chapter's page range comes from the base panel script's approved chapter
  cuts; each base page keeps its scene, beats, dialogue (speech, internal
  noise, captions), constraints ("No HUD ...") and the characters present;
* the season overlay's chapter allocation (``E1: Ch1 +1 / Ch2 +1``) and its
  episode section's ``Integrate:`` items are attached as **insertions**, each
  traced to the overlay and to the numbered beat documents it consolidates;
* where an insertion goes is a **placement decision** - data supplied by a
  person or a planner, PROPOSED or CONFIRMED - never a guess made here. An
  insertion without a decision stays ``NEEDS_PLACEMENT``, and an allocation
  the decisions do not satisfy is reported;
* integrated page numbers are provisional while earlier chapters' insertions
  are unplaced (the allocation deltas are applied as offsets).

Nothing here writes to a project document, knows a project name, or reorders
the approved story: base pages keep their order; insertions only land after
the base page their decision names. The same source blobs and decisions always
produce the same body and the same hash.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from continuum_core import canonical_json_hash

__all__ = [
    "MATERIALIZER_VERSION",
    "MaterializationInput",
    "PlacementDecision",
    "SourceText",
    "materialize_chapter",
    "page_intents",
]

MATERIALIZER_VERSION = "continuum.materialized-chapter/1"

_CUT = re.compile(
    r"^\s*-\s*\*\*Chapter\s+(?P<chapter>\d+)\s*[\u2014\u2013-]\s*approx\.?\s*pages\s*"
    r"(?P<first>\d+)\s*[\u2013-]\s*(?P<last>\d+):?\*\*:?\s*(?P<summary>.*)$",
    re.M | re.I,
)
_SCENE = re.compile(r"^#\s+(?P<title>[^#\n].*?)\s*$")
_PAGE = re.compile(
    r"^###\s+Page\s+(?P<number>\d+)(?:\s*[\u2014\u2013-]\s*(?P<label>.+?))?\s*$", re.I
)
_BULLET = re.compile(r"^\s*-\s+(?P<text>.+?)\s*$")
_SPEECH = re.compile(r"^\*\*(?P<speaker>[^*:]{1,60}):\*\*\s*`?(?P<text>.+?)`?\s*$")
_FRAGMENT = re.compile(
    r"^(?P<kind>Fragment|Noise|Caption|SFX|Thought):\s*`?(?P<text>.+?)`?\s*$", re.I
)
_ALLOCATION = re.compile(r"^\s*-\s*\*\*E(?P<episode>\d+):\*\*\s*(?P<parts>.+?)\s*$", re.M)
_ALLOCATION_PART = re.compile(r"Ch\s*(?P<chapter>\d+)\s*\+\s*(?P<delta>\d+)", re.I)
_EPISODE_SECTION = re.compile(r"^##\s+(?P<code>S\d+E\d+)\b.*$", re.M)
_BEAT = re.compile(
    r"^\s*(?P<number>\d+)\.\s+\*\*E(?P<episode>\d+)\s*[\u2014\u2013-]\s*(?P<title>.+?)\.?\*\*\s*(?P<text>.*)$",
    re.M,
)
_WORD = re.compile(r"[a-z]{4,}")

#: Generic manga-direction vocabulary -> page intent tags, used for grammar retrieval.
_INTENT_RULES: tuple[tuple[str, str], ...] = (
    (r"\bPOV\b", "pov"),
    (r"close[- ]?up|\bclose on\b|\bclose\b", "close_up"),
    (r"\blarge\b|full[- ]page|splash", "large_composition"),
    (r"back shot|from behind", "back_shot"),
    (r"\bwakes?\b|\bwaking\b|begins to wake", "awakening"),
    (r"magic|spell|\bstaff\b", "magic_effect"),
    (r"flower|field|sky|landscape|horizon|forest|lake|river", "nature_exterior"),
    (r"quiet|pause|silent|silence|observes|watches", "quiet_acting"),
    (r"disoriented|confus|searches|looks again|no idea", "confused_reaction"),
    (r"reveal", "reveal"),
    (r"chapter\s+end|chapter ends", "chapter_end"),
)


@dataclass(frozen=True, slots=True)
class SourceText:
    """A committed document's text and identity."""

    document_id: str
    text: str
    commit: str | None = None
    version: str | None = None
    #: A stable content id (e.g. the blob or file hash); recorded as lineage.
    content_hash: str | None = None

    def ref(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "commit": self.commit,
            "version": self.version,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class PlacementDecision:
    """Where an overlay insertion lands: after a base page of one chapter."""

    item_key: str
    chapter: int
    after_base_page: int
    #: PROPOSED (a planner's suggestion) or CONFIRMED (the creator's decision).
    status: str = "PROPOSED"
    author: str = ""
    note: str = ""


@dataclass(frozen=True, slots=True)
class MaterializationInput:
    project_key: str
    episode: str
    chapter: int
    panel_script: SourceText
    overlay: SourceText | None = None
    beats: tuple[SourceText, ...] = ()
    #: Other applicable sources (draft, addenda, bibles, visual packs) recorded as lineage.
    context_sources: tuple[tuple[str, SourceText], ...] = ()
    decisions: tuple[PlacementDecision, ...] = ()
    character_names: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


def page_intents(text: str, dialogue_count: int, characters: Sequence[str]) -> list[str]:
    """Structural intent tags for a page, from its own directions."""
    tags = {tag for pattern, tag in _INTENT_RULES if re.search(pattern, text, re.I)}
    if dialogue_count == 0:
        tags.add("silent")
    elif dialogue_count <= 2:
        tags.add("low_dialogue")
    else:
        tags.add("conversation")
    if len(characters) == 2:
        tags.add("two_character")
    elif len(characters) == 1:
        tags.add("single_character")
    return sorted(tags)


def _episode_number(code: str) -> int | None:
    match = re.search(r"E(\d+)$", code)
    return int(match.group(1)) if match else None


def _parse_pages(text: str) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    pages: dict[int, dict[str, Any]] = {}
    cuts = [
        {
            "chapter": int(m.group("chapter")),
            "first_page": int(m.group("first")),
            "last_page": int(m.group("last")),
            "summary": m.group("summary").strip(),
        }
        for m in _CUT.finditer(text)
    ]
    scene: str | None = None
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        heading = _PAGE.match(line)
        if heading:
            current = {
                "base_page": int(heading.group("number")),
                "label": (heading.group("label") or "").strip(),
                "scene": scene,
                "lines": [],
            }
            pages[current["base_page"]] = current
            continue
        scene_match = _SCENE.match(line)
        if scene_match and not line.startswith("##"):
            scene = scene_match.group("title").strip()
            current = None
            continue
        if line.startswith("## ") or line.startswith("---"):
            current = None if line.startswith("## ") else current
            continue
        bullet = _BULLET.match(line)
        if bullet and current is not None:
            current["lines"].append(bullet.group("text"))
    return pages, cuts


def _page_body(raw: dict[str, Any], character_names: Sequence[str]) -> dict[str, Any]:
    dialogue: list[dict[str, str]] = []
    directions: list[str] = []
    constraints: list[str] = []
    for text in raw["lines"]:
        speech = _SPEECH.match(text)
        fragment = _FRAGMENT.match(text)
        if speech:
            dialogue.append(
                {
                    "speaker": speech.group("speaker").strip(),
                    "kind": "speech",
                    "text": speech.group("text").strip().strip("`"),
                }
            )
        elif fragment:
            kind = fragment.group("kind").lower()
            dialogue.append(
                {
                    "speaker": "",
                    "kind": "internal_noise" if kind in {"fragment", "noise"} else kind,
                    "text": fragment.group("text").strip().strip("`"),
                }
            )
        elif re.match(r"^\*{0,2}No\b", text):
            constraints.append(text.strip("*").strip())
        else:
            directions.append(text)
    everything = " ".join(raw["lines"]) + " " + raw["label"]
    speakers = {d["speaker"].lower() for d in dialogue if d["speaker"]}
    present = [
        name
        for name in character_names
        if name.lower() in speakers or re.search(rf"\b{re.escape(name)}\b", everything, re.I)
    ]
    return {
        "base_page": raw["base_page"],
        "label": raw["label"],
        "scene": raw["scene"],
        "directions": directions,
        "dialogue": dialogue,
        "constraints": constraints,
        "characters": present,
        "intents": page_intents(everything, len(dialogue), present),
        "chapter_end": bool(re.search(r"chapter\s+\d*\s*end", raw["label"] + everything, re.I)),
    }


def _allocation(overlay: SourceText | None, episode: int | None) -> dict[int, int]:
    if overlay is None or episode is None:
        return {}
    for match in _ALLOCATION.finditer(overlay.text):
        if int(match.group("episode")) == episode:
            return {
                int(p.group("chapter")): int(p.group("delta"))
                for p in _ALLOCATION_PART.finditer(match.group("parts"))
            }
    return {}


def _overlay_items(overlay: SourceText | None, code: str) -> list[str]:
    if overlay is None:
        return []
    sections = list(_EPISODE_SECTION.finditer(overlay.text))
    for index, section in enumerate(sections):
        if section.group("code") != code:
            continue
        end = sections[index + 1].start() if index + 1 < len(sections) else len(overlay.text)
        body = overlay.text[section.end() : end]
        integrate = re.search(r"^Integrate:\s*$", body, re.M)
        if not integrate:
            return []
        items = []
        for line in body[integrate.end() :].splitlines():
            bullet = _BULLET.match(line)
            if bullet:
                items.append(bullet.group("text"))
            elif items and line.strip() and not line.startswith(" "):
                break
        return items
    return []


def _beats(beats: Sequence[SourceText], episode: int | None) -> list[dict[str, Any]]:
    found = []
    for doc in beats:
        for match in _BEAT.finditer(doc.text):
            if episode is not None and int(match.group("episode")) == episode:
                found.append(
                    {
                        "number": int(match.group("number")),
                        "title": match.group("title").strip(),
                        "text": match.group("text").strip(),
                        "source": doc.ref(),
                    }
                )
    return found


def materialize_chapter(given: MaterializationInput) -> dict[str, Any]:
    """The materialized chapter body; ``body["hash"]`` is stable for the same inputs."""
    pages, cuts = _parse_pages(given.panel_script.text)
    cut = next((c for c in cuts if c["chapter"] == given.chapter), None)
    warnings: list[str] = []
    if cut is None:
        raise ValueError(f"the panel script declares no cut for chapter {given.chapter}")
    episode_number = _episode_number(given.episode)
    allocation = _allocation(given.overlay, episode_number)
    beats = _beats(given.beats, episode_number)

    items: list[dict[str, Any]] = []
    for index, text in enumerate(_overlay_items(given.overlay, given.episode), start=1):
        words = set(_WORD.findall(text.lower()))
        related = [
            {"number": b["number"], "title": b["title"], "source": b["source"]}
            for b in beats
            if len(words & set(_WORD.findall((b["title"] + " " + b["text"]).lower()))) >= 3
        ]
        items.append(
            {
                "item_key": f"{given.episode.lower()}-overlay-{index}",
                "text": text,
                "overlay": given.overlay.ref() if given.overlay else None,
                "source_beats": related,
            }
        )
    by_key = {item["item_key"]: item for item in items}
    decisions = {d.item_key: d for d in given.decisions}
    for key in decisions:
        if key not in by_key:
            warnings.append(f"placement decision for unknown insertion {key}")

    placed_here: dict[int, list[dict[str, Any]]] = {}
    unplaced = []
    offsets_before = sum(delta for ch, delta in allocation.items() if ch < given.chapter)
    placed_before = 0
    for item in items:
        decision = decisions.get(item["item_key"])
        if decision is None:
            unplaced.append({**item, "status": "NEEDS_PLACEMENT"})
            continue
        entry = {
            **item,
            "status": decision.status,
            "placement": {
                "chapter": decision.chapter,
                "after_base_page": decision.after_base_page,
                "author": decision.author,
                "note": decision.note,
            },
        }
        if decision.chapter == given.chapter:
            if not cut["first_page"] <= decision.after_base_page <= cut["last_page"]:
                warnings.append(
                    f"{item['item_key']} is placed after page {decision.after_base_page}, "
                    f"outside chapter {given.chapter}"
                )
            placed_here.setdefault(decision.after_base_page, []).append(entry)
        elif decision.chapter < given.chapter:
            placed_before += 1
    placed_count = sum(len(v) for v in placed_here.values())
    expected = allocation.get(given.chapter)
    if expected is not None and placed_count != expected:
        warnings.append(
            f"the overlay allocates +{expected} page(s) to chapter {given.chapter}; "
            f"{placed_count} insertion(s) are placed here"
        )
    provisional = bool(unplaced) or placed_before != offsets_before

    sequence: list[dict[str, Any]] = []
    offset = offsets_before
    for base_page in range(cut["first_page"], cut["last_page"] + 1):
        raw = pages.get(base_page)
        if raw is None:
            warnings.append(f"base page {base_page} is missing from the panel script")
            continue
        body = _page_body(raw, given.character_names)
        sequence.append(
            {
                **body,
                "origin": "base",
                "integrated_page": base_page + offset,
                "lineage": {**given.panel_script.ref(), "base_page": base_page},
            }
        )
        for insertion in placed_here.get(base_page, []):
            offset += 1
            text = insertion["text"]
            present = [
                n for n in given.character_names if re.search(rf"\b{re.escape(n)}\b", text, re.I)
            ]
            sequence.append(
                {
                    "base_page": None,
                    "label": "overlay insertion",
                    "scene": body["scene"],
                    "directions": [text],
                    "dialogue": [],
                    "constraints": [],
                    "characters": present,
                    "intents": page_intents(text, 0, present),
                    "chapter_end": False,
                    "origin": "overlay",
                    "integrated_page": base_page + offset,
                    "insertion": {
                        "item_key": insertion["item_key"],
                        "status": insertion["status"],
                        "placement": insertion["placement"],
                    },
                    "lineage": {
                        "overlay": insertion["overlay"],
                        "source_beats": insertion["source_beats"],
                        "after_base_page": base_page,
                    },
                }
            )
    # A chapter end moves to the last page if an insertion follows the base ending.
    for index, page in enumerate(sequence):
        page["sequence"] = index + 1
        page["page_key"] = f"{given.episode.lower()}-c{given.chapter}-s{index + 1:03d}"
        page["page_hash"] = canonical_json_hash(
            {k: v for k, v in page.items() if k not in {"sequence", "page_key", "page_hash"}}
        )

    characters = sorted({name for page in sequence for name in page["characters"]})
    body = {
        "schema": MATERIALIZER_VERSION,
        "project_key": given.project_key,
        "episode": given.episode,
        "chapter": given.chapter,
        "chapter_cut": cut,
        "allocation": {str(k): v for k, v in sorted(allocation.items())},
        "page_count": len(sequence),
        "integrated_numbering_provisional": provisional,
        "characters": characters,
        "pages": sequence,
        "insertions": {
            "placed_in_chapter": [
                {"item_key": i["item_key"], "status": i["status"], "placement": i["placement"]}
                for group in placed_here.values()
                for i in group
            ],
            "unplaced": [
                {"item_key": i["item_key"], "text": i["text"], "source_beats": i["source_beats"]}
                for i in unplaced
            ],
        },
        "sources": {
            "panel_script": given.panel_script.ref(),
            "overlay": given.overlay.ref() if given.overlay else None,
            "beats": [b.ref() for b in given.beats],
            "context": [{"role": role, **doc.ref()} for role, doc in given.context_sources],
        },
        "decisions": [
            {
                "item_key": d.item_key,
                "chapter": d.chapter,
                "after_base_page": d.after_base_page,
                "status": d.status,
                "author": d.author,
                "note": d.note,
            }
            for d in sorted(given.decisions, key=lambda d: d.item_key)
        ],
        "warnings": sorted(set(warnings)),
    }
    body["hash"] = canonical_json_hash(body)
    return body
