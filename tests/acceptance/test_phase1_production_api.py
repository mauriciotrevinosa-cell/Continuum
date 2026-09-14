"""Rough production over HTTP: the API records and enqueues; the worker renders.

Under test (Phase 1 M2 API):

* an artifact is created for a real project page/panel; the panel script's
  version comes from the project manifest, never from the client;
* a source-derived edit is requested by ids only, rendered by the standalone
  worker loop, reviewed, regenerated, and promoted to continuity;
* images are served by attempt id and kind; provenance leads back to the
  held page without naming a path;
* readiness says honestly that the renderer is a deterministic fake;
* unknown projects/documents are 404; undeclared fields and bad intent 422.

PostgreSQL (the isolated test database). All content is invented.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from continuum_api import create_app
from continuum_config import Settings
from continuum_db.models import Job
from continuum_db.models import Worker as WorkerRow
from continuum_db.session import session_scope
from continuum_imaging import probe
from continuum_worker import register_default_handlers
from continuum_worker.main import Worker
from fastapi.testclient import TestClient
from sqlalchemy import delete

from tests.conftest import TEST_DATABASE_URL
from tests.phase1_world import (
    MANGA,
    MANGA_ENTRIES,
    World,
    build_world,
    clean_domain_tables,
    snapshot,
)
from tests.renderers import artwork_registry

pytestmark = pytest.mark.requires_db

PROJECT = "demo-saga"


@pytest.fixture
def world(tmp_path: Path, db_settings: Settings) -> World:
    with session_scope(db_settings) as session:
        clean_domain_tables(session)
        session.execute(delete(Job))
        session.execute(delete(WorkerRow))
    register_default_handlers()
    world = build_world(tmp_path)
    project = tmp_path / "projects" / PROJECT
    project.mkdir(parents=True)
    (project / "PANEL_SCRIPT_v0.3.md").write_text("# Panel script\n\nPage 35.\n", encoding="utf-8")
    (project / "continuum.project.json").write_text(
        json.dumps(
            {
                "id": PROJECT,
                "title": "Demo Saga",
                "kind": "what-if",
                "documents": [
                    {
                        "id": "panel-script",
                        "path": "PANEL_SCRIPT_v0.3.md",
                        "category": "panel-script",
                        "section": "story",
                        "lifecycle": "APPROVED",
                        "version": "0.3",
                        "episode": "S1E1",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return world


@pytest.fixture
def settings(world: World) -> Settings:
    return Settings(
        _env_file=None,
        data_home=str(world.data_home),
        source_vault_root=str(world.vault),
        acquisition_data_dir=str(world.acquisition_dir),
        project_sources=str(world.root / "projects"),
        database_url=TEST_DATABASE_URL,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def worker(settings: Settings) -> Worker:
    w = Worker(settings)
    w.register()
    return w


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_request_render_review_regenerate_and_promote(
    client: TestClient, worker: Worker, world: World
) -> None:
    before = snapshot(world.vault)
    readiness = ok(client.get("/production/readiness"))
    assert readiness["permitted"] is True and readiness["is_fake"] is True

    hero = ok(client.post("/library/characters", json={"display_name": "Aster Vale"}), 201)
    page = ok(
        client.post(
            "/library/references/from-source",
            json={
                "media_id": world.id_of(MANGA),
                "page_index": 1,
                "spec": {
                    "reference_class": "CANON",
                    "uses": ["SOURCE_PLATE"],
                    "panel_sources": [
                        {
                            "project_key": PROJECT,
                            "episode": "S1E1",
                            "page": 35,
                            "role": "SOURCE_PLATE",
                        }
                    ],
                },
            },
        ),
        201,
    )
    face = ok(
        client.post(
            "/library/references/from-source",
            json={
                "media_id": world.id_of(MANGA),
                "page_index": 0,
                "spec": {
                    "reference_class": "CANON",
                    "region": {"x": 0.2, "y": 0.1, "width": 0.4, "height": 0.3},
                    "characters": [{"character_id": hero["id"], "aspect": "FACE"}],
                },
            },
        ),
        201,
    )

    artifact = ok(
        client.post(
            f"/projects/{PROJECT}/rough-artifacts",
            json={
                "episode": "S1E1",
                "page": 35,
                "panel": 2,
                "chapter": 1,
                "panel_script_document": "panel-script",
            },
        ),
        201,
    )
    assert artifact["panel_script"] == {"document": "panel-script", "version": "0.3"}
    detail = ok(client.get(f"/production/rough-artifacts/{artifact['id']}"))
    assert [s["reference"]["id"] for s in detail["scene_sources"]] == [page["id"]]

    queued = ok(
        client.post(
            f"/production/rough-artifacts/{artifact['id']}/attempts",
            json={
                "mode": "SOURCE_DERIVED_EDIT",
                "bundle": [
                    {"role": "SOURCE_PLATE", "reference_id": page["id"]},
                    {
                        "role": "CANON",
                        "reference_id": face["id"],
                        "character_id": hero["id"],
                        "aspect": "FACE",
                    },
                ],
                "characters": [{"character_id": hero["id"], "acting_direction": "startled"}],
                "operations": [
                    {"kind": "PRESERVE", "region": {"x": 0, "y": 0, "width": 1, "height": 0.3}},
                    {
                        "kind": "REPLACE",
                        "region": {"x": 0.5, "y": 0.4, "width": 0.4, "height": 0.5},
                        "character_id": hero["id"],
                    },
                ],
                "width": 480,
                "height": 360,
                "execution": {"strength": 0.6},
            },
        ),
        202,
    )
    assert queued["display_state"] == "QUEUED"
    assert queued["recipe"]["execution"]["strength"] == 0.6
    assert client.get(f"/production/attempts/{queued['id']}/image").status_code == 404

    assert worker.run_once() is True
    rendered = ok(client.get(f"/production/attempts/{queued['id']}"))
    assert rendered["display_state"] == "GENERATED"
    image = client.get(f"/production/attempts/{queued['id']}/image")
    assert image.status_code == 200 and probe(image.content).width == 480
    mask = client.get(f"/production/attempts/{queued['id']}/image", params={"kind": "MASK"})
    assert mask.status_code == 200

    provenance = client.get(f"/production/attempts/{queued['id']}/provenance")
    chain = ok(provenance)
    plate = next(s for s in chain["sources"] if s["role"] == "SOURCE_PLATE")
    assert plate["locator"].endswith(f"#entry={MANGA_ENTRIES[1]}")
    assert plate["source"]["page_index"] == 1
    assert str(world.vault) not in provenance.text and "Demo Orbit/manga" not in provenance.text

    regenerated = ok(
        client.post(
            f"/production/attempts/{queued['id']}/review",
            json={"decision": "REGENERATE", "notes": "another take", "seed": 77},
        )
    )
    assert regenerated["attempt"]["state"] == "REJECTED"
    second = regenerated["regenerated"]
    assert second["attempt"] == 2 and second["seed"] == 77
    assert worker.run_once() is True
    # The sketch renderer draws test renders: creative approval is refused, with the reason.
    assert second["output_class"] is None and second["allowed_decisions"] == []
    drawn = ok(client.get(f"/production/attempts/{second['id']}"))
    assert drawn["output_class"] == "TEST_RENDER" and drawn["test_only"] is True
    assert "CREATIVE_APPROVE" not in drawn["allowed_decisions"]
    refused = client.post(
        f"/production/attempts/{second['id']}/review", json={"decision": "CREATIVE_APPROVE"}
    )
    assert refused.status_code == 422 and "test renderer" in refused.text
    passed = ok(
        client.post(
            f"/production/attempts/{second['id']}/review", json={"decision": "TECHNICAL_PASS"}
        )
    )
    assert passed["attempt"]["state"] == "TECHNICAL_PASS"
    assert (
        client.post(f"/production/attempts/{second['id']}/continuity", json={}).status_code == 422
    )

    # Drawn by a renderer whose images are artwork candidates, it can be approved as rough manga.
    worker.providers = artwork_registry()
    third = ok(
        client.post(
            f"/production/attempts/{second['id']}/review",
            json={"decision": "REGENERATE", "notes": "with a model"},
        )
    )["regenerated"]
    assert worker.run_once() is True
    approved = ok(
        client.post(
            f"/production/attempts/{third['id']}/review", json={"decision": "CREATIVE_APPROVE"}
        )
    )
    assert approved["attempt"]["state"] == "CREATIVE_APPROVED"
    second = third
    continuity = ok(
        client.post(
            f"/production/attempts/{second['id']}/continuity",
            json={
                "label": "p35 panel 2 approved",
                "characters": [{"character_id": hero["id"], "aspect": "FULL_BODY"}],
            },
        ),
        201,
    )
    assert (
        continuity["origin"] == "PROJECT_APPROVED" and continuity["reference_class"] == "CONTINUITY"
    )
    history = ok(client.get(f"/projects/{PROJECT}/rough-artifacts"))
    assert [a["attempt"] for a in history[0]["attempts"]] == [3, 2, 1]
    completion = ok(client.get(f"/projects/{PROJECT}/rough-completion"))
    assert completion["production"] == {"artifacts": 1, "creative_approved": 1, "final_approved": 0}
    assert snapshot(world.vault) == before


def test_errors_are_honest(client: TestClient, world: World) -> None:
    assert (
        client.post(
            "/projects/no-such-project/rough-artifacts", json={"episode": "S1E1", "page": 1}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/projects/{PROJECT}/rough-artifacts",
            json={"episode": "S1E1", "page": 1, "panel_script_document": "missing"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/projects/{PROJECT}/rough-artifacts",
            json={"episode": "S1E1", "page": 1, "panel_script_version": "9.9"},
        ).status_code
        == 422
    )
    artifact = ok(
        client.post(f"/projects/{PROJECT}/rough-artifacts", json={"episode": "S1E1", "page": 2}),
        201,
    )
    for body in (
        {"mode": "SOURCE_DERIVED_EDIT"},
        {"mode": "NOT_A_MODE"},
        {"mode": "LAYOUT_ONLY", "path": "C:\\ContinuumVault"},
        {
            "mode": "LAYOUT_ONLY",
            "placements": [{"region": {"x": 0.9, "y": 0.9, "width": 0.5, "height": 0.5}}],
        },
    ):
        response = client.post(f"/production/rough-artifacts/{artifact['id']}/attempts", json=body)
        assert response.status_code == 422, (body, response.text)
    assert client.get("/production/attempts/not-a-uuid").status_code == 422
