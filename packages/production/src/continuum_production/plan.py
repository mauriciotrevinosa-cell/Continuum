"""Page plans and full-page source references (M3).

Pure functions over a materialized page:

* :func:`page_plan` - who appears (from the script's names *and* its dialogue
  speakers), the primary and supporting characters, what the page is mostly
  about, its setting tags, and what is uncertain. A person's cast override is
  applied last and recorded.
* :func:`page_references` - complete source manga pages chosen for a page by
  **role**, each saying why it was chosen and what it may teach:

  - GRAMMAR: how a page of this kind is structured (panel hierarchy, reading
    flow, silence);
  - TECHNIQUE: how an artistic problem is solved (close-up acting, page
    impact, silence, effects, dialogue staging, exterior treatment);
  - ENVIRONMENT: wide establishing layouts from the source world of the
    characters on the page.

  None of these ever says what a character looks like: a full page of another
  series can be an excellent grammar reference for a scene and is still never
  identity evidence. Technique and environment are inferred from measured
  layout, so every such reference is a CANDIDATE and says so. They teach
  abstraction, never a composition to copy.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from continuum_production.corpus import setting_tags

__all__ = [
    "PRIMARY_INTENT_ORDER",
    "TECHNIQUE_NEEDS",
    "page_plan",
    "page_references",
    "source_page_image",
]

PRIMARY_INTENT_ORDER = (
    "chapter_end",
    "reveal",
    "magic_effect",
    "large_composition",
    "back_shot",
    "close_up",
    "awakening",
    "confused_reaction",
    "quiet_acting",
    "conversation",
    "nature_exterior",
    "pov",
    "silent",
    "low_dialogue",
)


_PANEL_DIRECTION = re.compile(
    r"^(?:PAGE CONSTRUCTION:\s*)?Panel\s+(?P<number>\d+)\s*:\s*(?P<direction>.+)$",
    re.I,
)


def _panel_shot(direction: str) -> str:
    lowered = direction.lower()
    if "close" in lowered:
        return "CLOSE"
    if any(token in lowered for token in ("wide", "establish", "full table", "exterior")):
        return "WIDE"
    if any(token in lowered for token in ("large", "impact", "splash")):
        return "IMPACT"
    if any(token in lowered for token in ("medium", "two-shot", "two shot")):
        return "MEDIUM"
    return "STANDARD"


def _render_panels(
    page: dict[str, Any], present: Sequence[str], primary: str | None
) -> list[dict[str, Any]]:
    """Return creator-authored render beats without inventing page structure."""
    directions = [str(value).strip() for value in page.get("directions") or []]
    explicit: list[tuple[int, str]] = []
    for direction in directions:
        match = _PANEL_DIRECTION.match(direction)
        if match:
            explicit.append((int(match.group("number")), match.group("direction").strip()))
    explicit.sort(key=lambda item: item[0])

    beats = explicit
    if not beats:
        source = next(
            (
                direction
                for direction in directions
                if direction
                and not direction.startswith("MUST SHOW:")
                and not direction.startswith("DO NOT:")
            ),
            "",
        )
        beats = [(1, source or str(page.get("label") or "page composition"))]

    out: list[dict[str, Any]] = []
    for number, direction in beats:
        named = [name for name in present if _mentions(direction, name)]
        lowered = direction.lower()
        if not named and len(present) == 1:
            named = list(present)
        elif not named and any(
            token in lowered
            for token in ("everyone", "all ", "household", "group", "ensemble", "cast")
        ):
            named = list(present)
        elif not named and primary and len(beats) == 1:
            named = list(present)
        out.append(
            {
                "number": number,
                "direction": direction,
                "characters": named,
                "shot": _panel_shot(direction),
                "emphasis": (
                    "HIGH"
                    if any(token in lowered for token in ("large", "impact", "splash", "final"))
                    else "NORMAL"
                ),
            }
        )
    return out


def _mentions(text: str, name: str) -> int:
    first = re.escape(name.split()[0])
    return len(re.findall(rf"\b{first}\b", text, re.I))


def page_plan(
    page: dict[str, Any], known: Sequence[str], override: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Who appears on the page and what it is about, derived from its script.

    Normal story material is conservative: only names already known to the
    Character Vault enter the inferred cast. Calibration pages are different:
    their explicit ``characters`` field is creator-authored test data, so those
    declared names must survive planning even when their Vault profiles do not
    exist yet. Grounding validation then reports and blocks the missing profile
    instead of silently deleting the character from the sampler page.
    """
    override = override or {}
    by_token = {name.split()[0].lower(): name for name in known}
    by_token.update({name.lower(): name for name in known})
    declared = [str(name).strip() for name in page.get("characters") or [] if str(name).strip()]
    calibration = page.get("origin") == "calibration"
    if calibration:
        for name in declared:
            by_token.setdefault(name.split()[0].lower(), name)
            by_token.setdefault(name.lower(), name)
    directions = " ".join(str(d) for d in page.get("directions") or [])
    speakers = [
        str(line.get("speaker") or "")
        for line in page.get("dialogue") or []
        if line.get("kind") != "internal_noise" and str(line.get("speaker") or "").strip()
    ]
    mapped: list[str] = []
    unmapped: list[str] = []
    for speaker in speakers:
        name = by_token.get(speaker.strip().lower()) or by_token.get(
            speaker.strip().split()[0].lower()
        )
        (mapped if name else unmapped).append(name or speaker)
    script = declared if calibration else [c for c in declared if c in known]
    present = list(dict.fromkeys([*script, *mapped]))
    removed = [c for c in override.get("remove") or [] if c in present]
    present = [c for c in present if c not in removed]
    added = [c for c in override.get("add") or [] if c in known and c not in present]
    present += added
    weight = {
        name: _mentions(directions, name) + 2 * mapped.count(name) + (1 if name in script else 0)
        for name in present
    }
    primary = override.get("primary") if override.get("primary") in present else None
    if primary is None and present:
        primary = max(present, key=lambda n: (weight[n], -present.index(n)))
    uncertain = [f"speaker {s!r} is not a known character" for s in dict.fromkeys(unmapped)]
    if not present and (speakers or directions):
        uncertain.append("no known character is named on this page")
    mapped_not_in_script = [n for n in dict.fromkeys(mapped) if n not in script]
    uncertain += [f"{n} speaks but is not named in the directions" for n in mapped_not_in_script]
    intents = list(page.get("intents") or [])
    primary_intent = next((i for i in PRIMARY_INTENT_ORDER if i in intents), None)
    return {
        "characters_present": present,
        "primary_character": primary,
        "supporting_characters": [c for c in present if c != primary],
        "speakers": list(dict.fromkeys(mapped + unmapped)),
        "unmapped_speakers": list(dict.fromkeys(unmapped)),
        "weights": weight,
        "cast_source": {
            "script": script,
            "dialogue": list(dict.fromkeys(mapped)),
            "override": {"add": added, "remove": removed, "primary": override.get("primary")}
            if override
            else None,
        },
        "uncertain": uncertain,
        "scene": page.get("scene"),
        "intents": intents,
        "primary_intent": primary_intent,
        "environment_tags": setting_tags(f"{directions} {page.get('scene') or ''}"),
        "dialogue_lines": sum(
            1 for line in page.get("dialogue") or [] if line.get("kind") != "internal_noise"
        ),
        "silent": not any(
            line.get("kind") != "internal_noise" for line in page.get("dialogue") or []
        ),
        "constraints": list(page.get("constraints") or []),
        "render_panels": _render_panels(page, present, primary),
    }


