"""Regression tests for ensemble Comfy budgeting and calibration prompt locks."""

from __future__ import annotations

from pathlib import Path

from continuum_core.references import RenderOutput
from continuum_production.calibration import calibration_body, parse_calibration
from continuum_providers.artwork import (
    ArtworkCapabilities,
    ArtworkReference,
    PageRenderRequest,
    capability_gaps,
)
from continuum_providers.comfy import _select_identity_references

CALIBRATION_DOC = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "creative"
    / "THE_ARRIVALS_S1_PRODUCTION_CALIBRATION_CHAPTER_v0.1.md"
)


def _reference(character: str, index: int) -> ArtworkReference:
    return ArtworkReference(
        role="CANON",
        reference_id=f"{character}-{index}",
        data=b"reference",
        character=character,
        provenance={"status": "CONFIRMED"},
    )


def _request(references: tuple[ArtworkReference, ...]) -> PageRenderRequest:
    return PageRenderRequest(
        page_key="ensemble",
        width=1024,
        height=1456,
        seed=7,
        page={"characters": ["A", "B", "C", "D", "E"], "directions": []},
        plan={},
        continuity={},
        references=references,
        settings={"workflow": "page.v1"},
    )


def _caps(limit: int = 12) -> ArtworkCapabilities:
    return ArtworkCapabilities(
        output=RenderOutput.ARTWORK_CANDIDATE,
        available=True,
        max_reference_images=limit,
        identity_conditioning=True,
        sibling_finishes=True,
        seeded=True,
        max_edge=2048,
    )


def test_large_bundle_is_budgeted_instead_of_blocked() -> None:
    references = tuple(
        _reference(character, index)
        for character in ("A", "B", "C", "D", "E")
        for index in range(6)
    )
    assert len(references) == 30
    assert capability_gaps(_caps(), _request(references)) == []

    selected = _select_identity_references(references, 12)
    assert len(selected) == 12
    selected_characters = [reference.character for reference in selected]
    assert set(selected_characters) == {"A", "B", "C", "D", "E"}
    counts = {name: selected_characters.count(name) for name in set(selected_characters)}
    assert max(counts.values()) - min(counts.values()) <= 1


def test_identity_budget_blocks_only_when_every_character_cannot_get_one_slot() -> None:
    references = tuple(_reference(f"C{index:02d}", 0) for index in range(13))
    gaps = capability_gaps(_caps(12), _request(references))
    assert len(gaps) == 1
    assert "identity coverage for 13 characters" in gaps[0]
    assert "at most 12 reference images" in gaps[0]


def test_real_calibration_validation_becomes_render_direction_and_failure_constraint() -> None:
    pages = parse_calibration(CALIBRATION_DOC.read_text(encoding="utf-8-sig"))
    body = calibration_body(
        "the-arrivals",
        "S1CAL",
        1,
        "calibration-doc",
        "0.1",
        "a" * 64,
        pages,
        tuple(
            sorted(
                {
                    character
                    for page in pages
                    for character in page.characters
                }
            )
        ),
    )
    cal01 = body["pages"][0]
    assert any("roughly five small abandoned houses" in item for item in cal01["directions"])
    assert any(item.startswith("MUST SHOW:") for item in cal01["directions"])
    assert any("dense roofscape" in item for item in cal01["constraints"])

    cal17 = body["pages"][16]
    assert any("PAGE CONSTRUCTION: Panel 1" in item for item in cal17["directions"])
    assert any("Yuta or Okarun carries the wrong person" in item for item in cal17["constraints"])
