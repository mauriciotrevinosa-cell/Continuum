"""Regression coverage for the committed M3 calibration document parser."""

from __future__ import annotations

from pathlib import Path

from continuum_production.calibration import parse_calibration

CALIBRATION_DOC = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "creative"
    / "THE_ARRIVALS_S1_PRODUCTION_CALIBRATION_CHAPTER_v0.1.md"
)


def test_real_calibration_document_parses_all_18_pages_and_extra_bullets() -> None:
    # The committed creative document is UTF-8; utf-8-sig also tolerates a BOM.
    pages = parse_calibration(CALIBRATION_DOC.read_text(encoding="utf-8-sig"))

    assert [page.cal_id for page in pages] == [f"CAL-{index:02d}" for index in range(1, 19)]

    by_id = {page.cal_id: page for page in pages}
    assert by_id["CAL-08"].wardrobe_stage == "E1"
    assert by_id["CAL-08"].extra["required_garment_truth"] == [
        "M-J1 white long-sleeve personalized jersey;",
        "back marking `MAU T`;",
        "number `5`;",
        "readable story-critical personalization;",
        (
            "use approved/creator-grounded reference treatment rather than inventing "
            "sponsor/logo detail."
        ),
    ]
    assert by_id["CAL-13"].extra["frieren_active_wardrobe_set_for_this_calibration_page"] == [
        "Mau-owned M-H1 orange/black McLaren hoodie;",
        "Mau-owned M-A2 white McLaren cap;",
        "Frieren-owned comfortable short bottoms.",
    ]

    assert by_id["CAL-17"].characters == (
        "Mau",
        "Sukuna",
        "Mahoraga",
        "Yuta",
        "Frieren",
        "Okarun",
        "Rimuru",
    )
    assert len(by_id["CAL-17"].extra["page_construction"]) == 5
    assert by_id["CAL-18"].characters == ("Mau", "Frieren")
    assert len(by_id["CAL-18"].extra["page_construction"]) == 5
