"""M3 critical path: a non-canon sample chapter produced page by page.

Pinned here, with an invented project and invented characters:

* the chapter is materialized from the committed documents - base pages in
  order, an overlay insertion only where a placement decision puts it, every
  page traced to its source;
* a character without grounded identity and body blocks its pages
  (MISSING_REQUIRED_REFERENCE); an original character is grounded only by the
  creator's own references, never by a concept marked as style;
* production is page by page: the next page waits for the previous approval;
* one attempt yields a composition master and black-and-white and color
  finishes of the same geometry, with complete reproducibility records;
* approving a page adds it to the run's continuity; the next attempt uses it;
* everything survives a restart;
* changing a character's references marks exactly that character's pages
  stale, keeps the approved art, and says what changed;
* a sample of test renders cannot pass; a passed sample promotes the profile,
  never the images; canonical production refuses to start while creative
  inputs are unconfirmed, and starts once they are.

All content is invented (D-18 / A-05).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from continuum_core.corpus import ProductionEvidenceRole
from continuum_core.references import (
    AttemptState,
    CharacterAspect,
    CharacterOrigin,
    ReferenceClass,
    ReferenceOrigin,
    ReferenceUse,
    RenderOutput,
    ReviewDecision,
    RoughPurpose,
)
from continuum_db.models import ProductionPage, RoughArtifact
from continuum_db.session import reset_engine, session_scope
from continuum_imaging import probe
from continuum_imaging.manga import analyze_layout
from continuum_library import (
    CatalogConflictError,
    CharacterLink,
    ReferenceCatalog,
    ReferenceSpec,
)
from continuum_production import RoughProduction
from continuum_production.character_models import CharacterModels
from continuum_production.manga import GrammarCandidate, MangaProduction, rank_grammar
from continuum_production.materialize import PlacementDecision
from continuum_providers.artwork import (
    ArtworkBackendKind,
    ArtworkCapabilities,
    ArtworkReference,
    PageRenderRequest,
    PageRenderResult,
    RenderedImage,
    capability_gaps,
    check_result,
)
from continuum_storage import ProjectLibrary
from continuum_worker.main import Worker
from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import MANGA, World, picture
from tests.renderers import artwork_page_registry

pytestmark = pytest.mark.requires_db

PROJECT = rough.PROJECT
world = rough.world
settings = rough.settings
session = rough.session
catalog = rough.catalog
worker = rough.worker
drain = rough.drain

SCRIPT = """# HARBOR - S1E1 Manga Panel Script v0.1

**Status:** APPROVED PANEL SCRIPT
**Approved total:** 5 provisional pages

## Approved chapter cuts for rough

- **Chapter 1 \u2014 approx. pages 1\u20132:** the storm.
- **Chapter 2 \u2014 approx. pages 3\u20135:** the rescue. **End on the lantern.**

# SCENE 1 \u2014 STORM

### Page 1
- Aster Vale alone on the pier.

### Page 2 \u2014 CHAPTER 1 END
- Rowan lies unconscious on the sand.

# SCENE 2 \u2014 RESCUE

### Page 3
- Aster Vale kneels beside Rowan.
- **ASTER:** `Can you hear me?`

### Page 4
- Rowan wakes, disoriented.
- Fragment: `...tide...`
- No HUD/UI reveal.

### Page 5 \u2014 CHAPTER 2 END
- Large back shot of Aster Vale and Rowan on the pier.
- **ASTER:** `I'll help.`
"""

OVERLAY = """# Harbor Season 1 Overlay v0.2

**Status:** APPROVED / AUTHORITATIVE PRODUCTION OVERLAY

# 4. Chapter allocation

- **E1:** Ch1 +0 / Ch2 +1.

# 5. Episode-by-episode integration

## S1E1 \u2014 Harbor \u2014 6 pages

Integrate:
- a lantern glow stays on Rowan's sleeve after the rescue; Aster Vale notices the glow later.

---
"""

BEATS = """# Harbor Season 1 Beats

**Status:** APPROVED