def source_page_image(unit_key: str | None, offset: int | None) -> str | None:
    if not unit_key or offset is None:
        return None
    return f"/production/source-pages/{unit_key}/{offset}/image"


#: (need id, page intents that call for it, what it teaches in words, teaches, layout score)
TECHNIQUE_NEEDS: tuple[tuple[str, frozenset[str], str, tuple[str, ...]], ...] = (
    (
        "close_up_acting",
        frozenset({"close_up", "quiet_acting", "confused_reaction", "awakening"}),
        "close-up acting and restrained expression",
        ("facial acting", "reaction timing", "camera distance"),
    ),
    (
        "page_impact",
        frozenset({"large_composition", "chapter_end", "reveal", "back_shot"}),
        "large composition and page impact",
        ("panel hierarchy", "page turn", "character staging"),
    ),
    (
        "silence",
        frozenset({"silent", "low_dialogue"}),
        "silence and negative space",
        ("silence", "negative space", "pacing"),
    ),
    (
        "effects",
        frozenset({"magic_effect"}),
        "effects, blacks and tones",
        ("effects", "blacks", "screentones"),
    ),
    (
        "dialogue_staging",
        frozenset({"conversation"}),
        "dialogue staging across panels",
        ("dialogue density", "shot sequence", "reading flow"),
    ),
    (
        "exterior",
        frozenset({"nature_exterior"}),
        "exterior and background treatment",
        ("background simplification", "perspective", "environment treatment"),
    ),
)


