"""Rough manga production: bundles, source plates, edit intent, append-only attempts.

Under test (Phase 1 M2, expansion sections 21-26, 30, 31 D-G):

* all four modes - NEW_GENERATION, SOURCE_DERIVED_EDIT, COMPOSITE, LAYOUT_ONLY -
  render through the real worker as durable ``visual.rough_attempt`` jobs;
* a source-derived edit starts from a held manga page, records what to
  preserve/remove/replace, and produces a NEW artifact with a source crop, a
  mask and an output - the page's bytes are byte-identical afterwards;
* attempts are append-only: regenerate makes the next attempt with a new seed
  and a parent; approval supersedes; nothing is overwritten or deleted;
* the same recipe and seed reproduce the same pixels;
* one source page feeds several artifacts;
* an approved attempt becomes a CONTINUITY reference usable in a composite;
* no permitted provider, or an unreachable source, parks the job BLOCKED with
  remediation - and it completes once the cause is fixed;
* removing a catalog reference breaks neither provenance nor regeneration;
* provenance reconstructs source page -> region -> recipe -> job -> bytes.

PostgreSQL (the isolated test database). All content is invented.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from continuum_config import Settings
from continuum_core import BlockedReason, JobStatus, NormalizedRegion
from continuum_core.references import (
    AttemptState,
    BundleRole,
    CharacterAspect,
    DerivativeKind,
    EditOperationKind,
    ReferenceClass,
    ReferenceOrigin,
    ReviewDecision,
    RoughMode,
    VisualModeCategory,
)
from continuum_db.models import Job
from continuum_db.session import session_scope
from continuum_imaging import open_image, pixel_digest, probe
from continuum_jobs import retry_job
from continuum_library import (
    CatalogConflictError,
    CatalogInputError,
    CatalogNotFoundError,
    CharacterLink,
    ReferenceCatalog,
    ReferenceSpec,
)
from continuum_production import (
    BundleEntry,
    CharacterDirection,
    EditOperation,
    Placement,
    RoughIntentSpec,
    RoughProduction,
    artifact_view,
    attempt_view,
    provenance_view,
)
from continuum_providers import ProviderRegistry, build_default_registry
from continuum_worker import register_default_handlers
from continuum_worker.main import Worker
from sqlalchemy import delete
from sqlalchemy.orm import Session

from tests.conftest import TEST_DATABASE_URL
from tests.phase1_world import (
    ART,
    GUIDE,
    MANGA,
    MANGA_ENTRIES,
    World,
    build_world,
    clean_domain_tables,
    picture,
    snapshot,
)

pytestmark = pytest.mark.requires_db

PROJECT = "demo-project"
SMALL = {"width": 480, "height": 360}


@pytest.fixture
def world(tmp_path: Path, db_settings: Settings) -> World:
    from continuum_db.models import Worker as WorkerRow

    with session_scope(db_settings) as session:
        clean_domain_tables(session)
        session.execute(delete(Job))
        session.execute(delete(WorkerRow))
    register_default_handlers()
    return build_world(tmp_path)


@pytest.fixture
def settings(world: World) -> Settings:
    return Settings(
        _env_file=None,
        data_home=str(world.data_home),
        source_vault_root=str(world.vault),
        acquisition_data_dir=str(world.acquisition_dir),
        database_url=TEST_DATABASE_URL,
    )


@pytest.fixture
def session(settings: Settings) -> Iterator[Session]:
    with session_scope(settings) as s:
        yield s


@pytest.fixture
def catalog(session: Session, world: World) -> ReferenceCatalog:
    return ReferenceCatalog(session, sources=world.sources(), derived=world.derived())


@pytest.fixture
def production(session: Session, catalog: ReferenceCatalog) -> RoughProduction:
    return RoughProduction(session, catalog, providers=build_default_registry())


@pytest.fixture
def worker(settings: Settings) -> Worker:
    w = Worker(settings)
    w.register()
    return w


def drain(worker: Worker, limit: int = 10) -> int:
    ran = 0
    while ran < limit and worker.run_once():
        ran += 1
    return ran


def cast(catalog: ReferenceCatalog, world: World) -> dict[str, Any]:
    """A small invented cast and reference set over the synthetic manga."""
    hero = catalog.create_character("Aster Vale")
    coat = catalog.create_outfit(hero.id, "Travel coat")
    face = catalog.add_from_source(
        world.id_of(MANGA),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.SOURCE,
            region=NormalizedRegion(0.2, 0.1, 0.4, 0.3),
            characters=(CharacterLink(hero.id, CharacterAspect.FACE, preferred=True),),
        ),
        page_index=0,
    )
    page = catalog.add_from_source(
        world.id_of(MANGA),
        ReferenceSpec(reference_class=ReferenceClass.CANON, origin=ReferenceOrigin.SOURCE),
        page_index=1,
    )
    style = catalog.add_from_source(
        world.id_of(ART),
        ReferenceSpec(
            reference_class=ReferenceClass.TECHNIQUE, origin=ReferenceOrigin.OFFICIAL_ART
        ),
    )
    mood = catalog.add_upload(
        picture(50),
        ReferenceSpec(reference_class=ReferenceClass.MOOD, origin=ReferenceOrigin.FAN_ART),
    )
    return {"hero": hero, "coat": coat, "face": face, "page": page, "style": style, "mood": mood}


def edit_spec(refs: dict[str, Any], **overrides: Any) -> RoughIntentSpec:
    hero = refs["hero"]
    values: dict[str, Any] = {
        "mode": RoughMode.SOURCE_DERIVED_EDIT,
        "bundle": (
            BundleEntry(BundleRole.SOURCE_PLATE, refs["page"].id, label="page plate"),
            BundleEntry(
                BundleRole.CANON,
                refs["face"].id,
                character_id=hero.id,
                aspect=CharacterAspect.FACE,
            ),
            BundleEntry(BundleRole.STYLE, refs["style"].id),
        ),
        "characters": (
            CharacterDirection(hero.id, outfit_id=refs["coat"].id, acting_direction="startled"),
        ),
        "operations": (
            EditOperation(EditOperationKind.PRESERVE, NormalizedRegion(0.0, 0.0, 1.0, 0.3)),
            EditOperation(EditOperationKind.REMOVE, NormalizedRegion(0.1, 0.5, 0.3, 0.3)),
            EditOperation(
                EditOperationKind.REPLACE,
                NormalizedRegion(0.5, 0.4, 0.4, 0.5),
                character_id=hero.id,
                outfit_id=refs["coat"].id,
                reference_position=1,
            ),
        ),
        **SMALL,
    }
    values.update(overrides)
    return RoughIntentSpec(**values)


class TestFourModes:
    def test_source_derived_edit_makes_a_new_artifact_and_keeps_the_source(
        self,
        production: RoughProduction,
        catalog: ReferenceCatalog,
        session: Session,
        world: World,
        worker: Worker,
    ) -> None:
        vault_before = snapshot(world.vault)
        refs = cast(catalog, world)
        artifact = production.create_artifact(
            PROJECT,
            "S1E1",
            35,
            panel=2,
            chapter=1,
            panel_script_document="panel-script",
            panel_script_version="0.1",
        )
        attempt = production.request_attempt(artifact.id, edit_spec(refs))
        session.commit()
        assert attempt.state is AttemptState.QUEUED and attempt.attempt == 1
        assert attempt_view(production, attempt)["display_state"] == "QUEUED"

        assert drain(worker) == 1
        session.expire_all()
        attempt = production.attempt(attempt.id)
        assert attempt.state is AttemptState.GENERATED
        kinds = {d.kind for d in production.derivatives(attempt.id)}
        assert kinds == {DerivativeKind.OUTPUT, DerivativeKind.SOURCE_CROP, DerivativeKind.MASK}

        output, mime = production.derivative_bytes(attempt.id, DerivativeKind.OUTPUT)
        assert mime == "image/png" and probe(output).width == 480
        crop, _ = production.derivative_bytes(attempt.id, DerivativeKind.SOURCE_CROP)
        # The whole-page crop is a derived copy under generated/, never the archive itself.
        assert pixel_digest(crop) == pixel_digest(world.page_bytes[MANGA_ENTRIES[1]])
        mask, _ = production.derivative_bytes(attempt.id, DerivativeKind.MASK)
        mask_image = open_image(mask).convert("L")
        assert mask_image.getpixel((int(0.2 * 300), int(0.65 * 420))) == 255  # REMOVE region
        assert mask_image.getpixel((int(0.5 * 300), int(0.1 * 420))) == 0  # PRESERVE region
        assert attempt.content_hash not in {world.sha256_of(MANGA)}

        # The source is untouched, and the plate's catalog record still reads it back.
        assert snapshot(world.vault) == vault_before
        assert catalog.unit_bytes(refs["page"]) == world.page_bytes[MANGA_ENTRIES[1]]

        chain = provenance_view(production, attempt)
        plate = next(s for s in chain["sources"] if s["role"] == "SOURCE_PLATE")
        assert plate["locator"].endswith(f"#entry={MANGA_ENTRIES[1]}")
        assert plate["source"]["media_id"] == world.id_of(MANGA)
        assert plate["source"]["page_index"] == 1
        assert chain["artifact"]["panel_script"] == {"document": "panel-script", "version": "0.1"}
        assert chain["recipe"]["mode"] == "SOURCE_DERIVED_EDIT"
        assert [op["kind"] for op in chain["recipe"]["operations"]] == [
            "PRESERVE",
            "REMOVE",
            "REPLACE",
        ]
        assert chain["rendered_with"]["provider_id"] == "fake.deterministic-sketch"
        assert chain["job"]["status"] == "SUCCEEDED"
        assert chain["output_hash"] == attempt.content_hash

    def test_new_generation_composite_and_layout_only(
        self,
        production: RoughProduction,
        catalog: ReferenceCatalog,
        session: Session,
        world: World,
        worker: Worker,
    ) -> None:
        refs = cast(catalog, world)
        hero = refs["hero"]
        chibi = catalog.create_visual_mode("Comic squash", VisualModeCategory.COMEDIC_DEFORMATION)

        new_art = production.create_artifact(PROJECT, "S1E1", 1, panel=1)
        new = production.request_attempt(
            new_art.id,
            RoughIntentSpec(
                mode=RoughMode.NEW_GENERATION,
                bundle=(
                    BundleEntry(BundleRole.CANON, refs["face"].id, character_id=hero.id),
                    BundleEntry(BundleRole.STYLE, refs["style"].id),
                    BundleEntry(BundleRole.MOOD, refs["mood"].id),
                ),
                characters=(CharacterDirection(hero.id, visual_mode_id=chibi.id),),
                placements=(Placement(NormalizedRegion(0.3, 0.2, 0.4, 0.7), character_id=hero.id),),
                **SMALL,
            ),
        )
        layout_art = production.create_artifact(PROJECT, "S1E1", 40)
        layout = production.request_attempt(
            layout_art.id,
            RoughIntentSpec(
                mode=RoughMode.LAYOUT_ONLY,
                characters=(CharacterDirection(hero.id),),
                placements=(
                    Placement(NormalizedRegion(0.05, 0.05, 0.9, 0.4), label="establishing"),
                    Placement(NormalizedRegion(0.05, 0.5, 0.4, 0.45), character_id=hero.id),
                ),
                **SMALL,
            ),
        )
        session.commit()
        assert drain(worker) == 2
        session.expire_all()
        new = production.attempt(new.id)
        layout = production.attempt(layout.id)
        assert new.state is AttemptState.GENERATED and layout.state is AttemptState.GENERATED
        assert {d.kind for d in production.derivatives(new.id)} == {DerivativeKind.OUTPUT}
        intent = production.recipe(new.recipe_id).intent
        assert intent["characters"][0]["visual_mode_name"] == "Comic squash"
        assert production.inputs(layout.id) == []

        # Approve the new generation and use it as continuity in a composite.
        production.review(new.id, ReviewDecision.APPROVE, notes="good read")
        continuity = production.promote_to_continuity(
            new.id, characters=(CharacterLink(hero.id, CharacterAspect.FULL_BODY),)
        )
        assert continuity.origin is ReferenceOrigin.PROJECT_APPROVED
        assert continuity.locator == f"gen:sha256:{new.content_hash}"
        composite_art = production.create_artifact(PROJECT, "S1E1", 36, panel=1)
        composite = production.request_attempt(
            composite_art.id,
            RoughIntentSpec(
                mode=RoughMode.COMPOSITE,
                bundle=(
                    BundleEntry(BundleRole.SOURCE_PLATE, refs["page"].id),
                    BundleEntry(BundleRole.CONTINUITY, continuity.id, character_id=hero.id),
                ),
                operations=(
                    EditOperation(
                        EditOperationKind.INSERT,
                        NormalizedRegion(0.55, 0.3, 0.4, 0.6),
                        reference_position=1,
                    ),
                ),
                **SMALL,
            ),
        )
        session.commit()
        assert drain(worker) == 1
        session.expire_all()
        composite = production.attempt(composite.id)
        assert composite.state is AttemptState.GENERATED
        roles = attempt_view(production, composite)["bundle"]
        assert [e["reference_origin"] for e in roles["CONTINUITY"]] == ["PROJECT_APPROVED"]
        assert (
            catalog.unit_bytes(continuity)
            == production.derivative_bytes(new.id, DerivativeKind.OUTPUT)[0]
        )


class TestAppendOnlyHistory:
    def test_regenerate_review_and_supersede(
        self,
        production: RoughProduction,
        catalog: ReferenceCatalog,
        session: Session,
        world: World,
        worker: Worker,
    ) -> None:
        refs = cast(catalog, world)
        artifact = production.create_artifact(PROJECT, "S1E1", 35, panel=2)
        first = production.request_attempt(artifact.id, edit_spec(refs))
        session.commit()
        drain(worker)
        session.expire_all()

        with pytest.raises(CatalogConflictError):
            production.review(
                production.request_attempt(artifact.id, edit_spec(refs)).id, ReviewDecision.APPROVE
            )
        session.rollback()

        second = production.regenerate(first.id, notes="try another take")
        session.commit()
        assert second.attempt == 2 and second.parent_attempt_id == first.id
        assert production.attempt(first.id).state is AttemptState.REJECTED
        assert [r.decision for r in production.reviews(first.id)] == [ReviewDecision.REGENERATE]
        drain(worker)
        session.expire_all()
        second = production.attempt(second.id)
        first = production.attempt(first.id)
        seeds = {production.recipe(a.recipe_id).execution["seed"] for a in (first, second)}
        assert len(seeds) == 2
        assert (
            production.recipe(first.recipe_id).intent_hash
            == production.recipe(second.recipe_id).intent_hash
        )
        out1, _ = production.derivative_bytes(first.id, DerivativeKind.OUTPUT)
        out2, _ = production.derivative_bytes(second.id, DerivativeKind.OUTPUT)
        assert pixel_digest(out1) != pixel_digest(out2)

        production.review(second.id, ReviewDecision.APPROVE)
        production.review(first.id, ReviewDecision.APPROVE, notes="the first take was better")
        session.commit()
        assert production.attempt(first.id).state is AttemptState.APPROVED
        assert production.attempt(second.id).state is AttemptState.SUPERSEDED
        with pytest.raises(CatalogConflictError):
            production.review(first.id, ReviewDecision.APPROVE)
        # Every attempt's bytes remain, and history is newest first.
        assert production.derivative_bytes(second.id, DerivativeKind.OUTPUT)[0] == out2
        view = artifact_view(production, artifact)
        assert [a["attempt"] for a in view["attempts"]] == [2, 1]
        assert view["approved_attempt_id"] == str(first.id)

    def test_same_recipe_and_seed_reproduce_the_same_pixels(
        self,
        production: RoughProduction,
        catalog: ReferenceCatalog,
        session: Session,
        world: World,
        worker: Worker,
    ) -> None:
        refs = cast(catalog, world)
        artifact = production.create_artifact(PROJECT, "S1E1", 35, panel=2)
        a = production.request_attempt(artifact.id, edit_spec(refs, seed=1234))
        b = production.request_attempt(artifact.id, edit_spec(refs, seed=1234))
        session.commit()
        assert a.recipe_id == b.recipe_id
        drain(worker)
        session.expire_all()
        a, b = production.attempt(a.id), production.attempt(b.id)
        assert a.content_hash == b.content_hash
        assert pixel_digest(production.derivative_bytes(a.id, DerivativeKind.OUTPUT)[0]) == (
            pixel_digest(production.derivative_bytes(b.id, DerivativeKind.OUTPUT)[0])
        )

    def test_one_source_page_feeds_several_artifacts(
        self,
        production: RoughProduction,
        catalog: ReferenceCatalog,
        session: Session,
        world: World,
        worker: Worker,
    ) -> None:
        refs = cast(catalog, world)
        attempts = [
            production.request_attempt(
                production.create_artifact(PROJECT, "S1E1", page, panel=1).id, edit_spec(refs)
            )
            for page in (35, 40)
        ]
        session.commit()
        assert drain(worker) == 2
        session.expire_all()
        outputs = {production.attempt(a.id).content_hash for a in attempts}
        assert len(outputs) == 2
        crops = {
            d.content_hash
            for a in attempts
            for d in production.derivatives(a.id)
            if d.kind is DerivativeKind.SOURCE_CROP
        }
        assert len(crops) == 1  # the same plate crop, stored once

    def test_removing_a_reference_keeps_provenance_and_regeneration(
        self,
        production: RoughProduction,
        catalog: ReferenceCatalog,
        session: Session,
        world: World,
        worker: Worker,
    ) -> None:
        refs = cast(catalog, world)
        artifact = production.create_artifact(PROJECT, "S1E1", 35, panel=2)
        first = production.request_attempt(artifact.id, edit_spec(refs))
        session.commit()
        drain(worker)
        session.expire_all()
        page = catalog.reference(refs["page"].id)
        catalog.remove_reference(page.id, page.row_version)
        session.commit()

        chain = provenance_view(production, production.attempt(first.id))
        plate = next(s for s in chain["sources"] if s["role"] == "SOURCE_PLATE")
        assert plate["locator"].endswith(f"#entry={MANGA_ENTRIES[1]}")
        assert plate["source"]["page_index"] == 1
        view = attempt_view(production, production.attempt(first.id))
        assert view["bundle"]["SOURCE_PLATE"][0]["reference_available"] is False

        again = production.regenerate(first.id)
        session.commit()
        drain(worker)
        session.expire_all()
        assert production.attempt(again.id).state is AttemptState.GENERATED
        # A new attempt cannot choose a removed reference; history above still can.
        with pytest.raises(CatalogNotFoundError):
            production.request_attempt(artifact.id, edit_spec(refs))


class TestBlockedAndRecovery:
    def test_no_permitted_provider_blocks_then_completes(
        self,
        production: RoughProduction,
        catalog: ReferenceCatalog,
        session: Session,
        world: World,
        worker: Worker,
    ) -> None:
        refs = cast(catalog, world)
        artifact = production.create_artifact(PROJECT, "S1E1", 35, panel=2)
        attempt = production.request_attempt(artifact.id, edit_spec(refs))
        session.commit()

        worker.providers = ProviderRegistry()  # nothing can render
        assert drain(worker) == 1
        session.expire_all()
        view = attempt_view(production, production.attempt(attempt.id))
        assert view["display_state"] == "BLOCKED"
        assert view["job"]["blocked_reason"] == BlockedReason.MISSING_PROVIDER.value
        assert view["job"]["remediation"]["capability"] == "ROUGH_RENDER"
        assert production.derivatives(attempt.id) == []

        worker.providers = build_default_registry()
        job = session.get(Job, attempt.job_id)
        assert job is not None and job.status is JobStatus.BLOCKED
        retry_job(session, job)
        session.commit()
        assert drain(worker) == 1
        session.expire_all()
        assert production.attempt(attempt.id).state is AttemptState.GENERATED

    def test_an_unreachable_source_blocks_with_remediation(
        self,
        production: RoughProduction,
        catalog: ReferenceCatalog,
        session: Session,
        world: World,
        worker: Worker,
    ) -> None:
        refs = cast(catalog, world)
        artifact = production.create_artifact(PROJECT, "S1E1", 35, panel=2)
        attempt = production.request_attempt(artifact.id, edit_spec(refs))
        session.commit()
        archive = world.vault / MANGA
        held = archive.read_bytes()
        archive.unlink()  # the drive is disconnected (the harness, not Continuum)

        assert drain(worker) == 1
        session.expire_all()
        view = attempt_view(production, production.attempt(attempt.id))
        assert view["display_state"] == "BLOCKED"
        assert view["job"]["blocked_reason"] == BlockedReason.MISSING_SOURCE_ASSET.value
        assert "Source Vault" in view["job"]["remediation"]["action"]

        archive.write_bytes(held)
        job = session.get(Job, attempt.job_id)
        assert job is not None
        retry_job(session, job)
        session.commit()
        assert drain(worker) == 1
        session.expire_all()
        assert production.attempt(attempt.id).state is AttemptState.GENERATED

    def test_rendering_twice_is_a_no_op(
        self,
        production: RoughProduction,
        catalog: ReferenceCatalog,
        session: Session,
        world: World,
        settings: Settings,
    ) -> None:
        """A crash after the bytes land but before completion commits: the re-run
        writes the same content-addressed files and no duplicate rows."""
        from continuum_production import render_attempt

        refs = cast(catalog, world)
        artifact = production.create_artifact(PROJECT, "S1E1", 35, panel=2)
        attempt = production.request_attempt(artifact.id, edit_spec(refs))
        session.commit()
        attempt_id = attempt.id

        first = render_attempt(
            session, attempt_id, catalog=catalog, providers=build_default_registry()
        )
        generated = world.data_home / "generated"
        files_after_first = sorted(p.name for p in generated.rglob("*") if p.is_file())
        session.rollback()  # the completion never committed

        second = render_attempt(
            session, attempt_id, catalog=catalog, providers=build_default_registry()
        )
        session.commit()
        assert first["content_hash"] == second["content_hash"]
        assert sorted(p.name for p in generated.rglob("*") if p.is_file()) == files_after_first
        third = render_attempt(
            session, attempt_id, catalog=catalog, providers=build_default_registry()
        )
        assert third["rerun"] is True
        assert len(production.derivatives(attempt_id)) == 3


class TestIntentValidation:
    @pytest.mark.parametrize(
        "change",
        [
            {"bundle": ()},  # edit without a plate
            {"operations": ()},  # edit that changes nothing
            {"mode": RoughMode.NEW_GENERATION},  # a plate in a new generation
            {"mode": RoughMode.LAYOUT_ONLY},
            {
                "operations": (
                    EditOperation(EditOperationKind.PRESERVE, NormalizedRegion(0, 0, 1, 1)),
                    EditOperation(EditOperationKind.REMOVE, NormalizedRegion(0.1, 0.1, 0.2, 0.2)),
                )
            },
            {
                "operations": (
                    EditOperation(EditOperationKind.REPLACE, NormalizedRegion(0.1, 0.1, 0.2, 0.2)),
                )
            },
            {
                "operations": (
                    EditOperation(
                        EditOperationKind.REMOVE,
                        NormalizedRegion(0.1, 0.1, 0.2, 0.2),
                        reference_position=9,
                    ),
                )
            },
            {"width": 99_999},
            {"seed": -1},
        ],
    )
    def test_contradictory_or_incomplete_intent_is_refused(
        self,
        production: RoughProduction,
        catalog: ReferenceCatalog,
        world: World,
        change: dict[str, Any],
    ) -> None:
        refs = cast(catalog, world)
        artifact = production.create_artifact(PROJECT, "S1E1", 35, panel=2)
        with pytest.raises(CatalogInputError):
            production.request_attempt(artifact.id, edit_spec(refs, **change))

    def test_catalog_rules_apply_to_bundles(
        self, production: RoughProduction, catalog: ReferenceCatalog, world: World
    ) -> None:
        refs = cast(catalog, world)
        other = catalog.create_character("Orin Holt")
        guide = catalog.add_from_source(
            world.id_of(GUIDE),
            ReferenceSpec(reference_class=ReferenceClass.CANON, origin=ReferenceOrigin.SOURCE),
            pdf_page=1,
        )
        artifact = production.create_artifact(PROJECT, "S1E1", 35, panel=2)
        bad_bundles = [
            (BundleEntry(BundleRole.SOURCE_PLATE, guide.id),),
            (BundleEntry(BundleRole.SOURCE_PLATE, uuid.uuid4()),),
            (
                BundleEntry(BundleRole.SOURCE_PLATE, refs["page"].id),
                BundleEntry(
                    BundleRole.CANON,
                    refs["face"].id,
                    character_id=other.id,
                    outfit_id=refs["coat"].id,
                ),
            ),
        ]
        for bundle in bad_bundles:
            with pytest.raises((CatalogInputError, CatalogNotFoundError)):
                production.request_attempt(artifact.id, edit_spec(refs, bundle=bundle))
        with pytest.raises(CatalogInputError):
            production.create_artifact("../escape", "S1E1", 1)
        with pytest.raises(CatalogInputError):
            production.create_artifact(PROJECT, "S1E1", 0)
        assert production.create_artifact(PROJECT, "S1E1", 35, panel=2).id == artifact.id
