"""Foundation batches, cross-provider comparison and curated training manifests.

Three separate promises:

* a batch is priced and checked before a penny moves, and nothing starts it
  except a person naming themselves;
* the same calibration stage can be drawn by several backends on equal terms,
  as added evidence - never replacing what a person already approved;
* a training dataset is an exact hashed manifest of material somebody approved
  for training, and style never shares a dataset with structural conditioning.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from continuum_core.catalog import TrainingEligibility
from continuum_core.references import ReferenceClass, ReferenceOrigin
from continuum_db.models import GenerationRecipe, SpendBudget, SpendEntry
from continuum_library import (
    CatalogConflictError,
    CatalogInputError,
    ReferenceCatalog,
    ReferenceSpec,
)
from continuum_library.training import TrainingDatasets, TrainingRuns
from continuum_production import RoughProduction
from continuum_production.benchmark import CalibrationBenchmark
from continuum_production.budget import SpendLedger
from continuum_production.foundation import BATCH_SCHEMA, FoundationBatch, parse_manifest
from continuum_production.layered import PanelConstruction
from continuum_production.manga import MangaProduction
from continuum_providers.pricing import PriceList, usd_to_micros
from continuum_storage import ProjectLibrary
from sqlalchemy import delete
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import World, clean_domain_tables, picture

pytestmark = pytest.mark.requires_db

PROJECT = rough.PROJECT
world = rough.world
settings = rough.settings
session = rough.session
catalog = rough.catalog
worker = rough.worker

PRICES = json.dumps(
    [
        {"provider_id": "test.paid", "model_ref": "cheap", "per_image_micros": 100_000},
        {"provider_id": "test.paid", "model_ref": "good", "per_image_micros": 1_000_000},
    ]
)
CALIBRATION = """# Demo Calibration Chapter v0.1

## CAL-01 — Abandoned settlement establishing

**Source:** `DEMO_S1E2_PANEL_SCRIPT_v0.1.md` — E2 Page 11.
**Source content:** A tiny abandoned settlement enclosed by forest. No people.

**Page construction:**
- Panel 1: full-page wide establishing view from the entering lane. Environment only.

