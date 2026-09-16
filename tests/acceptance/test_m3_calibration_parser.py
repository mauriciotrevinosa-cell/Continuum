"""Focused parser regressions for committed M3 calibration documents."""

from continuum_production.calibration import parse_calibration
from continuum_production.plan import page_plan


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


def test_character_field_excludes_lowercase_scene_description() -> None:
    text = """# Demo Calibration

## CAL-01 — Action

**Source:** `DEMO_S1E17_PANEL_SCRIPT_v0.1.md` — E17 Page 6.
**Source content:** A creature bursts from the right.

**Characters:** Mau, Yuta, one ordinary hostile creature.
"""
    pages = parse_calibration(text)
    assert len(pages) == 1
    assert pages[0].characters == ("Mau", "Yuta")


def test_calibration_plan_preserves_declared_cast_missing_from_vault() -> None:
    page = {
        "origin": "calibration",
        "characters": ["Mau", "Frieren"],
        "directions": ["Frieren leans lightly against Mau."],
        "dialogue": [],
        "intents": [],
        "constraints": [],
        "scene": "",
    }

    plan = page_plan(page, known=[])

    assert plan["characters_present"] == ["Mau", "Frieren"]
    assert plan["cast_source"]["script"] == ["Mau", "Frieren"]
