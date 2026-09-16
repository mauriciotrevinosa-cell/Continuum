"""Regression coverage for the committed M3 calibration document parser."""

from pathlib import Path

from continuum_production.calibration import parse_calibration


CALIBRATION_DOC = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "creative"
    / "THE_ARRIVALS_S1_PRODUCTION_CALIBRATION_CHAPTER_v0.1.md"
)


def test_real_calibration_document_parses_all_16_pages_and_extra_bullets() -> None:
    pages = parse_calibration(CALIBRATION_DOC.read_text(encoding="utf-8-sig"))

    assert [page.cal_id for page in pages] == [f"CAL-{index:02d}" for index in range(1, 17)]

    by_id = {page.cal_id: page for page in pages}
    assert by_id["CAL-08"].wardrobe_stage == "E1"
    assert by_id["CAL-08"].extra["required_garment_truth"] == [
        "M-J1 white long-sleeve personalized jersey;",
        "back marking `MAU T`;",
        "number `5`;",
        "readable story-critical personalization;",
        "use approved/creator-grounded reference treatment rather than inventing sponsor/logo detail.",
    ]
    assert by_id["CAL-13"].extra["frieren_active_wardrobe_set_for_this_calibration_page"] == [
        "Mau-owned M-H1 orange/black McLaren hoodie;",
        "Mau-owned M-A2 white McLaren cap;",
        "Frieren-owned comfortable short bottoms.",
    ]
