"""Production inputs: reference manifests, chapter packages, music, project standing.

Under test (Phase 1.5 F, G, H, I):

* a reference manifest resolves characters, references, manga pages (archive
  entry locators), anime moments (video locators and ``zip...#entry=...&t=``
  for videos inside archives), project documents, music and a chapter package
  from the real catalog - deterministically, stored once per content hash, with
  rights, training and identification warnings instead of silent assumptions;
* nothing in the manifest service knows a project, a series or an episode;
* chapter packages validate structure and cross-references, version on every
  change, keep identical saves as one version, and track approval; the
  published JSON Schema matches the model and the template is valid and holds
  no story content;
* music references are metadata: links stored, never fetched;
* project documents carry maturity, authority and the partial overrides their
  authors wrote, and the API reports who overrides whom.

PostgreSQL (the isolated test database). All content is invented.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from continuum_api import create_app
from continuum_config import Settings
from continuum_core import parse_locator
from continuum_core.references import ReferenceClass, ReferenceOrigin
from continuum_db.models import Job
from continuum_db.session import session_scope
from continuum_library.vault_jobs import request_scan
from continuum_production import ChapterPackageBody, package_json_schema
from continuum_storage import media_id_for
from continuum_worker import register_default_handlers
from continuum_worker.main import Worker
from fastapi.testclient import TestClient
from sqlalchemy import delete

from tests.conftest import REPO_ROOT
from tests.phase1_world import clean_domain_tables
from tests.phase15_world import SEASON_PART_1, VOLUME, Phase15World, build_phase15_world

pytestmark = pytest.mark.requires_db

PROJECT = "demo-project"


def _write_project(root: Path) -> None:
    project = root / "projects" / PROJECT
    project.mkdir(parents=True, exist_ok=True)
    (project / "rules.md").write_text(
        "# Rules\n\n**Status:** AUTHORITATIVE RULE\n", encoding="utf-8"
    )
    (project / "outline.md").write_text(
        "# Outline\n\n**Status:** APPROVED ROUGH\n", encoding="utf-8"
    )
    (project / "odd.md").write_text("# Odd" + chr(10), encoding="utf-8")
    (project / "outline-fix.md").write_text(
        "# Fix\n\n**Status:** AUTHORITATIVE CORRECTION\n", encoding="utf-8"
    )
    (project / "continuum.project.json").write_text(
        json.dumps(
            {
                "schema": "continuum.project/1",
                "id": PROJECT,
                "title": "Demo Project",
                "documents": [
                    {
                        "id": "rules",
                        "path": "rules.md",
                        "lifecycle": "APPROVED",
                        "authority": "RULE",
                    },
                    {
                        "id": "outline",
                        "path": "outline.md",
                        "lifecycle": "APPROVED",
                        "maturity": "ROUGH",
                    },
                    {
                        "id": "outline-fix",
                        "path": "outline-fix.md",
                        "lifecycle": "APPROVED",
                        "maturity": "ROUGH",
                        "authority": "CORRECTION",
                        "overrides": [{"document": "outline", "scope": "the placement only"}],
                    },
                    {
                        "id": "odd",
                        "path": "odd.md",
                        "lifecycle": "APPROVED",
                        "maturity": "FINISHED",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def world(tmp_path: Path, db_settings: Settings) -> Phase15World:
    from continuum_db.models import Worker as WorkerRow

    with session_scope(db_settings) as session:
        clean_domain_tables(session)
        session.execute(delete(Job))
        session.execute(delete(WorkerRow))
        session.commit()
    register_default_handlers()
    built = build_phase15_world(tmp_path)
    _write_project(tmp_path)
    return built


@pytest.fixture
def settings(world: Phase15World) -> Settings:
    return world.settings()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def _scan(settings: Settings) -> None:
    worker = Worker(settings)
    worker.register()
    with session_scope(settings) as s:
        request_scan(s, ["source_vault"])
        s.commit()
    for _ in range(40):
        if not worker.run_once():
            break


def _units(client: TestClient) -> dict[str, dict]:
    detail = client.get("/catalog/series/demo-orbit").json()
    chapter = next(u for u in detail["reading"] if u["label"] == "Chapter 2")
    seasons = {g["label"]: g["units"] for g in detail["watching"]}
    member_episode = seasons["Season 2"][0]
    file_episode = seasons["Season 1"][0]
    return {"chapter": chapter, "member": member_episode, "file": file_episode}


def _reference(client: TestClient, world: Phase15World) -> str:
    created = client.post(
        "/library/references/from-source",
        json={
            "media_id": media_id_for(VOLUME),
            "page_index": 0,
            "spec": {
                "reference_class": ReferenceClass.CANON.value,
                "origin": ReferenceOrigin.SOURCE.value,
            },
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


# ---------------------------------------------------------------------------
def test_a_manifest_resolves_real_vault_inputs_deterministically(
    world: Phase15World, settings: Settings, client: TestClient
) -> None:
    _scan(settings)
    units = _units(client)
    reference_id = _reference(client, world)
    character = client.post("/library/characters", json={"display_name": "Aster Vale"}).json()
    music = client.post(
        f"/projects/{PROJECT}/music",
        json={
            "track": "Invented Theme",
            "artist": "Nobody",
            "reference": "https://example.invalid/t",
            "mood": "calm",
        },
    ).json()
    request = {
        "label": "rough chapter inputs",
        "purpose": "rough manga test",
        "character_ids": [character["id"]],
        "reference_ids": [reference_id],
        "source_pages": [{"unit_id": units["chapter"]["id"], "page": 2}],
        "source_moments": [
            {"unit_id": units["member"]["id"], "time_ms": 461_250},
            {"unit_id": units["file"]["id"], "time_ms": 5_000},
        ],
        "document_ids": ["outline", "outline-fix"],
        "music_ids": [music["id"]],
        "generation_settings": {"workflow": "sketch.v1", "seed": 7},
    }
    first = client.post(f"/projects/{PROJECT}/reference-manifests", json=request)
    assert first.status_code == 201, first.text
    manifest = first.json()["manifest"]
    pages = [s for s in manifest["sources"] if s["kind"] == "manga_page"]
    assert len(pages) == 1
    page_locator = parse_locator(pages[0]["locator"])
    assert page_locator.entry == "Ch0002/002.png"
    assert pages[0]["archive_sha256"] == world.sha256(VOLUME)
    assert pages[0]["label"] == "Chapter 2" and pages[0]["series_key"] == "demo-orbit"
    moments = {s["member"] or "file": s for s in manifest["sources"] if s["kind"] == "anime_moment"}
    archived = next(v for k, v in moments.items() if k != "file")
    archived_locator = parse_locator(archived["locator"])
    assert archived_locator.time_ms == 461_250 and archived_locator.entry.endswith("S02E01.mkv")
    assert archived_locator.sha256 == world.sha256(SEASON_PART_1)
    assert parse_locator(moments["file"]["locator"]).time_ms == 5_000
    assert {d["id"]: d["authority"] for d in manifest["documents"]} == {
        "outline": "CONTENT",
        "outline-fix": "CORRECTION",
    }
    assert manifest["music"][0]["track"] == "Invented Theme"
    assert any("rights status unknown" in w for w in manifest["warnings"])
    assert any("not approved for model training" in w for w in manifest["warnings"])

    # The same request resolves to the same manifest, stored once.
    again = client.post(f"/projects/{PROJECT}/reference-manifests", json=request).json()
    assert (
        again["id"] == first.json()["id"]
        and again["manifest_hash"] == first.json()["manifest_hash"]
    )
    listed = client.get(f"/projects/{PROJECT}/reference-manifests").json()
    assert len(listed) == 1 and listed[0]["counts"]["sources"] == 3
    fetched = client.get(f"/production/reference-manifests/{again['id']}").json()
    assert fetched["manifest"] == manifest

    # Unknown units, pages out of range and unknown projects are refused.
    bad_page = dict(request, source_pages=[{"unit_id": units["chapter"]["id"], "page": 99}])
    assert client.post(f"/projects/{PROJECT}/reference-manifests", json=bad_page).status_code == 422
    assert client.post("/projects/no-such-project/reference-manifests", json={}).status_code == 404


def test_the_manifest_service_knows_no_project_or_series() -> None:
    source = (REPO_ROOT / "packages/production/src/continuum_production/manifest.py").read_text(
        "utf-8"
    )
    manifest_doc = json.loads(
        (REPO_ROOT / "docs/creative/continuum.project.json").read_text("utf-8")
    )
    assert manifest_doc["id"] not in source
    assert manifest_doc["title"] not in source
    assert "S1E1" not in source


def test_chapter_packages_validate_version_and_track_approval(
    world: Phase15World, settings: Settings, client: TestClient
) -> None:
    template = json.loads(
        (REPO_ROOT / "docs/templates/chapter-package.template.json").read_text("utf-8")
    )
    parsed = ChapterPackageBody.model_validate(template)
    assert parsed.approval_state.value == "DRAFT"
    body = dict(template, project=PROJECT)
    checked = client.post(
        f"/projects/{PROJECT}/chapter-packages/validate", json={"body": body}
    ).json()
    assert checked == {"valid": True, "problems": []}

    broken = json.loads(json.dumps(body))
    broken["pages"][0]["panels"][0]["characters_present"] = ["Nobody Listed"]
    broken["pages"][0]["scene_id"] = "scene-99"
    result = client.post(
        f"/projects/{PROJECT}/chapter-packages/validate", json={"body": broken}
    ).json()
    assert result["valid"] is False
    assert "not in characters" in json.dumps(result) and "does not exist" in json.dumps(result)
    other_project = dict(body, project="another-project")
    assert (
        client.post(
            f"/projects/{PROJECT}/chapter-packages/validate", json={"body": other_project}
        ).json()["valid"]
        is False
    )

    v1 = client.post(f"/projects/{PROJECT}/chapter-packages/ch-01", json={"body": body})
    assert v1.status_code == 201 and v1.json()["version"] == 1
    same = client.post(f"/projects/{PROJECT}/chapter-packages/ch-01", json={"body": body}).json()
    assert same["version"] == 1
    changed = json.loads(json.dumps(body))
    changed["title"] = "Another working title"
    v2 = client.post(f"/projects/{PROJECT}/chapter-packages/ch-01", json={"body": changed}).json()
    assert v2["version"] == 2 and v2["body_hash"] != v1.json()["body_hash"]
    versions = client.get(f"/projects/{PROJECT}/chapter-packages/ch-01").json()
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[1]["body"]["title"] == body["title"]  # never overwritten
    approved = client.post(
        f"/projects/{PROJECT}/chapter-packages/ch-01/approval",
        json={"version": 2, "approval_state": "APPROVED", "row_version": v2["row_version"]},
    )
    assert approved.status_code == 200 and approved.json()["approval_state"] == "APPROVED"
    stale = client.post(
        f"/projects/{PROJECT}/chapter-packages/ch-01/approval",
        json={"version": 2, "approval_state": "SUPERSEDED", "row_version": v2["row_version"]},
    )
    assert stale.status_code == 409
    assert [
        p["package_key"] for p in client.get(f"/projects/{PROJECT}/chapter-packages").json()
    ] == ["ch-01"]


def test_the_published_schema_matches_the_model_and_the_template_is_placeholder_only() -> None:
    published = json.loads(
        (REPO_ROOT / "docs/schemas/chapter-package.v1.schema.json").read_text("utf-8")
    )
    assert published == json.loads(json.dumps(package_json_schema())), (
        "docs/schemas is stale: run `uv run python scripts/export_schemas.py`"
    )
    template_text = (REPO_ROOT / "docs/templates/chapter-package.template.json").read_text("utf-8")
    template = json.loads(template_text)
    assert template["project"] == "your-project-id"
    assert {c["name"] for c in template["characters"]} == {"Character A", "Character B"}
    manifest = json.loads((REPO_ROOT / "docs/creative/continuum.project.json").read_text("utf-8"))
    assert manifest["title"] not in template_text


def test_music_references_are_metadata_only(settings: Settings, client: TestClient) -> None:
    created = client.post(
        f"/projects/{PROJECT}/music",
        json={
            "track": "Invented Theme",
            "episode": "E01",
            "scene": "opening",
            "intended_use": "temp track",
        },
    )
    assert created.status_code == 201
    row = created.json()
    updated = client.post(
        f"/projects/{PROJECT}/music/{row['id']}/update",
        json={"row_version": row["row_version"], "mood": "hopeful"},
    ).json()
    assert updated["mood"] == "hopeful"
    assert (
        client.post(
            f"/projects/{PROJECT}/music", json={"track": "x", "reference": "javascript:alert(1)"}
        ).json()["reference"]
        == "javascript:alert(1)"
    )  # kept as text, never a link and never fetched
    assert (
        client.post(
            f"/projects/{PROJECT}/music/{row['id']}/remove",
            json={"row_version": updated["row_version"]},
        ).status_code
        == 204
    )
    assert [m["track"] for m in client.get(f"/projects/{PROJECT}/music").json()] == ["x"]
    assert client.post("/projects/unknown-project/music", json={"track": "t"}).status_code == 404


def test_documents_carry_maturity_authority_and_stated_overrides(client: TestClient) -> None:
    detail = client.get(f"/projects/{PROJECT}").json()
    documents = {d["id"]: d for d in detail["documents"]}
    assert documents["rules"]["authority"] == "RULE"
    assert documents["outline"]["maturity"] == "ROUGH"
    assert documents["outline-fix"]["overrides"] == [
        {"document": "outline", "scope": "the placement only"}
    ]
    assert documents["outline"]["overridden_by"] == [
        {"document": "outline-fix", "scope": "the placement only"}
    ]
    # An unknown maturity is not guessed at.
    assert detail["project"]["warnings"]
