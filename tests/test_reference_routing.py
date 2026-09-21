"""Purpose-aware routing: what each reference is asked to teach, and why.

The failure this prevents is a render packet assembled from "whatever is about
this panel": a technique page becoming a character's face, a style exemplar
redefining identity, or an unrelated source page travelling to a GPU because it
happened to exist. Every rule here is checked on the pure router, with no
database and no franchise, so it holds for any project.
"""

from __future__ import annotations

from continuum_core.references import PanelStage
from continuum_core.routing import (
    PURPOSE_RULES,
    STAGE_NEEDS,
    Candidate,
    Influence,
    PurposeNeed,
    ReferencePurpose,
    record,
    route,
)


def _c(reference_id: str, role: str, **kwargs: object) -> Candidate:
    return Candidate(reference_id=reference_id, role=role, **kwargs)  # type: ignore[arg-type]


def _by_id(packet: object) -> dict[str, str]:
    return {e.reference_id: e.purpose.value for e in packet.selected}  # type: ignore[attr-defined]


def test_a_style_reference_never_becomes_identity() -> None:
    style = _c("house-style", "STYLE", facets=frozenset({"LINEART"}))
    face = _c(
        "hero-face", "CANON", character="Hero", authority="PRIMARY_SOURCE", status="CONFIRMED"
    )
    packet = route(STAGE_NEEDS[PanelStage.DRAWING], [style, face], cast=["Hero"])
    routed = _by_id(packet)
    assert routed["hero-face"] == "IDENTITY"
    assert routed.get("house-style") != "IDENTITY"
    assert packet.identity == {"Hero": ["hero-face"]}


def test_a_character_reference_never_becomes_a_style_authority() -> None:
    face = _c("hero-face", "CANON", character="Hero", status="CONFIRMED")
    packet = route([PurposeNeed(ReferencePurpose.MANGA_LINE_LANGUAGE, 2)], [face], cast=["Hero"])
    assert packet.selected == ()
    (rejected,) = packet.rejected
    assert "character evidence is never routed" in rejected.reason


def test_unrelated_source_material_is_not_selected_just_because_it_exists() -> None:
    """Availability is not relevance: nothing recorded about it matches."""
    stranger = _c("other-world-page", "TECHNIQUE", series="other-world")
    useful = _c("forest-page", "ENVIRONMENT", facets=frozenset({"BACKGROUND_TREATMENT"}))
    packet = route(
        STAGE_NEEDS[PanelStage.COMPOSITION],
        [stranger, useful],
        relevant_series=["this-world"],
    )
    assert _by_id(packet) == {"forest-page": "ENVIRONMENT"}
    (rejected,) = [r for r in packet.rejected if r.reference_id == "other-world-page"]
    assert "unrelated source material" in rejected.reason


def test_a_reference_from_another_world_still_counts_when_it_teaches_something() -> None:
    """A technique page earns its place by what it teaches, not by its origin."""
    teacher = _c("magic-page", "TECHNIQUE", series="other-world", facets=frozenset({"MAGIC", "FX"}))
    packet = route(STAGE_NEEDS[PanelStage.FX], [teacher], relevant_series=["this-world"])
    assert _by_id(packet) == {"magic-page": "MAGIC_EFFECT"}


def test_every_selection_records_its_purpose_and_what_it_may_influence() -> None:
    inn = _c(
        "inn",
        "ENVIRONMENT",
        facets=frozenset({"ESTABLISHING_SHOT"}),
        standing="PREFERRED_FOR_CURRENT_LOOK",
        why=("preferred for the project's current look",),
    )
    packet = route(STAGE_NEEDS[PanelStage.COMPOSITION], [inn])
    (entry,) = packet.selected
    assert entry.purpose is ReferencePurpose.ENVIRONMENT
    assert Influence.LAYOUT.value in entry.influences
    assert Influence.IDENTITY.value not in entry.influences
    assert entry.image_conditioned is True
    assert any("selected to teach" in why for why in entry.why)
    written = record("COMPOSITION", packet)
    assert written["selected"][0]["purpose"] == "ENVIRONMENT"
    assert written["stage"] == "COMPOSITION"


