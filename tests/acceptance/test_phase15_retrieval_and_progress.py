"""Retrieval, progress, archived episodes and collection import over the full catalog.

Under test (Phase 1.5 B, C, the anime-archive requirement and the FanArt import):

* series, units and unified search find manga chapters, episodes (including
  videos inside archives) and imported references by series, season, episode,
  chapter, collection and creator - through the API, by ids only;
* reading and watching progress persists, survives a rescan that rebuilds every
  unit, and drives "Continue" (resume, next chapter/episode, finished);
* a video inside a DEFLATE archive is prepared by a durable job into the
  bounded member cache, verified, streamed with byte ranges, and evicted
  least-recently-used first - the archive itself is never modified;
* an intake collection imports as UNSORTED fan art with collection, creator,
  posting date, rights UNKNOWN and training MANUAL_REVIEW; exact duplicates are
  linked, installers rejected, clips become Inbox candidates; a second import
  changes nothing; the intake folder is byte-identical afterwards.

PostgreSQL (the isolated test database). All content is invented.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from continuum_api import create_app
from continuum_config import Settings
from continuum_core.catalog import RightsStatus, TrainingEligibility
from continuum_core.references import IntakeKind, ReferenceClass, ReferenceOrigin
from continuum_db.models import CatalogEntry, CatalogMember, Job, ReferenceCandidate, ReferenceItem
from continuum_db.session import session_scope
from continuum_library.vault_jobs import request_scan
from continuum_storage import media_id_for
from continuum_worker import register_default_handlers
from continuum_worker.main import Worker
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from tests.phase1_world import clean_domain_tables, snapshot
from tests.phase15_world import (
    ALIAS,
    EPISODE_GOOD,
    INTAKE_CLIP,
    INTAKE_DUPLICATE_CLIP,
    INTAKE_INSTALLER,
    SEASON_MEMBERS,
    SEASON_PART_1,
    SERIES,
    VOLUME,
    Phase15World,
    build_phase15_world,
    mkv_bytes,
)

pytestmark = pytest.mark.requires_db

VAULT = "source_vault"
INTAKE = "intake:sketchbook"


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
    w = Worker(settings)
    w.register()
    return w


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as c:
        yield c


def drain(worker: Worker, limit: int = 60) -> None:
    ran = 0
    while ran < limit and worker.run_once():
        ran += 1


def scanned(settings: Settings, worker: Worker, *roots: str) -> None:
    with session_scope(settings) as s:
        request_scan(s, list(roots or (VAULT, INTAKE)))
        s.commit()
    drain(worker)


# ---------------------------------------------------------------------------
def test_series_units_and_search_find_the_real_structure_by_ids(
    settings: Settings, worker: Worker, client: TestClient
) -> None:
    scanned(settings, worker)
    series = client.get("/catalog/series").json()
    assert [s["series_key"] for s in series] == ["demo-orbit"]
    detail = client.get("/catalog/series/demo-orbit").json()
    chapters = [u["label"] for u in detail["reading"] if u["kind"] == "MANGA_CHAPTER"]
    assert chapters[:3] == ["Chapter 1", "Chapter 1.5", "Chapter 2"]
    seasons = {group["label"]: group["units"] for group in detail["watching"]}
    assert [u["episode"] for u in seasons["Season 2"]] == [1, 2, 3]
    member_unit = seasons["Season 2"][0]
    assert member_unit["open"]["kind"] == "member"
    assert member_unit["source"]["member_name"] == f"[Group] {ALIAS} - S02E01.mkv"
    # A unit never carries a Vault path; a person sees names, the client gets ids.
    assert "relative_path" not in str(detail)

    by_episode = client.get(
        "/catalog/units", params={"series": "demo-orbit", "season": 2, "episode": 3}
    ).json()
    assert [u["episode_kind"] for u in by_episode["units"]] == ["RECAP"]
    by_chapter = client.get("/catalog/units", params={"chapter": "1.5"}).json()
    assert [u["label"] for u in by_chapter["units"]] == ["Chapter 1.5"]
    by_alias = client.get("/catalog/units", params={"q": "kido orbit"}).json()
    assert by_alias["total"] >= 3
    by_creator = client.get(
        "/catalog/units", params={"creator": "orbit.sketches", "root": INTAKE}
    ).json()
    assert by_creator["total"] == 2  # exact copies are linked, not listed twice
    unit = client.get(f"/catalog/units/{member_unit['id']}").json()
    assert unit["provenance"]["member"].endswith("S02E01.mkv")
    assert unit["next_id"] is not None

    everything = client.get("/catalog/search", params={"q": "orbit"}).json()
    assert everything["units"]["total"] > 0
    assert client.get("/catalog/search", params={"q": "x" * 81}).status_code == 422
    # Hostile input is data, not a pattern.
    assert client.get("/catalog/units", params={"q": "%_%"}).json()["total"] == 0


def test_progress_persists_survives_rescans_and_drives_continue(
    world: Phase15World, settings: Settings, worker: Worker, client: TestClient
) -> None:
    scanned(settings, worker, VAULT)
    volume = media_id_for(VOLUME)
    # Chapter 1 has pages 0-1; reading its last page completes it.
    assert (
        client.post(
            "/catalog/progress/reading", json={"media_id": volume, "page_index": 0}
        ).status_code
        == 200
    )
    done = client.post(
        "/catalog/progress/reading", json={"media_id": volume, "page_index": 1}
    ).json()
    assert done["completed_at"] is not None and done["page_count"] == 2
    items = client.get("/catalog/progress/continue").json()
    reading = next(i for i in items if i["progress"]["medium"] == "READING")
    assert reading["state"] == "next" and reading["next"]["label"] == "Chapter 1.5"

    episode = media_id_for(EPISODE_GOOD)
    watched = client.post(
        "/catalog/progress/watching",
        json={"media_id": episode, "position_ms": 61_000, "duration_ms": 1_400_000},
    ).json()
    assert watched["completed_at"] is None and watched["position_ms"] == 61_000
    position = client.get("/catalog/progress/position", params={"media_id": episode}).json()
    assert position["position"]["position_ms"] == 61_000

    # A rescan with a new scanner rebuilds every unit; progress stays attached.
    with session_scope(settings) as s:
        s.execute(select(CatalogEntry)).scalars().all()
        from sqlalchemy import update

        s.execute(update(CatalogEntry).values(scanner_version=0))
        s.commit()
    scanned(settings, worker, VAULT)
    # A restarted application reads the same state back.
    with TestClient(create_app(settings)) as again:
        items = again.get("/catalog/progress/continue").json()
    watching = next(i for i in items if i["progress"]["medium"] == "WATCHING")
    assert watching["state"] == "resume"
    assert watching["unit"]["label"] == "S1 · E1"
    assert watching["progress"]["position_ms"] == 61_000
    series = client.get("/catalog/series/demo-orbit").json()["progress"]
    assert series["reading"]["last_completed"]["unit"]["label"] == "Chapter 1"
    assert series["watching"]["last_opened"]["progress"]["position_ms"] == 61_000

    # Refused: a page outside the archive, a video position on a manga archive, a path.
    assert (
        client.post(
            "/catalog/progress/reading", json={"media_id": volume, "page_index": 99}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/catalog/progress/watching", json={"media_id": volume, "position_ms": 1}
        ).status_code
        == 422
    )
    assert (
        client.post("/catalog/progress/reading", json={"path": "C:/x", "page_index": 0}).status_code
        == 422
    )


def test_a_video_inside_a_compressed_archive_is_prepared_streamed_and_evicted(
    world: Phase15World, settings: Settings, worker: Worker, client: TestClient
) -> None:
    scanned(settings, worker, VAULT)
    before = snapshot(world.vault)
    with session_scope(settings) as s:
        part = s.execute(
            select(CatalogEntry).where(CatalogEntry.relative_path == SEASON_PART_1)
        ).scalar_one()
        members = {
            m.name: m.id
            for m in s.execute(
                select(CatalogMember).where(CatalogMember.entry_id == part.id)
            ).scalars()
        }
    first = members[SEASON_MEMBERS[SEASON_PART_1][1]]  # S02E01
    state = client.get(f"/catalog/members/{first}").json()
    assert state["state"] == "not_prepared"
    assert client.get(f"/catalog/members/{first}/content").status_code == 409

    assert client.post(f"/catalog/members/{first}/prepare").json()["state"] == "preparing"
    drain(worker)
    ready = client.get(f"/catalog/members/{first}").json()
    assert ready["state"] == "ready" and ready["content_type"] == "video/x-matroska"
    expected = mkv_bytes(2)
    whole = client.get(f"/catalog/members/{first}/content")
    assert whole.status_code == 200 and whole.content == expected
    ranged = client.get(f"/catalog/members/{first}/content", headers={"Range": "bytes=100-199"})
    assert ranged.status_code == 206 and ranged.content == expected[100:200]
    assert ranged.headers["content-range"] == f"bytes 100-199/{len(expected)}"
    cached = list((world.data_home / "cache" / "archive-members").rglob("*"))
    assert any(p.is_file() for p in cached)

    # Preparing again is a no-op; progress works for archived episodes too.
    assert client.post(f"/catalog/members/{first}/prepare").json()["state"] == "ready"
    watched = client.post(
        "/catalog/progress/watching",
        json={"member_id": str(first), "position_ms": 5000, "ended": True},
    ).json()
    assert watched["completed_at"] is not None

    # A budget smaller than two episodes evicts the least recently used one.
    small = world.settings(member_cache_bytes=len(expected) + 10)
    second = members[SEASON_MEMBERS[SEASON_PART_1][0]]
    tight = Worker(small)
    tight.register()
    with TestClient(create_app(small)) as limited:
        limited.post(f"/catalog/members/{second}/prepare")
        drain(tight)
        assert limited.get(f"/catalog/members/{second}").json()["state"] == "ready"
        assert limited.get(f"/catalog/members/{first}").json()["state"] == "not_prepared"
    assert snapshot(world.vault) == before


def test_a_changed_archive_is_never_served_as_the_catalogued_member(
    world: Phase15World, settings: Settings, worker: Worker, client: TestClient
) -> None:
    scanned(settings, worker, VAULT)
    with session_scope(settings) as s:
        member = (
            s.execute(
                select(CatalogMember)
                .join(CatalogEntry, CatalogEntry.id == CatalogMember.entry_id)
                .where(CatalogEntry.relative_path == SEASON_PART_1)
            )
            .scalars()
            .first()
        )
        assert member is not None
        member_id = member.id
    # The archive is replaced behind the catalog's back (same names, other bytes).
    with zipfile.ZipFile(world.vault / SEASON_PART_1, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in SEASON_MEMBERS[SEASON_PART_1]:
            archive.writestr(name, b"\x1a\x45\xdf\xa3 replaced")
    client.post(f"/catalog/members/{member_id}/prepare")
    drain(worker)
    state = client.get(f"/catalog/members/{member_id}").json()
    assert state["state"] == "unavailable"
    assert client.get(f"/catalog/members/{member_id}/content").status_code == 409


def test_the_collection_imports_as_unsorted_fan_art_with_honest_metadata(
    world: Phase15World, settings: Settings, worker: Worker, client: TestClient
) -> None:
    before = snapshot(world.intake)
    started = client.post(f"/catalog/roots/{INTAKE}/import").json()
    assert started["import"]["job_type"] == "library.intake_import"
    drain(worker)
    report = client.get(f"/catalog/roots/{INTAKE}/import").json()
    totals = report["totals"]
    assert totals["discovered"] == 8
    assert totals["imported_images_as_references"] == 4
    assert totals["imported_clips_as_inbox_candidates"] == 1
    assert totals["exact_duplicates_linked"] == 2
    assert totals["rejected"] == 1 and report["rejected"][0]["file"] == INTAKE_INSTALLER
    assert report["unknown_creator"] == ["untitled-scan.png"]
    assert report["unknown_date"] == ["untitled-scan.png"]
    assert {r["file"] for r in report["duplicates"]} >= {INTAKE_DUPLICATE_CLIP}
    assert report["defaults"]["training_eligibility"] == "MANUAL_REVIEW"

    with session_scope(settings) as s:
        references = list(s.execute(select(ReferenceItem)).scalars())
        candidates = list(s.execute(select(ReferenceCandidate)).scalars())
    assert len(references) == 4 and len(candidates) == 1
    for item in references:
        assert item.reference_class is ReferenceClass.UNSORTED
        assert item.origin is ReferenceOrigin.FAN_ART
        assert item.collection == "Sketchbook"
        assert item.rights_status is RightsStatus.UNKNOWN
        assert item.training_eligibility is TrainingEligibility.MANUAL_REVIEW
        assert item.provenance["source"] == "local_intake"
        assert item.provenance["original_file_name"] in world.bytes_of
    handled = {i.provenance["original_file_name"]: i for i in references}
    painter = handled["moon_painter_1700500000_3100000000000000003_7700.heic"]
    assert painter.creator_handle == "@moon_painter" and painter.source_posted_at is not None
    assert "extension_mismatch" in painter.provenance
    assert handled["untitled-scan.png"].creator_handle is None
    clip = candidates[0]
    assert clip.intake_kind is IntakeKind.VIDEO and clip.display_name == INTAKE_CLIP
    assert clip.training_eligibility is TrainingEligibility.MANUAL_REVIEW

    # Imported references are searchable by collection and creator.
    found = client.get("/catalog/search", params={"q": "moon_painter"}).json()
    assert len(found["references"]) >= 1
    assert client.get("/library/references").status_code == 200

    # A second import settles nothing new.
    client.post(f"/catalog/roots/{INTAKE}/import")
    drain(worker)
    with session_scope(settings) as s:
        assert len(list(s.execute(select(ReferenceItem)).scalars())) == 4
        assert len(list(s.execute(select(ReferenceCandidate)).scalars())) == 1
    assert (
        world.data_home / "generated" / "reports" / "imports" / "sketchbook-latest.md"
    ).is_file()
    assert snapshot(world.intake) == before
    assert SERIES  # the Vault was not imported: collections come only from intake folders
    assert client.post(f"/catalog/roots/{VAULT}/import").status_code == 404
