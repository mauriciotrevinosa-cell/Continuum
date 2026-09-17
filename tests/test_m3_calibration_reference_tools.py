from __future__ import annotations

import json

from scripts.bootstrap_calibration_cast import DEFAULT_ROSTER, _characters
from scripts.import_character_pack import _rule, _setting


def test_calibration_roster_marks_mahoraga_as_monster() -> None:
    roster = json.loads(DEFAULT_ROSTER.read_text(encoding="utf-8"))
    specs = _characters(roster, "all")

    assert len(specs) == 19
    mahoraga = next(spec for spec in specs if spec["name"] == "Mahoraga")
    assert mahoraga["subject_kind"] == "MONSTER"
    assert mahoraga["calibration_pages"] == ["CAL-17"]


def test_character_pack_rules_can_keep_fanart_supplemental() -> None:
    spec = {
        "reference_class": "CANON",
        "reference_origin": "SOURCE",
        "uses": ["IDENTITY"],
        "folders": {
            "fanart_variants/": {
                "aspects": ["FULL_BODY", "POSE"],
                "reference_class": "MOOD",
                "reference_origin": "FAN_ART",
                "uses": ["STYLE"],
            }
        },
    }

    rule = _rule(spec, "fanart_variants/angle.png")

    assert rule is not None
    assert _setting(rule, spec, "reference_class", "CANON") == "MOOD"
    assert _setting(rule, spec, "reference_origin", "USER_CREATED") == "FAN_ART"
    assert _setting(rule, spec, "uses", []) == ["STYLE"]