**Primary validation:**
- the inn is the largest surviving building.
"""


@pytest.fixture(autouse=True)
def _clean(session: Session) -> None:
    clean_domain_tables(session)
    # The ledger is operational, not domain: clear it here so each case
    # starts from an untouched budget.
    session.execute(delete(SpendEntry))
    session.execute(delete(SpendBudget))
    session.flush()


def _ledger(session: Session, cap: float = 10.0) -> SpendLedger:
    return SpendLedger(session, prices=PriceList.from_json(PRICES), cap_usd=cap, scope="batch-test")


def _manifest(**extra: Any) -> dict[str, Any]:
    return {
        "schema": BATCH_SCHEMA,
        "project_key": PROJECT,
        "label": "first anchors",
        "defaults": {
            "provider_id": "test.paid",
            "model_ref": "cheap",
            "width": 1024,
            "height": 1024,
        },
        "items": [
            {"id": "sheet-hero", "kind": "CHARACTER_SHEET", "subject": "hero", "count": 2},
            {"id": "cal-01", "kind": "CALIBRATION_RERUN", "cal_id": "CAL-01", "count": 3},
            {"id": "ensemble", "kind": "ENSEMBLE", "count": 1, "model_ref": "good"},
        ],
        **extra,
    }


# -- the foundation batch ---------------------------------------------------
def test_a_batch_is_priced_and_checked_before_anything_moves(session: Session) -> None:
    batch = FoundationBatch(session, _ledger(session))
    plan = batch.plan(_manifest())
    assert plan["images"] == 6
    # five cheap images plus one good one.
    assert plan["total_micros"] == usd_to_micros(1.5)
    assert plan["fits"] is True and plan["blockers"] == []
    # Planning spends nothing.
    assert plan["budget"]["reserved_micros"] == 0


def test_a_batch_that_does_not_fit_is_refused_with_the_numbers(session: Session) -> None:
    batch = FoundationBatch(session, _ledger(session, cap=1.0))
    plan = batch.plan(_manifest())
    assert plan["fits"] is False
    assert any("costs $1.5" in blocker for blocker in plan["blockers"])
    with pytest.raises(CatalogInputError, match="does not fit the budget"):
        batch.reserve(_manifest(), approved_by="creator")
    assert _ledger(session, cap=1.0).state()["reserved_micros"] == 0


def test_an_unpriced_item_blocks_the_batch_rather_than_costing_nothing(
    session: Session,
) -> None:
    manifest = _manifest()
    manifest["items"][0]["model_ref"] = "a-model-nobody-priced"
    plan = FoundationBatch(session, _ledger(session)).plan(manifest)
    assert plan["fits"] is False
    assert any("no configured price covers" in blocker for blocker in plan["blockers"])


def test_only_a_person_starts_a_paid_batch_and_then_every_item_is_held(
    session: Session,
) -> None:
    batch = FoundationBatch(session, _ledger(session))
    with pytest.raises(CatalogInputError, match="started by a person"):
        batch.reserve(_manifest(), approved_by="   ")
    held = batch.reserve(_manifest(), approved_by="creator")
    assert len(held["reserved"]) == 3
    assert held["budget"]["reserved_micros"] == usd_to_micros(1.5)
    entries = _ledger(session).entries()
    assert {row["purpose"] for row in entries} == {
        "CHARACTER_SHEET",
        "CALIBRATION_RERUN",
        "ENSEMBLE",
    }
    assert all(row["subject"].startswith(held["manifest_hash"][:12]) for row in entries)


def test_a_batch_manifest_is_editable_and_validated_not_hardcoded() -> None:
    parsed = parse_manifest(json.dumps(_manifest()))
    assert [item["id"] for item in parsed["items"]] == ["sheet-hero", "cal-01", "ensemble"]
    with pytest.raises(CatalogInputError, match="declares"):
        parse_manifest({"schema": "something-else", "project_key": PROJECT, "items": [{}]})
    with pytest.raises(CatalogInputError, match="appears twice"):
        parse_manifest(
            {
                "schema": BATCH_SCHEMA,
                "project_key": PROJECT,
                "items": [
                    {"id": "a", "kind": "ENSEMBLE"},
                    {"id": "a", "kind": "ENSEMBLE"},
                ],
            }
        )
    with pytest.raises(CatalogInputError, match="a batch builds"):
        parse_manifest(
            {
                "schema": BATCH_SCHEMA,
                "project_key": PROJECT,
                "items": [{"id": "a", "kind": "FINAL_MANGA_PAGE"}],
            }
        )


# -- the cross-provider benchmark -------------------------------------------
def _calibration(session: Session, catalog: ReferenceCatalog, world: World, tmp_path: Path) -> Any:
    cat = ReferenceCatalog(session, sources=world.sources(), derived=world.derived())
    manga = MangaProduction(RoughProduction(session, cat), ProjectLibrary([str(tmp_path / "p")]))
    profile = manga.create_profile(
        PROJECT,
        "benchmark",
        {
            "backend": {"provider_id": "fake.deterministic-page", "width": 320, "height": 460},
            "grammar": {"limit": 0},
        },
    )
    run = manga.start_calibration(
        PROJECT,
        "S1E2",
        1,
        "demo-calibration",
        "v0.1",
        hashlib.sha256(CALIBRATION.encode()).hexdigest(),
        CALIBRATION,
        profile.id,
    )
    session.commit()
    return manga, PanelConstruction(manga), manga.pages(run.id)[0]


def test_the_same_stage_is_drawn_by_each_backend_on_equal_terms(
    session: Session, catalog: ReferenceCatalog, world: World, worker: Any, tmp_path: Path
) -> None:
    _manga, construction, page = _calibration(session, catalog, world, tmp_path)
    benchmark = CalibrationBenchmark(construction)
    with pytest.raises(CatalogInputError, match="at least two providers"):
        benchmark.compare(page.id, 1, "COMPOSITION", ["fake.deterministic-stage"])
    requested = benchmark.compare(
        page.id, 1, "COMPOSITION", ["fake.deterministic-stage", "fake.deterministic-page"]
    )
    session.commit()
    assert [row["provider_id"] for row in requested] == [
        "fake.deterministic-stage",
        "fake.deterministic-page",
    ]
    # Same seed, same contract: only the backend differs.
    assert len({row["seed"] for row in requested}) == 1
    recipes = [
        session.get(GenerationRecipe, construction.rough.attempt(row["attempt_id"]).recipe_id)
        for row in requested
    ]
    assert len({recipe.intent["contract"]["hash"] for recipe in recipes if recipe}) == 1
    assert [recipe.execution["provider_id"] for recipe in recipes if recipe] == [
        "fake.deterministic-stage",
        "fake.deterministic-page",
    ]


def test_a_comparison_adds_evidence_and_replaces_nothing(
    session: Session, catalog: ReferenceCatalog, world: World, worker: Any, tmp_path: Path
) -> None:
    _manga, construction, page = _calibration(session, catalog, world, tmp_path)
    first = construction.request_stage(page.id, 1, "COMPOSITION")
    session.commit()
    assert rough.drain(worker) == 1
    session.expire_all()
    construction.review_stage(first.id, "FREEZE")
    session.commit()

    benchmark = CalibrationBenchmark(construction)
    benchmark.compare(
        page.id, 1, "COMPOSITION", ["fake.deterministic-stage", "fake.deterministic-page"]
    )
    session.commit()
    results = benchmark.results(page.id, 1, "COMPOSITION")
    assert len(results["attempts"]) == 3
    # The frozen attempt is still there, still frozen: a run never approves.
    frozen = next(row for row in results["attempts"] if row["attempt_id"] == str(first.id))
    assert frozen["state"] == "TECHNICAL_PASS"
    assert all(
        row["state"] in {"QUEUED", "GENERATED", "TECHNICAL_PASS"} for row in results["attempts"]
    )
    assert results["comparison"]["providers"] == [
        "fake.deterministic-page",
        "fake.deterministic-stage",
    ]


# -- training manifests ------------------------------------------------------
def _approved(catalog: ReferenceCatalog, shade: int, label: str) -> Any:
    item = catalog.add_upload(
        picture(shade),
        ReferenceSpec(
            reference_class=ReferenceClass.TECHNIQUE,
            origin=ReferenceOrigin.USER_CREATED,
            label=label,
        ),
    )
    item.training_eligibility = TrainingEligibility.APPROVED
    return item


def test_only_material_somebody_approved_for_training_is_admitted(
    session: Session, catalog: ReferenceCatalog
) -> None:
    datasets = TrainingDatasets(session)
    dataset = datasets.create(
        PROJECT, "house-style", "STYLE", "house style", purpose_tags=["LINE_LANGUAGE"]
    )
    not_reviewed = catalog.add_upload(
        picture(51),
        ReferenceSpec(reference_class=ReferenceClass.TECHNIQUE, origin=ReferenceOrigin.SOURCE),
    )
    with pytest.raises(CatalogInputError, match="not approved for training"):
        datasets.add_reference(dataset.id, not_reviewed.id)
    approved = _approved(catalog, 52, "a line study")
    item = datasets.add_reference(dataset.id, approved.id, caption="clean contour study")
    assert item.training_eligibility == "APPROVED"
    assert item.purpose_tags == ["LINE_LANGUAGE"]


def test_style_and_structural_conditioning_never_share_a_dataset(
    session: Session, catalog: ReferenceCatalog
) -> None:
    datasets = TrainingDatasets(session)
    dataset = datasets.create(PROJECT, "house-style", "STYLE", "house style")
    approved = _approved(catalog, 53, "a pose sheet")
    with pytest.raises(CatalogInputError, match="does not teach pose"):
        datasets.add_reference(dataset.id, approved.id, purpose_tags=["POSE"])
    structure = datasets.create(PROJECT, "poses", "STRUCTURE", "pose conditioning")
    datasets.add_reference(structure.id, approved.id, purpose_tags=["POSE"])


def test_locking_fixes_the_split_and_hashes_the_manifest(
    session: Session, catalog: ReferenceCatalog
) -> None:
    datasets = TrainingDatasets(session)
    dataset = datasets.create(
        PROJECT,
        "house-style",
        "STYLE",
        "house style",
        purpose_tags=["LINE_LANGUAGE"],
        validation=0.25,
        seed=17012026,
    )
    for shade in range(60, 68):
        datasets.add_reference(dataset.id, _approved(catalog, shade, f"study {shade}").id)
    with pytest.raises(CatalogInputError, match="human reviewer"):
        datasets.lock(dataset.id, "  ")
    locked = datasets.lock(dataset.id, "creator")
    assert locked.state == "LOCKED"
    assert locked.counts == {"items": 8, "train": 6, "validation": 2}
    assert len(str(locked.manifest_hash)) == 64
    # A locked manifest never changes.
    with pytest.raises(CatalogConflictError, match="locked manifest never changes"):
        datasets.add_reference(dataset.id, _approved(catalog, 70, "late").id)
    # The same manifest always splits the same way.
    splits = {item.item_key: item.split for item in datasets.items(dataset.id)}
    datasets._assign_splits(locked, datasets.items(dataset.id))
    assert {item.item_key: item.split for item in datasets.items(dataset.id)} == splits


def test_a_training_run_needs_a_locked_manifest_and_a_reproducible_output(
    session: Session, catalog: ReferenceCatalog
) -> None:
    datasets, runs = TrainingDatasets(session), TrainingRuns(session)
    dataset = datasets.create(
        PROJECT, "house-style", "STYLE", "house style", purpose_tags=["SCREENTONE"]
    )
    datasets.add_reference(dataset.id, _approved(catalog, 71, "tone study").id)
    with pytest.raises(CatalogConflictError, match="locked manifest only"):
        runs.plan(dataset.id, "base-model", {"steps": 1000})
    datasets.lock(dataset.id, "creator")
    run = runs.plan(dataset.id, "base-model", {"steps": 1000, "rank": 16}, label="first pass")
    assert run.state == "PLANNED" and len(run.config_hash) == 64
    with pytest.raises(CatalogInputError, match="not reproducible without"):
        runs.record_output(run.id, {"name": "adapter.safetensors"})
    done = runs.record_output(
        run.id,
        {
            "name": "adapter.safetensors",
            "sha256": "e" * 64,
            "license": "a permissive licence",
            "trained_on": "a notebook GPU session",
        },
    )
    assert done.state == "SUCCEEDED"


def test_a_second_version_is_a_second_row(session: Session) -> None:
    datasets = TrainingDatasets(session)
    first = datasets.create(PROJECT, "house-style", "STYLE", "house style")
    second = datasets.create(PROJECT, "house-style", "STYLE", "house style, wider")
    assert (first.version, second.version) == (1, 2)
    assert len(datasets.all(PROJECT)) == 2
