"""Focused parser regressions for committed M3 calibration documents."""

from continuum_production.calibration import parse_calibration


def test_explicit_wardrobe_stage_drops_sentence_punctuation() -> None:
    text = """# Demo Calibration

## CAL-01 — Wardrobe detail

**Source:** `DEMO_S1E1_PANEL_SCRIPT_v0.1.md` — E1 Page 43.
**Source content:** Wardrobe detail.

**Wardrobe stage:** E1.
"""
    pages = parse_calibration(text)
    assert len(pages) == 1
    assert pages[0].wardrobe_stage == "E1"