1. **E1 \u2014 Lantern glow.** After the rescue a lantern glow stays caught
on Rowan's sleeve; Aster Vale notices the glow later.
"""


def _write_project(root: Path, *, checklist_status: str = "REVIEW") -> ProjectLibrary:
    folder = root / "projects" / PROJECT
    folder.mkdir(parents=True, exist_ok=True)
    files = {
        "HARBOR_S1E1_MANGA_PANEL_SCRIPT_v0.1.md": SCRIPT,
        "HARBOR_S1E1_DRAFT_1_v0.1.md": "# Harbor S1E1 Draft 1\n\n**Status:** APPROVED\n",
        "HARBOR_S1_OVERLAY_v0.2.md": OVERLAY,
        "HARBOR_S1_BEATS_v0.1.md": BEATS,
        "HARBOR_S1_CHECKLIST_v0.1.md": "# Checklist\n\n**Status:** PENDING CREATOR REVIEW\n",
    }
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    entry = lambda path, doc_id, category, lifecycle="APPROVED", **extra: {  # noqa: E731
        "id": doc_id,
        "path": path,
        "category": category,
        "section": "production",
        "lifecycle": lifecycle,
        **extra,
    }
    manifest = {
        "id": PROJECT,
        "title": "Demo Project",
        "documents": [
            entry(
                "HARBOR_S1E1_MANGA_PANEL_SCRIPT_v0.1.md",
                "s1e1-panel",
                "panel-script",
                episode="S1E1",
            ),
            entry("HARBOR_S1E1_DRAFT_1_v0.1.md", "s1e1-draft", "draft", episode="S1E1"),
            entry(
                "HARBOR_S1_OVERLAY_v0.2.md",
                "s1-overlay",
                "production-overlay",
                applies_to="season:1",
            ),
            entry("HARBOR_S1_BEATS_v0.1.md", "s1-beats", "revision-beats", applies_to="season:1"),
            entry(
                "HARBOR_S1_CHECKLIST_v0.1.md",
                "s1-checklist",
                "review-checklist",
                checklist_status,
                applies_to="season:1",
            ),
        ],
        "episodes": {
            "match": r"^S(?P<season>\d+)E(?P<number>\d+)$",
            "levels": [{"id": "4", "label": "Ready", "requires": ["draft", "panel-script"]}],
            "production_sources": [
                {"role": "base-panel-script", "categories": ["panel-script"], "required": True},
                {"role": "draft", "categories": ["draft"], "required": True},
                {
                    "role": "production-overlay",
                    "categories": ["production-overlay"],
                    "scope": "season",
                },
            ],
        },
    }
    (folder / "continuum.project.json").write_text(json.dumps(manifest), encoding="utf-8")
    return ProjectLibrary([str(root / "projects")])


def _cast(catalog: ReferenceCatalog, world: World) -> dict[str, Any]:
    aster = catalog.create_character("Aster Vale")
    rowan = catalog.create_character(
        "Rowan", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key=PROJECT
    )

    def source(character: Any, aspects: list[CharacterAspect], page: int) -> Any:
        return catalog.add_from_source(
            world.id_of(MANGA),
            ReferenceSpec(
                reference_class=ReferenceClass.CANON,
                origin=ReferenceOrigin.SOURCE,
                characters=tuple(CharacterLink(character.id, a) for a in aspects),
            ),
            page_index=page,
        )

    def photo(seed: int, aspects: list[CharacterAspect]) -> Any:
        return catalog.add_upload(
            picture(seed),
            ReferenceSpec(
                reference_class=ReferenceClass.CANON,
                origin=ReferenceOrigin.USER_CREATED,
                characters=tuple(CharacterLink(rowan.id, a) for a in aspects),
            ),
        )

    aster_face = source(aster, [CharacterAspect.FACE], 0)
    concept = photo(90, [CharacterAspect.FACE, CharacterAspect.FULL_BODY])
    catalog.set_uses(concept.id, [ReferenceUse.STYLE])
    return {
        "aster": aster,
        "rowan": rowan,
        "aster_face": aster_face,
        "concept": concept,
        "source": source,
        "photo": photo,
    }


def _profile_body() -> dict[str, Any]:
    return {
        "backend": {"provider_id": "fake.artwork-page-double", "width": 360, "height": 520},
        "reference_policy": {"per_facet": 2},
        "character_rules": {"Rowan": {"forbidden_accessories": ["glasses"]}},
        "setting": {"environment_tags": ["pier"]},
        "grammar": {"limit": 0},
    }


def _manga(session: Session, world: World, projects: ProjectLibrary) -> MangaProduction:
    cat = ReferenceCatalog(session, sources=world.sources(), derived=world.derived())
    return MangaProduction(RoughProduction(session, cat), projects)


# ---------------------------------------------------------------------------
def test_materialization_is_traced_and_placement_is_a_decision(
    session: Session, world: World, tmp_path: Path
) -> None:
    projects = _write_project(tmp_path)
    manga = _manga(session, world, projects)
    bare = manga.materialize(PROJECT, "S1E1", 2)
    assert bare.body["page_count"] == 3
    assert [i["item_key"] for i in bare.body["insertions"]["unplaced"]] == ["s1e1-overlay-1"]
    assert bare.body["insertions"]["unplaced"][0]["source_beats"][0]["number"] == 1
    assert any("allocates +1" in w for w in bare.body["warnings"])

    decision = PlacementDecision("s1e1-overlay-1", 2, 4, "PROPOSED", "planner", "after waking")
    placed = manga.materialize(PROJECT, "S1E1", 2, [decision])
    again = manga.materialize(PROJECT, "S1E1", 2, [decision])
    assert placed.id == again.id and placed.body_hash == again.body_hash, "deterministic"
    pages = placed.body["pages"]
    assert [(p["origin"], p["base_page"]) for p in pages] == [
        ("base", 3),
        ("base", 4),
        ("overlay", None),
        ("base", 5),
    ]
    assert pages[1]["dialogue"][0] == {
        "speaker": "",
        "kind": "internal_noise",
        "text": "...tide...",
    }
    assert pages[1]["constraints"] == ["No HUD/UI reveal."]
    assert pages[2]["lineage"]["overlay"]["document_id"] == "s1-overlay"
    assert pages[3]["chapter_end"] and "back_shot" in pages[3]["intents"]
    assert pages[0]["lineage"]["document_id"] == "s1e1-panel"
    assert placed.body["warnings"] == []


def test_fresh_non_canon_sample_starts_without_inherited_continuity(
    session: Session, world: World, tmp_path: Path
) -> None:
    """A fresh NON_CANON_SAMPLE from Page 1 begins with empty art continuity.

    Continuity is scoped to a run, so TEST-approved pages of an older sample or
    workflow-test run can never feed a new run's real-art continuity. This is
    the W7 invariant: no inherited TEST artwork.
    """
    projects = _write_project(tmp_path)
    manga = _manga(session, world, projects)
    profile = manga.create_profile(PROJECT, "harbor-manga", _profile_body())
    decision = PlacementDecision("s1e1-overlay-1", 2, 4, "PROPOSED", "planner")

    first = manga.start_run(
        PROJECT,
        "S1E1",
        purpose=RoughPurpose.NON_CANON_SAMPLE,
        profile_id=profile.id,
        chapters=[2],
        decisions=[decision],
    )
    second = manga.start_run(
        PROJECT,
        "S1E1",
        purpose=RoughPurpose.NON_CANON_SAMPLE,
        profile_id=profile.id,
        chapters=[2],
        decisions=[decision],
    )
    session.commit()

    first_continuity = manga.current_continuity(first.id)
    second_continuity = manga.current_continuity(second.id)
    assert first_continuity.id != second_continuity.id
    assert first_continuity.body["approved_pages"] == []
    assert second_continuity.body["approved_pages"] == []
    # Page 1 of a fresh run is READY, not waiting on any prior run's approval.
    assert manga.pages(second.id)[0].state == "READY"


def test_sample_chapter_page_by_page_through_restart_invalidation_and_pass(
    session: Session,
    catalog: ReferenceCatalog,
    settings: Any,
    world: World,
    worker: Worker,
    tmp_path: Path,
) -> None:
    projects = _write_project(tmp_path)
    cast = _cast(catalog, world)
    session.commit()
    manga = _manga(session, world, projects)
    profile = manga.create_profile(PROJECT, "harbor-manga", _profile_body())
    decision = PlacementDecision("s1e1-overlay-1", 2, 4, "PROPOSED", "planner")
    run = manga.start_run(
        PROJECT,
        "S1E1",
        purpose=RoughPurpose.NON_CANON_SAMPLE,
        profile_id=profile.id,
        chapters=[2],
        decisions=[decision],
    )
    session.commit()
    pages = manga.pages(run.id)
    assert [p.state for p in pages] == ["BLOCKED", "BLOCKED", "BLOCKED", "BLOCKED"]
    reasons = {r["key"]: r["detail"] for r in pages[0].reasons}
    assert "body" in reasons["Aster Vale"] and "identity" in reasons["Rowan"], reasons
    with pytest.raises(CatalogConflictError, match="BLOCKED"):
        manga.request_page_attempt(pages[0].id)
    session.rollback()

    # Grounding arrives: Aster's body from the source, Rowan's photos. The concept
    # stays style only.
    cast["source"](cast["aster"], [CharacterAspect.FULL_BODY], 1)
    cast["photo"](91, [CharacterAspect.FACE])
    cast["photo"](92, [CharacterAspect.FULL_BODY])
    manga.corpus.sync_curated(cast["aster"].id)
    aster_evidence = [
        row
        for row in manga.corpus.observations(cast["aster"].id)
        if row.status == "CONFIRMED" and row.role == "GROUNDING"
    ]
    model_service = CharacterModels(session)
    model = model_service.create(PROJECT, cast["aster"].id, name="Aster production lock")
    model_service.add_evidence(
        model.id, aster_evidence[0].id, ProductionEvidenceRole.IDENTITY, required=True
    )
    model_service.submit(model.id)
    model_service.approve(model.id, "test art director")
    session.commit()
    manga.refresh_staleness(run.id)
    session.commit()
    pages = manga.pages(run.id)
    assert [p.state for p in pages] == ["READY", "WAITING", "WAITING", "WAITING"]
    with pytest.raises(CatalogConflictError, match="WAITING"):
        manga.request_page_attempt(pages[1].id)
    session.rollback()

    bundle = manga.assemble(pages[0])
    assert bundle["canon_inputs"][0]["production_model_id"] == str(model.id)
    assert bundle["characters"][0]["production_model"]["status"] == "APPROVED"
    rowan_grounding = next(c for c in bundle["characters"] if c["name"] == "Rowan")
    assert str(cast["concept"].id) not in rowan_grounding["grounding"]["identity"]
    assert str(cast["concept"].id) in rowan_grounding["stylization"]
    assert bundle["continuity"]["character_rules"]["Rowan"] == {
        "forbidden_accessories": ["glasses"]
    }
    assert any("pier" in gap for gap in bundle["gaps"])

    worker.providers = artwork_page_registry()
    first = manga.request_page_attempt(pages[0].id)
    session.commit()
    assert drain(worker) == 1
    session.expire_all()
    first = manga.rough.attempt(first.id)
    assert first.output_class is RenderOutput.ARTWORK_CANDIDATE
    kinds = {d.kind.value: d for d in manga.rough.derivatives(first.id)}
    assert {"COMPOSITION_MASTER", "BW_FINISH", "COLOR_FINISH"} <= set(kinds)
    master = kinds["COMPOSITION_MASTER"]
    for finish in ("BW_FINISH", "COLOR_FINISH"):
        assert (kinds[finish].width, kinds[finish].height) == (master.width, master.height)
        assert kinds[finish].detail["master_sha256"] == master.content_hash
    provenance = first.artwork_provenance
    assert provenance["model"]["sha256"] and provenance["workflow"]["id"] and provenance["settings"]
    assert {r["character"] for r in provenance["references"] if r["role"] == "CANON"} == {
        "Aster Vale",
        "Rowan",
    }

    with pytest.raises(Exception, match="technical pass"):
        manga.review_page(first.id, ReviewDecision.CREATIVE_APPROVE)
    session.rollback()
    manga.review_page(first.id, ReviewDecision.TECHNICAL_PASS, notes="reads well")
    session.commit()
    pages = manga.pages(run.id)
    assert [p.state for p in pages] == ["APPROVED", "READY", "WAITING", "WAITING"]
    continuity = manga.current_continuity(run.id)
    assert continuity.version == 2
    assert continuity.body["approved_pages"][0]["master_sha256"] == master.content_hash

    second = manga.request_page_attempt(pages[1].id, seed=7)
    session.commit()
    assert drain(worker) == 1
    session.expire_all()
    second_row = manga.rough.attempt(second.id)
    assert any(r["role"] == "CONTINUITY" for r in second_row.artwork_provenance["references"]), (
        "the approved page feeds the next one"
    )
    run_id, second_id, rowan_id = run.id, second.id, cast["rowan"].id

    # -- restart ------------------------------------------------------------------
    session.close()
    reset_engine()
    with session_scope(settings) as fresh:
        manga = _manga(fresh, world, projects)
        pages = manga.pages(run_id)
        assert [p.state for p in pages] == ["APPROVED", "IN_REVIEW", "WAITING", "WAITING"]
        assert manga.next_page(run_id).sequence == 2  # type: ignore[union-attr]
        assert manga.current_continuity(run_id).version == 2
        attempt = manga.rough.attempt(second_id)
        assert manga.rough.recipe(attempt.recipe_id).execution["seed"] == 7
        assert attempt.continuity_state_id is not None and attempt.profile_id is not None
        manga.review_page(second_id, ReviewDecision.TECHNICAL_PASS)
        fresh.commit()

    # -- selective invalidation: Rowan's references change --------------------------
    with session_scope(settings) as fresh:
        cat = ReferenceCatalog(fresh, sources=world.sources(), derived=world.derived())
        rowan = cat.character(rowan_id)
        cat.add_upload(
            picture(93),
            ReferenceSpec(
                reference_class=ReferenceClass.CANON,
                origin=ReferenceOrigin.USER_CREATED,
                characters=(CharacterLink(rowan.id, CharacterAspect.FACE, preferred=True),),
            ),
        )
        fresh.commit()
        manga = _manga(fresh, world, projects)
        changes = manga.refresh_staleness(run_id)
        fresh.commit()
        stale = {c["sequence"]: {r["kind"] for r in c["reasons"]} for c in changes}
        pages = manga.pages(run_id)
        assert stale[1] == {"CHARACTER_REFERENCES"} and stale[2] == {"CHARACTER_REFERENCES"}
        assert pages[0].state == "STALE" and pages[0].approved_attempt_id is not None, (
            "approved art is kept, only flagged"
        )
        reason = next(r for r in pages[0].reasons if r["kind"] == "CHARACTER_REFERENCES")
        assert reason["key"] == "Rowan" and reason["old"] != reason["new"]
        assert all(r["key"] == "Rowan" for r in pages[0].reasons)

        # -- the sample decision -------------------------------------------------------
        promoted = manga.decide_sample(run_id, passed=True, notes="identity holds")
        fresh.commit()
        assert promoted is not None and promoted.status == "PROMOTED" and promoted.version == 2
        assert promoted.body["proven_by"]["run_id"] == str(run_id)
        promoted_id = promoted.id
        artifacts = (
            fresh.execute(select(RoughArtifact).where(RoughArtifact.production_run_id == run_id))
            .scalars()
            .all()
        )
        assert {a.purpose for a in artifacts} == {RoughPurpose.NON_CANON_SAMPLE}, (
            "the sample images stay non-canon"
        )

        # -- canonical production waits for creative confirmation -----------------------
        reasons = manga.canonical_start_readiness(PROJECT, "S1E1", promoted.id, [2], [decision])
        kinds = {r["kind"] for r in reasons}
        assert kinds == {"CREATIVE_REVIEW_PENDING", "INSERTION_UNCONFIRMED"}, reasons
        with pytest.raises(CatalogConflictError, match="cannot start"):
            manga.start_run(
                PROJECT,
                "S1E1",
                purpose=RoughPurpose.PRODUCTION,
                profile_id=promoted.id,
                chapters=[2],
                decisions=[decision],
            )
        fresh.rollback()

    ready_projects = _write_project(tmp_path, checklist_status="APPROVED")
    confirmed = PlacementDecision("s1e1-overlay-1", 2, 4, "CONFIRMED", "creator")
    with session_scope(settings) as fresh:
        manga = _manga(fresh, world, ready_projects)
        assert manga.canonical_start_readiness(PROJECT, "S1E1", promoted_id, [2], [confirmed]) == []
        canonical = manga.start_run(
            PROJECT,
            "S1E1",
            purpose=RoughPurpose.PRODUCTION,
            profile_id=promoted_id,
            chapters=[2],
            decisions=[confirmed],
        )
        fresh.commit()
        assert canonical.purpose is RoughPurpose.PRODUCTION
        assert manga.pages(canonical.id)[0].state == "READY"
        canonical_id = canonical.id
        first_page_id = manga.pages(canonical.id)[0].id
        drawn = manga.request_page_attempt(first_page_id)
        fresh.commit()
        drawn_id = drawn.id

    # A creatively approved canonical page becomes project-created character evidence;
    # a rejected one never does.
    assert drain(worker) == 1
    with session_scope(settings) as fresh:
        manga = _manga(fresh, world, ready_projects)
        manga.review_page(drawn_id, ReviewDecision.TECHNICAL_PASS)
        fresh.commit()
        assert manga.pages(canonical_id)[0].state == "IN_REVIEW", "a technical pass is not approval"
        assert not any(
            o.source_kind == "APPROVED_OUTPUT"
            for o in manga.corpus.observations(manga.corpus.by_name("Rowan").id)  # type: ignore[union-attr]
        )
        manga.review_page(drawn_id, ReviewDecision.CREATIVE_APPROVE, notes="canon")
        fresh.commit()
        learned = [
            o
            for name in ("Aster Vale", "Rowan")
            for o in manga.corpus.observations(manga.corpus.by_name(name).id)  # type: ignore[union-attr]
            if o.source_kind == "APPROVED_OUTPUT"
        ]
        assert len(learned) == 2
        assert {(o.authority, o.status, o.role) for o in learned} == {
            ("PROJECT_CREATED", "CONFIRMED", "EVIDENCE")
        }
        assert learned[0].evidence["attempt_id"] == str(drawn_id)
        assert manga.pages(canonical_id)[1].state == "READY"


def test_a_sample_of_test_renders_cannot_pass(
    session: Session, catalog: ReferenceCatalog, world: World, worker: Worker, tmp_path: Path
) -> None:
    projects = _write_project(tmp_path)
    cast = _cast(catalog, world)
    cast["source"](cast["aster"], [CharacterAspect.FULL_BODY], 1)
    cast["photo"](91, [CharacterAspect.FACE])
    cast["photo"](92, [CharacterAspect.FULL_BODY])
    session.commit()
    manga = _manga(session, world, projects)
    body = {
        **_profile_body(),
        "backend": {"provider_id": "fake.deterministic-page", "width": 300, "height": 420},
    }
    profile = manga.create_profile(PROJECT, "diagram", body)
    run = manga.start_run(
        PROJECT, "S1E1", purpose=RoughPurpose.NON_CANON_SAMPLE, profile_id=profile.id, chapters=[2]
    )
    session.commit()
    attempt = manga.request_page_attempt(manga.pages(run.id)[0].id)
    session.commit()
    assert drain(worker) == 1
    session.expire_all()
    assert manga.rough.attempt(attempt.id).output_class is RenderOutput.TEST_RENDER
    manga.review_page(attempt.id, ReviewDecision.TECHNICAL_PASS)
    session.commit()
    with pytest.raises(CatalogConflictError, match="test render"):
        manga.decide_sample(run.id, passed=True)
    session.rollback()
    assert manga.rough.attempt(attempt.id).state is AttemptState.TECHNICAL_PASS
    page = (
        session.execute(select(ProductionPage).where(ProductionPage.run_id == run.id))
        .scalars()
        .first()
    )
    assert page is not None and page.state == "APPROVED"


def test_backend_honesty_and_grammar_ranking() -> None:
    def image(width: int, height: int) -> RenderedImage:
        buffer = io.BytesIO()
        Image.new("L", (width, height), 200).save(buffer, format="PNG")
        return RenderedImage(buffer.getvalue(), "image/png", width, height)

    master = image(100, 140)
    loose = PageRenderResult(
        backend=ArtworkBackendKind.COMFY_LOCAL,
        provider_id="comfy.local",
        output=RenderOutput.ARTWORK_CANDIDATE,
        master=master,
        bw=image(100, 140),
        color=image(120, 140),
        provenance={"backend": "COMFY_LOCAL"},
    )
    problems = check_result(loose)
    assert any("geometry" in p for p in problems)
    assert any("model.sha256" in p and "workflow.version" in p for p in problems)

    caps = ArtworkCapabilities(output=RenderOutput.ARTWORK_CANDIDATE, max_reference_images=2)
    request = PageRenderRequest(
        page_key="p",
        width=100,
        height=140,
        seed=1,
        page={},
        plan={},
        continuity={},
        references=tuple(
            ArtworkReference(role="CANON", reference_id=str(i), data=b"", character="Rowan")
            for i in range(3)
        ),
        settings={},
    )
    gaps = capability_gaps(caps, request)
    assert any("condition identity" in g for g in gaps)
    assert any("accepts 2" in g for g in gaps)
    assert any("one master" in g for g in gaps)

    # A four-panel page and a splash page, measured and ranked by page intent.
    four = Image.new("L", (400, 600), 255)
    draw = ImageDraw.Draw(four)
    for x0, y0, x1, y1 in (
        (20, 20, 380, 180),
        (20, 200, 190, 400),
        (210, 200, 380, 400),
        (20, 420, 380, 580),
    ):
        draw.rectangle((x0, y0, x1, y1), fill=40)
    splash = Image.new("L", (400, 600), 255)
    ImageDraw.Draw(splash).rectangle((10, 10, 390, 590), fill=60)
    layouts = {}
    for name, canvas in (("four", four), ("splash", splash)):
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG")
        layouts[name] = analyze_layout(buffer.getvalue())
    assert layouts["four"].panel_count == 4
    assert layouts["splash"].panel_count == 1
    candidates = [
        GrammarCandidate(
            f"zip:{name}",
            name,
            name,
            lay.panel_count,
            round(lay.largest_panel_share, 4),
            lay.negative_space,
            lay.ink_density,
        )
        for name, lay in layouts.items()
    ]
    assert (
        rank_grammar(["large_composition", "back_shot"], candidates, 1)[0]["series_key"] == "splash"
    )
    assert rank_grammar(["conversation", "two_character"], candidates, 1)[0]["series_key"] == "four"
    assert probe(master.data).width == 100


def test_the_page_loop_over_http(
    session: Session,
    catalog: ReferenceCatalog,
    settings: Any,
    world: World,
    worker: Worker,
    tmp_path: Path,
) -> None:
    from continuum_api import create_app
    from fastapi.testclient import TestClient

    _write_project(tmp_path)
    cast = _cast(catalog, world)
    cast["source"](cast["aster"], [CharacterAspect.FULL_BODY], 1)
    cast["photo"](91, [CharacterAspect.FACE])
    cast["photo"](92, [CharacterAspect.FULL_BODY])
    session.commit()
    session.close()
    worker.providers = artwork_page_registry()
    api = create_app(settings.model_copy(update={"project_sources": str(tmp_path / "projects")}))
    decision = {"item_key": "s1e1-overlay-1", "chapter": 2, "after_base_page": 4}
    with TestClient(api) as client:
        api.state.providers = artwork_page_registry()
        materialized = client.post(
            f"/projects/{PROJECT}/episodes/S1E1/materialize",
            json={"chapter": 2, "decisions": [decision]},
        )
        assert materialized.status_code == 200, materialized.text
        assert materialized.json()["body"]["page_count"] == 4
        backends = {b["kind"]: b for b in client.get("/production/backends").json()["backends"]}
        assert backends["TEST"]["ready"] and not backends["COMFY_LOCAL"]["configured"]
        assert not backends["COMFY_REMOTE"]["configured"]
        unknown = client.post(
            f"/projects/{PROJECT}/episodes/S1E1/sample-runs",
            json={"chapter": 2, "provider_id": "comfy.local"},
        )
        assert unknown.status_code == 422, "an unconfigured backend cannot be chosen"
        started = client.post(
            f"/projects/{PROJECT}/episodes/S1E1/sample-runs",
            json={"chapter": 2, "decisions": [decision], "provider_id": "fake.artwork-page-double"},
        )
        assert started.status_code == 201, started.text
        run = started.json()
        assert run["purpose"] == "NON_CANON_SAMPLE" and run["profile"]["status"] == "DRAFT"
        profile = run["profile"]
        listed = client.get(f"/projects/{PROJECT}/production-runs").json()
        assert listed[0]["id"] == run["id"] and listed[0]["pages"] == 4
        assert [p["state"] for p in run["pages"]] == ["READY", "WAITING", "WAITING", "WAITING"]
        first = run["pages"][0]
        waiting = client.post(f"/production/pages/{run['pages'][1]['id']}/attempts", json={})
        assert waiting.status_code == 409, waiting.text

        page = client.get(f"/production/pages/{first['id']}").json()
        assert page["body"]["page_key"] == first["page_key"]
        assert {d["kind"] for d in page["dependencies"]} >= {
            "MATERIALIZED_PAGE",
            "PROFILE",
            "SOURCE_DOCUMENT",
            "CHARACTER_REFERENCES",
        }
        assert {c["name"] for c in page["bundle"]["characters"]} == {"Aster Vale", "Rowan"}
        rowan_bundle = next(c for c in page["bundle"]["characters"] if c["name"] == "Rowan")
        assert rowan_bundle["observations"] and all(
            o["authority"] == "CREATOR_PRIMARY" for o in rowan_bundle["observations"]
        )
        assert [o["reference_id"] for o in rowan_bundle["stylization_observations"]] == [
            str(cast["concept"].id)
        ]

        overview = client.get(f"/library/characters/{cast['rowan'].id}/overview").json()
        assert overview["readiness"]["grounded"] is True
        assert [s["reference_id"] for s in overview["stylization"]] == [str(cast["concept"].id)]
        observations = client.get(
            f"/library/characters/{cast['aster'].id}/observations", params={"facet": "BODY"}
        ).json()
        assert observations["total"] == 1
        body_obs = observations["observations"][0]
        image = client.get(body_obs["image"])
        assert image.status_code == 200 and image.headers["content-type"] == "image/webp"
        reviewed_obs = client.post(
            f"/library/character-observations/{body_obs['id']}/review",
            json={"angle": "FRONT", "expression": "neutral"},
        )
        assert reviewed_obs.status_code == 200 and reviewed_obs.json()["angle"] == "FRONT"
        bad = client.post(
            f"/library/character-observations/{body_obs['id']}/review", json={"angle": "SIDEWAYS"}
        )
        assert bad.status_code == 422

        queued = client.post(f"/production/pages/{first['id']}/attempts", json={"seed": 11})
        assert queued.status_code == 202, queued.text
        assert drain(worker) == 1
        page = client.get(f"/production/pages/{first['id']}").json()
        attempt = page["attempts"][0]
        assert page["state"] == "IN_REVIEW" and attempt["output_class"] == "ARTWORK_CANDIDATE"
        assert attempt["artwork_provenance"]["model"]["name"]
        bw = client.get(attempt["images"]["BW_FINISH"])
        color = client.get(attempt["images"]["COLOR_FINISH"])
        assert bw.status_code == 200 and color.status_code == 200
        assert probe(bw.content).width == probe(color.content).width == 1024

        reviewed = client.post(
            f"/production/page-attempts/{attempt['id']}/review",
            json={"decision": "TECHNICAL_PASS", "notes": "reads"},
        )
        assert reviewed.status_code == 200, reviewed.text
        run = client.get(f"/production/runs/{run['id']}").json()
        assert [p["state"] for p in run["pages"]][:2] == ["APPROVED", "READY"]
        assert run["continuity"]["version"] == 2 and run["next_page_id"] == run["pages"][1]["id"]
        assert run["pages"][0]["images"]["COLOR_FINISH"].endswith("kind=COLOR_FINISH")

        readiness = client.post(
            f"/projects/{PROJECT}/episodes/S1E1/canonical-readiness",
            json={"profile_id": profile["id"], "chapters": [2], "decisions": [decision]},
        ).json()
        assert readiness["ready"] is False
        refused = client.post(
            f"/projects/{PROJECT}/production-runs",
            json={
                "episode": "S1E1",
                "purpose": "PRODUCTION",
                "profile_id": profile["id"],
                "chapters": [2],
            },
        )
        assert refused.status_code == 409 and "PROMOTED" in refused.text
        refreshed = client.post(f"/production/runs/{run['id']}/refresh").json()
        assert refreshed["changes"] == []
        passed = client.post(
            f"/production/runs/{run['id']}/sample-decision", json={"passed": True, "notes": "ok"}
        ).json()
        assert passed["promoted_profile"]["status"] == "PROMOTED"
        assert passed["run"]["status"] == "SAMPLE_PASSED"
