"""M3: page plans, full-page references by role, chapter technical preview, QA, visual origin.

Pinned with invented content (D-18 / A-05):

* the cast is derived from the script's names and dialogue speakers; unknown
  speakers are flagged; a person's override is applied and recorded;
* full source pages are returned by role - grammar, technique, environment -
  each with why and what it teaches, and never as identity evidence;
* a chapter technical preview renders every page with the test backend, is
  never approved, never feeds continuity and leaves the sample run untouched;
* chapter QA flags problems without fixing them;
* an image acquired as fan art can be recorded as official anime: its
  acquisition provenance is kept and it gains official authority, still a
  candidate until confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from continuum_core.references import (
    CharacterAspect,
    ReferenceClass,
    ReferenceOrigin,
    ReviewDecision,
    RoughPurpose,
)
from continuum_library import CatalogInputError, ReferenceCatalog, ReferenceSpec
from continuum_production.corpus import CharacterCorpus
from continuum_production.plan import page_plan, page_references
from continuum_worker.main import Worker
from sqlalchemy.orm import Session

from tests.acceptance import test_m3_page_production as m3
from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import World, picture
from tests.renderers import artwork_page_registry

pytestmark = pytest.mark.requires_db

world = rough.world
settings = rough.settings
session = rough.session
catalog = rough.catalog
worker = rough.worker
drain = rough.drain
PROJECT = rough.PROJECT


def test_page_plan_derives_and_overrides_the_cast() -> None:
    page = {
        "characters": ["Aster Vale"],
        "directions": ["Aster Vale kneels.", "Aster Vale looks at the sea."],
        "dialogue": [
            {"speaker": "ROWAN", "kind": "speech", "text": "Where am I?"},
            {"speaker": "STRANGER", "kind": "speech", "text": "Hello."},
            {"speaker": "", "kind": "internal_noise", "text": "...tide..."},
        ],
        "intents": ["low_dialogue", "close_up"],
        "scene": "SCENE 2 - PIER AT NIGHT",
    }
    plan = page_plan(page, ["Aster Vale", "Rowan"])
    assert plan["characters_present"] == ["Aster Vale", "Rowan"]
    assert plan["primary_character"] == "Aster Vale" and plan["supporting_characters"] == ["Rowan"]
    assert plan["unmapped_speakers"] == ["STRANGER"]
    assert "speaker 'STRANGER' is not a known character" in plan["uncertain"]
    assert "Rowan speaks but is not named in the directions" in plan["uncertain"]
    assert plan["primary_intent"] == "close_up" and plan["environment_tags"] == ["night"]
    assert plan["dialogue_lines"] == 2 and plan["silent"] is False
    corrected = page_plan(
        page, ["Aster Vale", "Rowan"], {"remove": ["Rowan"], "primary": "Aster Vale"}
    )
    assert corrected["characters_present"] == ["Aster Vale"]
    assert corrected["cast_source"]["override"] == {
        "add": [],
        "remove": ["Rowan"],
        "primary": "Aster Vale",
    }


@dataclass(frozen=True)
class Layout:
    locator: str
    series_key: str
    label: str
    panel_count: int
    largest_panel_share: float
    negative_space: float
    ink_density: float
    unit_key: str
    page_offset: int


def test_full_page_references_carry_role_reason_and_no_identity() -> None:
    other = [
        Layout("zip:a", "other-work", "Ch 1 p5", 5, 0.3, 0.4, 0.2, "a" * 40, 4),
        Layout("zip:b", "other-work-2", "Ch 3 p9", 2, 0.7, 0.2, 0.3, "b" * 40, 8),
        Layout("zip:c", "other-work-3", "Ch 7 p2", 3, 0.4, 0.8, 0.1, "c" * 40, 1),
    ]
    world_pages = [Layout("zip:w", "demo-orbit", "Ch 2 p3", 2, 0.66, 0.3, 0.3, "d" * 40, 2)]
    grammar = [{"locator": "zip:c", "score": 1.5}]
    refs = page_references(
        ["close_up", "silent", "large_composition"],
        grammar,
        other,
        world_pages,
        world_series={"demo-orbit"},
        environment_wanted=True,
    )
    assert [g["role"] for g in refs["grammar"]] == ["GRAMMAR"]
    assert refs["grammar"][0]["image"] == f"/production/source-pages/{'c' * 40}/1/image"
    roles = {t["role"] for t in refs["technique"]}
    assert roles == {"TECHNIQUE"} and len(refs["technique"]) == 2
    assert all(
        "technique inferred from layout - content not verified" in t["why"]
        for t in refs["technique"]
    )
    assert refs["technique"][0]["teaches"] == [
        "facial acting",
        "reaction timing",
        "camera distance",
    ]
    environment = refs["environment_pages"]
    assert [e["locator"] for e in environment] == ["zip:w"]
    assert environment[0]["source"].endswith("same source world as the cast")
    every = [*refs["grammar"], *refs["technique"], *environment]
    assert all(r["identity_evidence"] is False for r in every)
    assert len({r["locator"] for r in every}) == len(every), "no page is used twice"


def test_chapter_preview_renders_every_page_and_is_never_approved(
    session: Session, catalog: ReferenceCatalog, world: World, worker: Worker, tmp_path: Path
) -> None:
    projects = m3._write_project(tmp_path)
    cast = m3._cast(catalog, world)
    cast["source"](cast["aster"], [CharacterAspect.FULL_BODY], 1)
    cast["photo"](91, [CharacterAspect.FACE])
    cast["photo"](92, [CharacterAspect.FULL_BODY])
    session.commit()
    manga = m3._manga(session, world, projects)
    profile = manga.create_profile(PROJECT, "harbor", m3._profile_body())
    decision = m3.PlacementDecision("s1e1-overlay-1", 2, 4, "PROPOSED", "planner")
    sample = manga.start_run(
        PROJECT,
        "S1E1",
        purpose=RoughPurpose.NON_CANON_SAMPLE,
        profile_id=profile.id,
        chapters=[2],
        decisions=[decision],
    )
    session.commit()
    sample_states = [p.state for p in manga.pages(sample.id)]

    page = manga.pages(sample.id)[0]
    body = manga.page_body(page)
    assert body["plan"]["characters_present"] == ["Aster Vale", "Rowan"]
    assert body["plan"]["speakers"] == ["Aster Vale"]
    manga.set_cast_override(page.id, remove=["Rowan"], note="off panel")
    session.commit()
    assert manga.page_body(page)["characters"] == ["Aster Vale"]
    assert {c["name"] for c in manga.assemble(page)["characters"]} == {"Aster Vale"}
    with pytest.raises(CatalogInputError, match="Unknown"):
        manga.set_cast_override(page.id, add=["Nobody"])
    session.rollback()

    preview = manga.start_preview(sample.id)
    session.commit()
    assert preview.purpose is RoughPurpose.WORKFLOW_TEST
    pages = manga.pages(preview.id)
    assert len(pages) == 4 and {p.state for p in pages} == {"READY"}

    worker.providers = artwork_page_registry()
    assert manga.render_preview(preview.id) == 4
    session.commit()
    assert drain(worker) == 4
    session.expire_all()
    assert manga.render_preview(preview.id) == 0, "rendered pages are not queued twice"

    view = manga.chapter_view(preview.id)
    assert [e["sequence"] for e in view["pages"]] == [1, 2, 3, 4]
    assert all(e["render"]["output_class"] == "TEST_RENDER" for e in view["pages"]), (
        "previews use the test backend"
    )
    qa = view["qa"]
    assert qa["pages"] == 4 and qa["rendered"] == 4
    assert qa["counts"].get("NO_GRAMMAR") == 4, "no grammar source configured in this world"
    third = view["pages"][2]
    assert third["origin"] == "overlay" and third["lineage"]["insertion"] == "s1e1-overlay-1"
    assert third["plan"]["characters_present"] == ["Aster Vale", "Rowan"]
    assert all(isinstance(w, dict) and w["kind"] for e in view["pages"] for w in e["warnings"])

    attempt = manga.rough.attempts(pages[0].artifact_id)[0]
    with pytest.raises(CatalogInputError, match="never approved"):
        manga.review_page(attempt.id, ReviewDecision.TECHNICAL_PASS)
    session.rollback()
    assert manga.current_continuity(preview.id).version == 1
    assert [p.state for p in manga.pages(sample.id)] == sample_states, "the sample run is untouched"


def test_visual_origin_is_kept_apart_from_acquisition(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    aster = catalog.create_character("Aster Vale", source_label="Demo Orbit")
    frame = catalog.add_upload(
        picture(7),
        ReferenceSpec(
            reference_class=ReferenceClass.UNSORTED,
            origin=ReferenceOrigin.FAN_ART,
            label="fan_account_aster_vale_frame",
            creator_handle="fan_account",
        ),
    )
    session.commit()
    corpus = CharacterCorpus(session, catalog)
    corpus.refresh(aster.id)
    session.commit()
    observation = next(o for o in corpus.observations(aster.id) if o.reference_id == frame.id)
    assert (observation.authority, observation.status) == ("SUPPLEMENTAL", "CANDIDATE")
    with pytest.raises(CatalogInputError, match="visual origin"):
        corpus.review(observation.id, {"authority": "OFFICIAL"})
    session.rollback()

    updated = corpus.set_visual_origin(observation.id, "OFFICIAL_ANIME")
    session.commit()
    item = catalog.reference(frame.id)
    assert item.origin is ReferenceOrigin.FAN_ART and item.creator_handle == "fan_account", (
        "acquisition kept"
    )
    assert item.visual_origin == "OFFICIAL_ANIME"
    assert (updated.authority, updated.role, updated.status) == (
        "OFFICIAL",
        "GROUNDING",
        "CANDIDATE",
    )
    assert updated.evidence["acquired_from"]["origin"] == "FAN_ART"
    confirmed = corpus.review(updated.id, {"status": "CONFIRMED", "facets": ["FACE"]})
    assert confirmed.authority == "OFFICIAL"
    assert corpus.readiness(aster.id)["groups"]["face"]["confirmed_high_authority"] == 1
    corpus.refresh(aster.id)
    assert corpus.observation(updated.id).authority == "OFFICIAL", "refresh keeps the judgement"


def _unused(value: Any) -> None:  # keep imports honest for type checkers
    return None
