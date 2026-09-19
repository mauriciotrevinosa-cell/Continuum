"""The external-resource registry: the registry proposes, a person decides.

Synthetic registry entries only. Covers: normalization of free-text registry
fields, conservative proposed uses, imports that never grant training and never
widen a decision, re-imports that narrow only what the registry withdrew, the
decision rules (and the database refusing what the service refuses), intake
bindings by key, and the HTTP surface.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from continuum_api import create_app
from continuum_config import Settings
from continuum_core.knowledge import AccessState, KnowledgeUse
from continuum_db.models import ExternalResource
from continuum_db.session import session_scope
from continuum_library import CatalogConflictError, CatalogInputError
from continuum_library.resources import ExternalResources, proposed_uses
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from tests.phase1_world import clean_domain_tables
from tests.phase15_world import Phase15World, build_phase15_world

pytestmark = pytest.mark.requires_db

REGISTRY: dict[str, Any] = {
    "schema": "continuum.external-dataset-registry/0.1",
    "updated_at": "2026-09-19",
    "entries": [
        {
            "id": "panel-corpus-v1",
            "kind": "dataset",
            "access": "gated",
            "urls": ["https://example.org/panel-corpus"],
            "scope": ["panel_layout", "retrieval", "validators", "training_candidate"],
            "license_summary": "Experiments allowed; redistribution forbidden.",
            "training_default": "candidate_requires_local_license_acceptance",
        },
        {
            "id": "speaker-linker",
            "kind": "model_and_tool",
            "access": "public",
            "urls": ["https://example.org/speaker-linker"],
            "scope": ["speaker_matching", "validator"],
            "license_summary": "Models are for academic research only.",
            "training_default": "research_only",
        },
        {
            "id": "order-estimator",
            "kind": "tool",
            "access": "public",
            "urls": ["https://example.org/order"],
            "scope": ["reading_order"],
            "license_summary": "MIT code.",
            "training_default": "not_training_data",
        },
        {
            "id": "rumoured-sketch-kit",
            "kind": "unverified_reference",
            "access": "unknown",
            "urls": [],
            "scope": ["line_drawing"],
            "license_summary": "No canonical package found.",
            "training_default": "blocked",
        },
    ],
}


@pytest.fixture
def world(tmp_path: Path, db_settings: Settings) -> Phase15World:
    with session_scope(db_settings) as session:
        clean_domain_tables(session)
    return build_phase15_world(tmp_path)


@pytest.fixture
def settings(world: Phase15World) -> Settings:
    return world.settings()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as value:
        yield value


def _by_key(rows: list[ExternalResource]) -> dict[str, ExternalResource]:
    return {row.key: row for row in rows}


def test_import_proposes_conservatively_and_never_grants_training(settings: Settings) -> None:
    with session_scope(settings) as session:
        resources = ExternalResources(session)
        summary = resources.import_registry(copy.deepcopy(REGISTRY))
        session.commit()
        assert sorted(summary.created) == sorted(e["id"] for e in REGISTRY["entries"])
        rows = _by_key(resources.all())

        corpus = rows["panel-corpus-v1"]
        assert (corpus.kind, corpus.access_state) == ("DATASET", "NOT_REQUESTED")
        assert corpus.proposed_uses == [
            "REFERENCE_ONLY",
            "RETRIEVAL",
            "VALIDATOR",
            "TRAINING_CANDIDATE",
        ]
        # A new resource allows only looking until a person decides otherwise.
        assert corpus.allowed_uses == ["REFERENCE_ONLY"]

        research = rows["speaker-linker"]
        assert research.kind == "MODEL" and research.access_state == "OPEN"
        assert research.proposed_uses == ["REFERENCE_ONLY"]  # research-only: nothing else

        assert rows["order-estimator"].kind == "TOOL"
        assert rows["rumoured-sketch-kit"].kind == "UNVERIFIED"
        assert rows["rumoured-sketch-kit"].proposed_uses == []
        assert rows["rumoured-sketch-kit"].access_state == "UNKNOWN"
        assert not any("TRAINING_APPROVED" in row.allowed_uses for row in rows.values())

        again = resources.import_registry(copy.deepcopy(REGISTRY))
        assert len(again.unchanged) == 4 and not again.created and not again.updated


def test_reimport_narrows_only_what_the_registry_withdrew(settings: Settings) -> None:
    with session_scope(settings) as session:
        resources = ExternalResources(session)
        resources.import_registry(copy.deepcopy(REGISTRY))
        corpus = resources.get("panel-corpus-v1")
        resources.decide(
            "panel-corpus-v1",
            corpus.row_version,
            access_state=AccessState.REQUESTED,
            allowed_uses=[
                KnowledgeUse.RETRIEVAL,
                KnowledgeUse.VALIDATOR,
                KnowledgeUse.TRAINING_CANDIDATE,
            ],
            notes="asked for access",
        )
        session.commit()

        changed = copy.deepcopy(REGISTRY)
        changed["entries"][0]["training_default"] = "blocked_until_image_rights_review"
        summary = resources.import_registry(changed)
        session.commit()
        assert summary.updated == ("panel-corpus-v1",)
        assert summary.narrowed == ("panel-corpus-v1",)
        corpus = resources.get("panel-corpus-v1")
        assert "TRAINING_CANDIDATE" not in corpus.proposed_uses
        assert corpus.allowed_uses == ["REFERENCE_ONLY", "RETRIEVAL", "VALIDATOR"]
        # The person's other decisions are untouched by the import.
        assert corpus.access_state == "REQUESTED"
        assert corpus.notes == "asked for access"


def test_training_needs_access_and_an_accepted_license(settings: Settings) -> None:
    with session_scope(settings) as session:
        resources = ExternalResources(session)
        resources.import_registry(copy.deepcopy(REGISTRY))
        row = resources.get("panel-corpus-v1")

        with pytest.raises(CatalogInputError, match="license accepted"):
            resources.decide(
                row.key, row.row_version, allowed_uses=[KnowledgeUse.TRAINING_APPROVED]
            )
        with pytest.raises(CatalogInputError, match="which terms"):
            resources.decide(row.key, row.row_version, accept_license=True)
        resources.decide(
            row.key,
            row.row_version,
            accept_license=True,
            acceptance_note="terms v2026, accepted on the dataset page",
        )
        with pytest.raises(CatalogInputError, match="access granted"):
            resources.decide(
                row.key, row.row_version, allowed_uses=[KnowledgeUse.TRAINING_APPROVED]
            )
        resources.decide(row.key, row.row_version, access_state=AccessState.GRANTED)
        resources.decide(row.key, row.row_version, allowed_uses=[KnowledgeUse.TRAINING_APPROVED])
        assert row.allowed_uses == ["REFERENCE_ONLY", "TRAINING_APPROVED"]
        with pytest.raises(CatalogConflictError):
            resources.decide(row.key, row.row_version - 1, notes="stale")

        # Withdrawing the acceptance withdraws the approval with it.
        resources.decide(row.key, row.row_version, accept_license=False)
        assert row.allowed_uses == ["REFERENCE_ONLY"]

        for key in ("speaker-linker", "rumoured-sketch-kit"):
            other = resources.get(key)
            if other.kind == "UNVERIFIED":
                with pytest.raises(CatalogInputError, match="never training"):
                    resources.decide(
                        key, other.row_version, allowed_uses=[KnowledgeUse.TRAINING_CANDIDATE]
                    )
        session.commit()


def test_the_database_refuses_training_without_acceptance(settings: Settings) -> None:
    with session_scope(settings) as session:
        ExternalResources(session).import_registry(copy.deepcopy(REGISTRY))
        session.commit()
        with pytest.raises(IntegrityError):
            session.execute(
                update(ExternalResource)
                .where(ExternalResource.key == "order-estimator")
                .values(allowed_uses=["REFERENCE_ONLY", "TRAINING_APPROVED"])
            )
        session.rollback()


def test_registry_entries_never_carry_local_paths(settings: Settings) -> None:
    hostile = copy.deepcopy(REGISTRY)
    hostile["entries"][2]["license_summary"] = "copied from C:/Datasets/order"
    with session_scope(settings) as session:
        with pytest.raises(CatalogInputError, match="local path"):
            ExternalResources(session).import_registry(hostile)


def test_http_surface_imports_decides_and_binds_intake_roots(client: TestClient) -> None:
    imported = client.post("/library/external-resources/import", json=REGISTRY)
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert len(body["summary"]["created"]) == 4
    assert body["intake_roots"] == [{"key": "intake:sketchbook", "collection": "Sketchbook"}]
    corpus = next(r for r in body["resources"] if r["key"] == "panel-corpus-v1")
    assert corpus["allowed_uses"] == ["REFERENCE_ONLY"]
    assert "path" not in str(corpus["registry"]).lower()

    unknown_root = client.post(
        "/library/external-resources/panel-corpus-v1/decision",
        json={"row_version": corpus["row_version"], "intake_root_key": "intake:elsewhere"},
    )
    assert unknown_root.status_code == 422
    assert "configured" in unknown_root.json()["detail"]["message"]

    decided = client.post(
        "/library/external-resources/panel-corpus-v1/decision",
        json={
            "row_version": corpus["row_version"],
            "access_state": "REQUESTED",
            "intake_root_key": "intake:sketchbook",
            "allowed_uses": ["RETRIEVAL", "VALIDATOR"],
        },
    )
    assert decided.status_code == 200, decided.text
    view = decided.json()
    assert view["access_state"] == "REQUESTED"
    assert view["intake_root_key"] == "intake:sketchbook"
    assert view["allowed_uses"] == ["REFERENCE_ONLY", "RETRIEVAL", "VALIDATOR"]

    stale = client.post(
        "/library/external-resources/panel-corpus-v1/decision",
        json={"row_version": corpus["row_version"], "notes": "late"},
    )
    assert stale.status_code == 409

    path_like = client.post(
        "/library/external-resources/panel-corpus-v1/decision",
        json={"row_version": view["row_version"], "intake_root_key": "C:/Datasets"},
    )
    assert path_like.status_code == 422

    listing = client.get("/library/external-resources").json()
    assert {r["key"] for r in listing["resources"]} == {e["id"] for e in REGISTRY["entries"]}


def test_proposed_uses_is_pure_and_stable() -> None:
    entry = REGISTRY["entries"][0]
    assert proposed_uses(entry) == proposed_uses(copy.deepcopy(entry))
    assert "TRAINING_APPROVED" not in proposed_uses({**entry, "scope": ["training_approved"]})
