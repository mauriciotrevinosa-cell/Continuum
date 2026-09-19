"""Continue shelf controls preserve the distinction between hiding and forgetting."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from continuum_api import create_app
from continuum_config import Settings
from continuum_db.models import Job
from continuum_db.session import session_scope
from continuum_library.vault_jobs import request_scan
from continuum_storage import media_id_for
from continuum_worker import register_default_handlers
from continuum_worker.main import Worker
from fastapi.testclient import TestClient
from sqlalchemy import delete

from tests.phase1_world import clean_domain_tables, snapshot
from tests.phase15_world import VOLUME, Phase15World, build_phase15_world

pytestmark = pytest.mark.requires_db
VAULT = "source_vault"


@pytest.fixture
def world(tmp_path: Path, db_settings: Settings) -> Phase15World:
    from continuum_db.models import Worker as WorkerRow

    with session_scope(db_settings) as session:
        clean_domain_tables(session)
        session.execute(delete(Job))
        session.execute(delete(WorkerRow))
        session.commit()
    register_default_handlers()
    return build_phase15_world(tmp_path)


@pytest.fixture
def settings(world: Phase15World) -> Settings:
    return world.settings()


@pytest.fixture
def worker(settings: Settings) -> Worker:
    value = Worker(settings)
    value.register()
    return value


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as value:
        yield value


def _scan(settings: Settings, worker: Worker) -> None:
    with session_scope(settings) as session:
        request_scan(session, [VAULT])
        session.commit()
    while worker.run_once():
        pass


def _reading_item(client: TestClient) -> dict[str, object] | None:
    for item in client.get("/catalog/progress/continue").json():
        if item["progress"]["medium"] == "READING":
            return item
    return None


def test_hide_preserves_progress_and_new_activity_unhides(
    world: Phase15World, settings: Settings, worker: Worker, client: TestClient
) -> None:
    _scan(settings, worker)
    before = snapshot(world.vault)
    media_id = media_id_for(VOLUME)
    progress = client.post(
        "/catalog/progress/reading", json={"media_id": media_id, "page_index": 0}
    ).json()
    item = _reading_item(client)
    assert item is not None

    hidden = client.post("/catalog/progress/hide", json={"unit_key": progress["unit_key"]})
    assert hidden.status_code == 200
    assert hidden.json()["progress_preserved"] is True
    assert _reading_item(client) is None
    position = client.get("/catalog/progress/position", params={"media_id": media_id}).json()
    assert position["position"]["page_index"] == 0

    # Reading again is fresh activity, so the shelf preference clears itself.
    client.post("/catalog/progress/reading", json={"media_id": media_id, "page_index": 1})
    assert _reading_item(client) is not None
    assert snapshot(world.vault) == before


def test_havent_read_forgets_series_reading_progress_only(
    world: Phase15World, settings: Settings, worker: Worker, client: TestClient
) -> None:
    _scan(settings, worker)
    before = snapshot(world.vault)
    media_id = media_id_for(VOLUME)
    progress = client.post(
        "/catalog/progress/reading", json={"media_id": media_id, "page_index": 1}
    ).json()
    assert _reading_item(client) is not None

    reset = client.post("/catalog/progress/reset", json={"unit_key": progress["unit_key"]})
    assert reset.status_code == 200
    assert reset.json()["reset"] is True
    assert reset.json()["rows_removed"] >= 1
    assert _reading_item(client) is None
    position = client.get("/catalog/progress/position", params={"media_id": media_id}).json()
    assert position["position"] is None
    assert snapshot(world.vault) == before
