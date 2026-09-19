"""M2 closeout: the rough workflow round trip, honest approval semantics, reference grounding.

What M2 proves is the *workflow* - panel script and recipe, reference bundle,
attempt, regenerate, review, persistence - not manga. These tests pin the
closeout decisions:

* the whole round trip survives a restart with every recorded fact intact:
  artifact identity, recipe and hashes, the exact references and their
  provenance snapshot, the source plate, seeds, ancestry, notes and states;
* a technical pass is not a creative approval: a workflow test, a non-canon
  sample and a test render can pass technically and can never be approved as
  art - enforced by the service and by a database check - and none of them
  counts toward completion;
* a character manifest resolves a complementary reference set by facet and
  lane; "preferred" only ranks; fan art needs a project standing; an original
  project character is never grounded in franchise material and nothing is
  substituted for missing references;
* upgrading a database that holds M2 data reclassifies its "approved" test
  renders as technical passes without losing anything.

All content is invented (D-18 / A-05).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from continuum_api import create_app
from continuum_config import Settings
from continuum_core import NormalizedRegion
from continuum_core.references import (
    AttemptState,
    BundleRole,
    CharacterAspect,
    CharacterOrigin,
    DerivativeKind,
    EditOperationKind,
    ProjectStanding,
    ReferenceClass,
    ReferenceOrigin,
    RenderOutput,
    ReviewDecision,
    RoughMode,
    RoughPurpose,
)
from continuum_db.session import reset_engine, session_scope
from continuum_library import (
    CatalogInputError,
    CharacterLink,
    ReferenceCatalog,
    ReferenceSpec,
    StandingSpec,
)
from continuum_production import (
    BundleEntry,
    EditOperation,
    ManifestRequest,
    ReferenceManifests,
    RoughIntentSpec,
    RoughProduction,
    character_manifest,
    completion_view,
)
from continuum_storage import ProjectLibrary
from continuum_worker.main import Worker
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.acceptance.test_110_14_migrations import _alembic
from tests.phase1_world import MANGA, World, picture
from tests.renderers import artwork_registry

pytestmark = pytest.mark.requires_db

# The rough production world and its fixtures, shared rather than copied.
PROJECT, SMALL, cast, drain = rough.PROJECT, rough.SMALL, rough.cast, rough.drain
world = rough.world
settings = rough.settings
session = rough.session
catalog = rough.catalog
production = rough.production
worker = rough.worker


def _body_reference(catalog: ReferenceCatalog, world: World, hero: Any) -> Any:
    return catalog.add_from_source(
        world.id_of(MANGA),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.SOURCE,
            region=NormalizedRegion(0.1, 0.1, 0.6, 0.8),
            characters=(
                CharacterLink(hero.id, CharacterAspect.FULL_BODY),
                CharacterLink(hero.id, CharacterAspect.OUTFIT),
            ),
        ),
        page_index=2,
    )


def _workflow_spec(refs: dict[str, Any], body: Any) -> RoughIntentSpec:
    hero = refs["hero"]
    return RoughIntentSpec(
        mode=RoughMode.SOURCE_DERIVED_EDIT,
        bundle=(
            BundleEntry(BundleRole.SOURCE_PLATE, refs["page"].id, label="scene plate"),
            BundleEntry(
                BundleRole.CANON, refs["face"].id, character_id=hero.id, aspect=CharacterAspect.FACE
            ),
            BundleEntry(
                BundleRole.CANON, body.id, character_id=hero.id, aspect=CharacterAspect.FULL_BODY
            ),
            BundleEntry(BundleRole.STYLE, refs["style"].id),
        ),
        operations=(
            EditOperation(EditOperationKind.PRESERVE, NormalizedRegion(0.0, 0.0, 1.0, 0.3)),
            EditOperation(
                EditOperationKind.REPLACE,
                NormalizedRegion(0.5, 0.4, 0.4, 0.5),
                character_id=hero.id,
                reference_position=1,
            ),
        ),
        brief="Scene slice: the hero looks up.",
        **SMALL,
    )


# ---------------------------------------------------------------------------
def test_workflow_round_trip_survives_a_restart(
    production: RoughProduction,
    catalog: ReferenceCatalog,
    session: Session,
    settings: Settings,
    world: World,
    worker: Worker,
) -> None:
    refs = cast(catalog, world)
    body = _body_reference(catalog, world, refs["hero"])
    artifact = production.create_artifact(
        PROJECT,
        "S1E1",
        35,
        title="Scene slice",
        panel_script_document="demo-panel-script",
        panel_script_version="0.1",
        purpose=RoughPurpose.WORKFLOW_TEST,
    )
    first = production.request_attempt(artifact.id, _workflow_spec(refs, body))
    session.commit()
    assert drain(worker) == 1
    session.expire_all()
    _review, second = production.review(
        first.id, ReviewDecision.REGENERATE, notes="another take", seed=4242
    )
    assert second is not None
    session.commit()
    assert drain(worker) == 1
    session.expire_all()

    with pytest.raises(CatalogInputError, match="workflow test"):
        production.review(second.id, ReviewDecision.CREATIVE_APPROVE)
    session.rollback()
    production.review(second.id, ReviewDecision.TECHNICAL_PASS, notes="workflow verified")
    session.commit()
    before = {
        "artifact": production.artifact(artifact.id),
        "second": production.attempt(second.id),
    }
    recorded = {
        "purpose": before["artifact"].purpose,
        "intent_hash": production.recipe(before["second"].recipe_id).intent_hash,
        "execution_hash": production.recipe(before["second"].recipe_id).execution_hash,
        "inputs": [
            (row.position, row.role, row.reference_id, row.aspect, row.provenance)
            for row in production.inputs(second.id)
        ],
        "derivatives": sorted((d.kind, d.content_hash) for d in production.derivatives(second.id)),
        "output": production.attempt(second.id).content_hash,
    }
    assert recorded["inputs"][1][4]["origin"] == "SOURCE"
    assert recorded["inputs"][1][4]["asset_content_hash"]
    assert {kind for kind, _ in recorded["derivatives"]} == {
        DerivativeKind.OUTPUT,
        DerivativeKind.SOURCE_CROP,
        DerivativeKind.MASK,
    }

    artifact_id, first_id, second_id = artifact.id, first.id, second.id
    # -- restart: every connection gone, a new API process, a new worker -------
    session.close()
    reset_engine()
    api = create_app(settings)
    with TestClient(api) as client:
        listed = client.get(f"/projects/{PROJECT}/rough-artifacts").json()
        assert [a["id"] for a in listed] == [str(artifact_id)]
        view = listed[0]
        assert view["purpose"] == "WORKFLOW_TEST" and view["test_only"] is True
        assert view["technical_pass_attempt_id"] == str(second_id)
        assert view["creative_approved_attempt_id"] is None
        assert view["counts_toward_completion"] is False
        assert view["panel_script"] == {"document": "demo-panel-script", "version": "0.1"}
        assert [a["attempt"] for a in view["attempts"]] == [2, 1]

        detail = client.get(f"/production/attempts/{second_id}").json()
        assert detail["state"] == "TECHNICAL_PASS" and detail["output_class"] == "TEST_RENDER"
        assert detail["seed"] == 4242 and detail["parent_attempt_id"] == str(first_id)
        assert detail["recipe"]["intent_hash"] == recorded["intent_hash"]
        assert detail["recipe"]["execution_hash"] == recorded["execution_hash"]
        assert "CREATIVE_APPROVE" not in detail["allowed_decisions"]
        bundle = [e for role in detail["bundle"].values() for e in role]
        assert sorted((e["position"], e["reference_id"]) for e in bundle) == sorted(
            (p, str(r)) for p, _role, r, _a, _prov in recorded["inputs"]
        )
        assert {e["position"]: e["provenance"] for e in bundle} == {
            p: prov for p, _role, _r, _a, prov in recorded["inputs"]
        }
        assert [r["notes"] for r in detail["reviews"]] == ["workflow verified"]
        parent = client.get(f"/production/attempts/{first_id}").json()
        assert [r["decision"] for r in parent["reviews"]] == ["REGENERATE"]
        assert parent["reviews"][0]["notes"] == "another take"

        chain = client.get(f"/production/attempts/{second_id}/provenance").json()
        assert chain["output_hash"] == recorded["output"]
        assert chain["lineage"] == [{"attempt_id": str(first_id), "attempt": 1}]
        assert chain["artifact"]["purpose"] == "WORKFLOW_TEST"
        plate = client.get(
            f"/production/attempts/{second_id}/image", params={"kind": "SOURCE_CROP"}
        )
        assert plate.status_code == 200

        completion = client.get(f"/projects/{PROJECT}/rough-completion").json()
        assert completion["production"] == {
            "artifacts": 0,
            "creative_approved": 0,
            "final_approved": 0,
        }
        assert completion["workflow_tests"] == {"artifacts": 1, "technical_pass": 1}

    # The restarted worker can still regenerate from the persisted bundle.
    with session_scope(settings) as fresh:
        again = RoughProduction(
            fresh, ReferenceCatalog(fresh, sources=world.sources(), derived=world.derived())
        )
        _r, third = again.review(second_id, ReviewDecision.REGENERATE, seed=7)
        assert third is not None
        third_id = third.id
    restarted = Worker(settings)
    restarted.register()
    assert drain(restarted) == 1
    with session_scope(settings) as fresh:
        again = RoughProduction(
            fresh, ReferenceCatalog(fresh, sources=world.sources(), derived=world.derived())
        )
        assert again.attempt(third_id).state is AttemptState.GENERATED
        assert [row.provenance for row in again.inputs(third_id)] == [
            prov for _p, _role, _r, _a, prov in recorded["inputs"]
        ]


def test_tests_and_production_are_separate_and_counted_apart(
    production: RoughProduction,
    catalog: ReferenceCatalog,
    session: Session,
    world: World,
    worker: Worker,
) -> None:
    refs = cast(catalog, world)
    body = _body_reference(catalog, world, refs["hero"])
    spec = _workflow_spec(refs, body)
    real = production.create_artifact(PROJECT, "S1E1", 35)
    test = production.create_artifact(PROJECT, "S1E1", 35, purpose=RoughPurpose.WORKFLOW_TEST)
    sample = production.create_artifact(PROJECT, "SAMPLE", 1, purpose=RoughPurpose.NON_CANON_SAMPLE)
    assert len({real.id, test.id, sample.id}) == 3, "a test never takes a production page's slot"
    assert production.create_artifact(PROJECT, "S1E1", 35).id == real.id

    sketched = production.request_attempt(real.id, spec)
    session.commit()
    drain(worker)
    session.expire_all()
    sketched = production.attempt(sketched.id)
    assert sketched.output_class is RenderOutput.TEST_RENDER
    with pytest.raises(CatalogInputError, match="test renderer"):
        production.review(sketched.id, ReviewDecision.CREATIVE_APPROVE)
    session.rollback()

    # The database refuses creative approval of a test render, whatever the code does.
    with pytest.raises(IntegrityError):
        session.execute(
            text("UPDATE rough_attempt SET state = 'CREATIVE_APPROVED' WHERE id = :id"),
            {"id": sketched.id},
        )
        session.flush()
    session.rollback()

    worker.providers = artwork_registry()
    drawn = production.request_attempt(real.id, spec)
    in_sample = production.request_attempt(sample.id, spec)
    in_test = production.request_attempt(test.id, spec)
    session.commit()
    assert drain(worker) == 3
    session.expire_all()
    for attempt in (drawn, in_sample, in_test):
        assert production.attempt(attempt.id).output_class is RenderOutput.ARTWORK_CANDIDATE
    with pytest.raises(CatalogInputError, match="non-canon sample"):
        production.review(in_sample.id, ReviewDecision.CREATIVE_APPROVE)
    session.rollback()
    with pytest.raises(CatalogInputError, match="workflow test"):
        production.review(in_test.id, ReviewDecision.FINAL_APPROVE)
    session.rollback()
    with pytest.raises(CatalogInputError, match="Only a creatively approved"):
        production.review(drawn.id, ReviewDecision.FINAL_APPROVE)
    session.rollback()

    production.review(in_sample.id, ReviewDecision.TECHNICAL_PASS, notes="usable quality")
    production.review(in_test.id, ReviewDecision.TECHNICAL_PASS)
    production.review(drawn.id, ReviewDecision.CREATIVE_APPROVE)
    session.commit()
    assert production.attempt(drawn.id).state is AttemptState.CREATIVE_APPROVED
    with pytest.raises(CatalogInputError, match="creatively approved production"):
        production.promote_to_continuity(in_sample.id)
    session.rollback()
    assert completion_view(production, PROJECT) == {
        "production": {"artifacts": 1, "creative_approved": 1, "final_approved": 0},
        "workflow_tests": {"artifacts": 1, "technical_pass": 1},
        "non_canon_samples": {"artifacts": 1, "technical_pass": 1},
        "calibration": {"artifacts": 0, "creative_approved": 0},
    }


def test_character_manifest_resolves_complementary_references(
    catalog: ReferenceCatalog, session: Session, world: World, tmp_path: Path
) -> None:
    refs = cast(catalog, world)
    hero = refs["hero"]
    body = _body_reference(catalog, world, hero)
    acting = catalog.add_upload(
        picture(71),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.OFFICIAL_ART,
            characters=(CharacterLink(hero.id, CharacterAspect.EXPRESSION),),
        ),
    )
    fan_face = catalog.add_upload(
        picture(72),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.FAN_ART,
            creator_handle="an-artist",
            characters=(CharacterLink(hero.id, CharacterAspect.FACE),),
        ),
    )
    approved_fan_pose = catalog.add_upload(
        picture(73),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.FAN_ART,
            characters=(CharacterLink(hero.id, CharacterAspect.POSE),),
            standings=(StandingSpec(PROJECT, ProjectStanding.USEFUL),),
        ),
    )
    unsorted = catalog.add_upload(
        picture(74),
        ReferenceSpec(
            reference_class=ReferenceClass.UNSORTED,
            origin=ReferenceOrigin.FAN_ART,
            characters=(CharacterLink(hero.id, CharacterAspect.ACCESSORY),),
        ),
    )
    session.commit()

    manifest = character_manifest(session, catalog, hero.id, project_key=PROJECT)
    ids = {
        facet: [e["reference_id"] for e in entries] for facet, entries in manifest["facets"].items()
    }
    assert ids["identity"] == [str(refs["face"].id)], "the preferred face, and only approved faces"
    assert ids["body"] == [str(body.id)] and ids["wardrobe"] == [str(body.id)]
    assert ids["expression"] == [str(acting.id)]
    assert ids["pose"] == [str(approved_fan_pose.id)]
    assert ids["accessories"] == []
    lanes = {
        e["reference_id"]: e["lane"] for entries in manifest["facets"].values() for e in entries
    }
    assert lanes[str(body.id)] == "canonical_manga" and lanes[str(acting.id)] == "official_art"
    assert lanes[str(approved_fan_pose.id)] == "supplemental"
    skipped = {e["reference_id"]: e["reason"] for e in manifest["not_selected"]}
    assert "standing" in skipped[str(fan_face.id)]
    assert "not sorted" in skipped[str(unsorted.id)]
    assert manifest["usable"] is True and manifest["missing"] == []
    face = manifest["facets"]["identity"][0]["reference"]
    assert face["rights_status"] and face["provenance"], (
        "every selected reference carries provenance"
    )

    built = ReferenceManifests(session, catalog).build(
        ManifestRequest(project_key=PROJECT, character_ids=(hero.id,))
    )
    roles = {r["id"]: r["roles"] for r in built.manifest["references"]}
    assert f"character:{hero.id}:identity:FACE" in roles[str(refs["face"].id)]
    assert f"character:{hero.id}:body:FULL_BODY" in roles[str(body.id)]
    assert f"character:{hero.id}:wardrobe:OUTFIT" in roles[str(body.id)]
    assert str(fan_face.id) not in roles and str(unsorted.id) not in roles
    assert len(built.manifest["characters"][0]["facets"]["identity"]) == 1

    # -- an original project character ---------------------------------------
    project_dir = tmp_path / "projects" / PROJECT
    project_dir.mkdir(parents=True)
    (project_dir / "VISUAL_PACK_v0.1.md").write_text(
        "# Visual pack\n\n**Status:** APPROVED BASE VISUAL CANON\n\nSoft features.\n",
        encoding="utf-8",
    )
    (project_dir / "continuum.project.json").write_text(
        json.dumps(
            {
                "id": PROJECT,
                "title": "Demo Project",
                "documents": [
                    {"id": "visual-pack", "path": "VISUAL_PACK_v0.1.md", "lifecycle": "APPROVED"}
                ],
            }
        ),
        encoding="utf-8",
    )
    projects = ProjectLibrary([str(tmp_path / "projects")])
    with pytest.raises(CatalogInputError, match="belongs to a project"):
        catalog.create_character("Lone Original", origin=CharacterOrigin.PROJECT_ORIGINAL)
    with pytest.raises(CatalogInputError, match="source-work character"):
        catalog.create_character("Borrowed", design_documents=["visual-pack"])
    session.rollback()
    original = catalog.create_character(
        "Rowan Original",
        origin=CharacterOrigin.PROJECT_ORIGINAL,
        project_key=PROJECT,
        design_documents=["visual-pack"],
    )
    franchise_face = catalog.add_from_source(
        world.id_of(MANGA),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.SOURCE,
            characters=(CharacterLink(original.id, CharacterAspect.FACE, preferred=True),),
        ),
        page_index=0,
    )
    creator_photo = catalog.add_upload(
        picture(75),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.USER_CREATED,
            characters=(CharacterLink(original.id, CharacterAspect.FACE),),
        ),
    )
    session.commit()
    mine = character_manifest(session, catalog, original.id, project_key=PROJECT, projects=projects)
    assert [e["reference_id"] for e in mine["facets"]["identity"]] == [str(creator_photo.id)]
    assert mine["facets"]["identity"][0]["lane"] == "project_created"
    assert (
        "franchise"
        in {e["reference_id"]: e["reason"] for e in mine["not_selected"]}[str(franchise_face.id)]
    )
    assert mine["missing"] == ["body"] and mine["usable"] is False
    assert any("nothing is substituted" in w for w in mine["warnings"])
    assert mine["design_documents"] == [
        {
            "id": "visual-pack",
            "title": "Visual pack",
            "lifecycle": "APPROVED",
            "commit": None,
            "available": True,
        }
    ]


def test_m2_data_is_reclassified_by_the_upgrade(
    settings: Settings, world: World, session: Session
) -> None:
    session.close()
    reset_engine()
    home = str(settings.data_home)
    assert _alembic("upgrade", "head", data_home=home).returncode == 0
    down = _alembic("downgrade", "0003_phase15", data_home=home)
    assert down.returncode == 0, down.stderr

    artifact, recipe, first, second = (uuid.uuid4() for _ in range(4))
    digest = "a" * 64
    with session_scope(settings) as db:
        db.execute(
            text(
                "INSERT INTO rough_artifact (id, project_key, episode, page, kind, title, brief)"
                " VALUES (:id, :p, 'S1E1', 35, 'PAGE', 'Scene slice', '')"
            ),
            {"id": artifact, "p": PROJECT},
        )
        db.execute(
            text(
                "INSERT INTO generation_recipe (id, mode, recipe_schema_version,"
                " template_package_version, intent, execution, intent_hash, execution_hash)"
                " VALUES (:id, 'SOURCE_DERIVED_EDIT', 1, 'rough.v1', '{}', :ex, :h, :h)"
            ),
            {"id": recipe, "h": digest, "ex": json.dumps({"seed": 11, "workflow": "sketch.v1"})},
        )
        for attempt_id, number, state, parent in (
            (first, 1, "APPROVED", None),
            (second, 2, "REJECTED", first),
        ):
            db.execute(
                text(
                    "INSERT INTO rough_attempt (id, artifact_id, attempt, recipe_id,"
                    " parent_attempt_id, state, content_hash, mime, width, height)"
                    " VALUES (:id, :a, :n, :r, :parent, :state, :h, 'image/png', 480, 360)"
                ),
                {
                    "id": attempt_id,
                    "a": artifact,
                    "n": number,
                    "r": recipe,
                    "parent": parent,
                    "state": state,
                    "h": digest,
                },
            )
        db.execute(
            text(
                "INSERT INTO attempt_input (id, attempt_id, position, role, locator, label)"
                " VALUES (:id, :a, 0, 'SOURCE_PLATE', 'image:sha256:' || :h, 'plate')"
            ),
            {"id": uuid.uuid4(), "a": first, "h": digest},
        )
        for decision, notes in (("APPROVE", "looks right"), ("REGENERATE", "another")):
            db.execute(
                text(
                    "INSERT INTO attempt_review (id, attempt_id, decision, notes)"
                    " VALUES (:id, :a, :d, :n)"
                ),
                {"id": uuid.uuid4(), "a": first, "d": decision, "n": notes},
            )
    reset_engine()
    up = _alembic("upgrade", "head", data_home=home)
    assert up.returncode == 0, up.stderr

    with session_scope(settings) as db:
        attempts = dict(
            db.execute(
                text(
                    "SELECT attempt, state || '/' || output_class FROM rough_attempt"
                    " WHERE artifact_id = :a"
                ),
                {"a": artifact},
            ).all()
        )
        assert attempts == {1: "TECHNICAL_PASS/TEST_RENDER", 2: "REJECTED/TEST_RENDER"}
        reviews = db.execute(
            text(
                "SELECT decision, reclassified_from, notes FROM attempt_review"
                " WHERE attempt_id = :a ORDER BY decision"
            ),
            {"a": first},
        ).all()
        assert [tuple(r) for r in reviews] == [
            ("REGENERATE", None, "another"),
            ("TECHNICAL_PASS", "APPROVE", "looks right"),
        ]
        purpose = db.execute(
            text("SELECT purpose FROM rough_artifact WHERE id = :a"), {"a": artifact}
        ).scalar_one()
        assert purpose == "WORKFLOW_TEST"
        kept = db.execute(
            text("SELECT count(*) FROM attempt_input WHERE attempt_id = :a"), {"a": first}
        ).scalar_one()
        assert kept == 1