def _technique_score(need: str, c: Any) -> float:
    pc = int(c.panel_count)
    share, neg, ink = float(c.largest_panel_share), float(c.negative_space), float(c.ink_density)
    if need == "close_up_acting":
        return 1.0 - abs(pc - 5) * 0.15 - abs(share - 0.3)
    if need == "page_impact":
        return share + (0.3 if pc <= 3 else 0.0)
    if need == "silence":
        return neg + (0.2 if pc <= 4 else 0.0)
    if need == "effects":
        return ink
    if need == "dialogue_staging":
        return min(pc, 8) / 8
    return share * 0.6 + (1 - neg) * 0.4


def _layout_words(c: Any) -> str:
    return (
        f"{c.panel_count} panels, largest {round(c.largest_panel_share * 100)}%, "
        f"negative space {round(c.negative_space * 100)}%, ink {round(c.ink_density * 100)}%"
    )


def _entry(
    c: Any, role: str, why: list[str], teaches: Sequence[str], world: set[str]
) -> dict[str, Any]:
    same_world = c.series_key in world
    return {
        "role": role,
        "locator": c.locator,
        "series_key": c.series_key,
        "label": c.label,
        "unit_key": getattr(c, "unit_key", None),
        "page_offset": getattr(c, "page_offset", None),
        "image": source_page_image(getattr(c, "unit_key", None), getattr(c, "page_offset", None)),
        "source": "source manga page"
        + (" - same source world as the cast" if same_world else " - another work"),
        "authority": "SOURCE_PAGE",
        "status": "CANDIDATE" if role != "GRAMMAR" else "LAYOUT_MATCH",
        "identity_evidence": False,
        "why": why,
        "teaches": list(teaches),
        "structure": {
            "panel_count": c.panel_count,
            "largest_panel_share": c.largest_panel_share,
            "negative_space": c.negative_space,
            "ink_density": c.ink_density,
        },
    }


def page_references(
    intents: Sequence[str],
    grammar: Sequence[dict[str, Any]],
    candidates: Sequence[Any],
    world_candidates: Sequence[Any],
    *,
    world_series: set[str],
    environment_wanted: bool,
    technique_limit: int = 3,
    environment_limit: int = 2,
    recent_usage: Mapping[str, int] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Technique and environment pages to go with the page's grammar pages."""
    used = {g["locator"] for g in grammar}
    by_locator = {c.locator: c for c in [*candidates, *world_candidates]}
    grammar_out = []
    for g in grammar:
        c = by_locator.get(g["locator"])
        if c is None:
            continue
        grammar_out.append(
            {
                **_entry(
                    c,
                    "GRAMMAR",
                    [
                        f"page structure fits this page's intents ({', '.join(intents) or 'none'})",
                        _layout_words(c),
                    ],
                    ("panel hierarchy", "reading flow", "dialogue density", "silence"),
                    world_series,
                ),
                "score": g.get("score"),
            }
        )
    tags = set(intents)
    technique: list[dict[str, Any]] = []
    seen_series: set[str | None] = set()
    for need, calls, words, teaches in TECHNIQUE_NEEDS:
        if len(technique) >= technique_limit or not (tags & calls):
            continue
        ranked = sorted(
            (c for c in candidates if c.locator not in used),
            key=lambda c: (
                -_technique_score(need, c) + 0.18 * (recent_usage or {}).get(c.locator, 0),
                c.series_key in seen_series,
                c.locator,
            ),
        )
        if not ranked:
            continue
        chosen = ranked[0]
        used.add(chosen.locator)
        seen_series.add(chosen.series_key)
        technique.append(
            _entry(
                chosen,
                "TECHNIQUE",
                [
                    f"this page needs {words} ({', '.join(sorted(tags & calls))})",
                    f"layout suits it: {_layout_words(chosen)}",
                    "technique inferred from layout - content not verified",
                ],
                teaches,
                world_series,
            )
        )
    environment: list[dict[str, Any]] = []
    if environment_wanted:
        wide = sorted(
            (
                c
                for c in world_candidates
                if c.locator not in used and c.largest_panel_share >= 0.45
            ),
            key=lambda c: (-c.largest_panel_share, c.locator),
        )
        for c in wide[:environment_limit]:
            used.add(c.locator)
            environment.append(
                _entry(
                    c,
                    "ENVIRONMENT",
                    [
                        "wide establishing layout from the cast's source world",
                        _layout_words(c),
                        "environment content not verified - the setting canon governs",
                    ],
                    ("perspective", "atmosphere", "background treatment"),
                    world_series,
                )
            )
    return {"grammar": grammar_out, "technique": technique, "environment_pages": environment}