def test_the_current_outfit_wins_over_an_older_one() -> None:
    old = _c("old-coat", "WARDROBE", character="Hero", outfit_id="coat-1", order=0)
    now = _c("winter-coat", "WARDROBE", character="Hero", outfit_id="coat-2", order=9)
    packet = route(
        [PurposeNeed(ReferencePurpose.WARDROBE, 1)],
        [old, now],
        cast=["Hero"],
        current_outfits={"Hero": "coat-2"},
    )
    assert _by_id(packet) == {"winter-coat": "WARDROBE"}


def test_an_accessory_scale_lock_is_carried_but_never_image_conditioned() -> None:
    brooch = _c(
        "brooch-scale",
        "WARDROBE",
        character="Hero",
        prop_id="prop-1",
        declared=frozenset({"ACCESSORY_SCALE"}),
    )
    packet = route([PurposeNeed(ReferencePurpose.ACCESSORY_SCALE, 1)], [brooch], cast=["Hero"])
    (entry,) = packet.selected
    assert entry.purpose is ReferencePurpose.ACCESSORY_SCALE
    assert entry.image_conditioned is False
    assert entry.influences == (Influence.DETAIL.value,)


def test_identity_is_reported_as_unmet_when_a_cast_member_has_no_evidence() -> None:
    packet = route(
        STAGE_NEEDS[PanelStage.DRAWING],
        [_c("hero-face", "CANON", character="Hero", status="CONFIRMED")],
        cast=["Hero", "Stranger"],
    )
    assert any("Stranger: no identity evidence" in gap for gap in packet.unmet)
    assert not any("Hero: no identity" in gap for gap in packet.unmet)


def test_an_unconfirmed_candidate_never_grounds_identity() -> None:
    packet = route(
        [PurposeNeed(ReferencePurpose.IDENTITY, 1, required_for_cast=True)],
        [_c("maybe-hero", "CANON", character="Hero", status="CANDIDATE")],
        cast=["Hero"],
    )
    assert packet.selected == ()
    assert "an unconfirmed candidate" in packet.rejected[0].reason


def test_a_reference_serves_one_purpose_and_budgets_are_honoured_in_stage_order() -> None:
    a = _c("a", "STYLE", facets=frozenset({"LINEART", "SCREENTONE"}), order=0)
    b = _c("b", "STYLE", facets=frozenset({"LINEART"}), order=1)
    c = _c("c", "STYLE", facets=frozenset({"LINEART"}), order=2)
    packet = route(STAGE_NEEDS[PanelStage.LINE], [a, b, c])
    assert _by_id(packet) == {"a": "MANGA_LINE_LANGUAGE", "b": "MANGA_LINE_LANGUAGE"}
    assert any(r.reference_id == "c" and "budget" in r.reason for r in packet.rejected)


def test_routing_is_deterministic() -> None:
    pool = [
        _c("z", "ENVIRONMENT", facets=frozenset({"BACKGROUND_TREATMENT"}), order=1),
        _c("a", "ENVIRONMENT", facets=frozenset({"BACKGROUND_TREATMENT"}), order=1),
    ]
    first = route(STAGE_NEEDS[PanelStage.COMPOSITION], pool)
    second = route(STAGE_NEEDS[PanelStage.COMPOSITION], list(reversed(pool)))
    assert _by_id(first) == _by_id(second) == {"a": "ENVIRONMENT"}


def test_only_identity_purposes_bear_identity() -> None:
    bearing = {p.value for p, rule in PURPOSE_RULES.items() if rule.identity_bearing}
    assert bearing == {"IDENTITY", "BODY"}
    for rule in PURPOSE_RULES.values():
        if rule.identity_bearing:
            assert rule.character_scoped, rule.purpose
        else:
            assert Influence.IDENTITY not in rule.influences, rule.purpose


def test_every_stage_asks_for_something_and_only_for_known_purposes() -> None:
    for stage in PanelStage:
        needs = STAGE_NEEDS[stage]
        assert needs, stage
        assert all(need.purpose in PURPOSE_RULES for need in needs)
        assert all(need.budget > 0 for need in needs)
