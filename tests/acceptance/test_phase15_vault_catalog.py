"""The full-Vault catalog: every file accounted for, incrementally, read-only.

Under test (Phase 1.5 A, B, D, E and the anime-archive requirement):

* a scan of the Source Vault and of an intake folder records **every** file -
  catalogued, unsupported (with its reason) or failed - and every entry the walk
  skipped, with no sample limit;
* archives are inspected from their central directory: page groups become
  chapters, video members become episodes with season/episode read from their
  names and folders, and uncertain identifications are flagged, never guessed;
* files the acquisition engine never listed are catalogued and become openable
  in the Library viewer; engine hashes are reused, the rest are hashed once by a
  resumable hash pass and never again while size and mtime hold;
* a rescan of an unchanged Vault reopens nothing; changed, added and removed
  files are handled incrementally; a failed file is retried by the next scan;
* exact duplicates are linked, never deleted;
* the coverage report accounts for every file and names every exclusion;
* the Vault and the intake folder are byte-identical afterwards.

PostgreSQL (the isolated test database). All content is invented.
"""

from __future__ import annotations

import json
import os
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from continuum_config import Settings
from continuum_core.catalog import (
    Confidence,
    DetectedKind,
    EntryStatus,
    EpisodeKind,
    HashSource,
    MaterialClass,
    UnitKind,
)
from continuum_db.models import CatalogEntry, CatalogMember, CatalogScan, CatalogUnit, Job, JobStep
from continuum_db.session import session_scope
from continuum_library.catalog_records import CatalogRecordSupplement
from continuum_library.coverage import build_coverage, render_coverage_markdown
from continuum_library.vault_jobs import request_scan
from continuum_storage import AcquisitionStore, MediaLibrary, catalog_roots, media_id_for
from continuum_worker import register_default_handlers
from continuum_worker.main import Worker
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from tests.phase1_world import clean_domain_tables, snapshot
from tests.phase15_world import (
    ALIAS,
    DAMAGED,
    EMPTY,
    EPISODE_GOOD,
    EPISODE_POOR,
    INTAKE_CLIP,
    INTAKE_INSTALLER,
    LOOSE,
    MIXED,
    MOVIE,
    NOTES,
    RAR,
    SEASON_PART_1,
    SEASON_PART_2,
    SERIES,
    SOFTWARE,
    VOLUME,
    VOLUME_COPY,
    Phase15World,
    build_phase15_world,
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
def session(settings: Settings) -> Iterator[Session]:
    with session_scope(settings) as s:
        yield s


def drain(worker: Worker, limit: int = 50) -> int:
    ran = 0
    while ran < limit and worker.run_once():
        ran += 1
    return ran


def scan(settings: Settings, worker: Worker, *roots: str, hash_after: bool = True) -> None:
    with session_scope(settings) as s:
        request_scan(s, list(roots or (VAULT, INTAKE)), hash_after=hash_after)
        s.commit()
    drain(worker)


def entry(session: Session, relative: str, root: str = VAULT) -> CatalogEntry:
    session.expire_all()
    return session.execute(
        select(CatalogEntry).where(
            CatalogEntry.root_key == root, CatalogEntry.relative_path == relative
        )
    ).scalar_one()


def units_of(session: Session, relative: str, root: str = VAULT) -> list[CatalogUnit]:
    found = entry(session, relative, root)
    return list(
        session.execute(
            select(CatalogUnit)
            .where(CatalogUnit.entry_id == found.id)
            .order_by(CatalogUnit.sort_key)
        ).scalars()
    )


# ---------------------------------------------------------------------------
def test_every_file_is_accounted_for_with_a_state_or_a_skip_reason(
    world: Phase15World, settings: Settings, worker: Worker, session: Session
) -> None:
    before = (snapshot(world.vault), snapshot(world.intake))
    scan(settings, worker)

    files_on_disk = {
        p.relative_to(world.vault).as_posix() for p in world.vault.rglob("*") if p.is_file()
    }
    catalogued = set(
        session.execute(
            select(CatalogEntry.relative_path).where(CatalogEntry.root_key == VAULT)
        ).scalars()
    )
    latest = (
        session.execute(
            select(CatalogScan)
            .where(CatalogScan.root_key == VAULT)
            .order_by(CatalogScan.started_at.desc())
        )
        .scalars()
        .first()
    )
    assert latest is not None and latest.status.value == "COMPLETED"
    skipped = {s["relative"]: s["reason"] for s in latest.survey["skipped_entries"]}
    assert skipped == {"Thumbs.db": "system file written by the OS or a sync client"}
    # No sample limit: every file is either an entry or a recorded skip.
    assert catalogued | set(skipped) == files_on_disk

    states = {
        rel: entry(session, rel).status
        for rel in (
            VOLUME,
            SEASON_PART_1,
            EPISODE_POOR,
            MIXED,
            SOFTWARE,
            NOTES,
            DAMAGED,
            RAR,
            EMPTY,
            LOOSE,
        )
    }
    assert states[VOLUME] is EntryStatus.CATALOGUED
    assert states[SEASON_PART_1] is EntryStatus.CATALOGUED
    assert states[MIXED] is EntryStatus.CATALOGUED
    assert states[LOOSE] is EntryStatus.CATALOGUED
    for unsupported in (SOFTWARE, NOTES, RAR, EMPTY):
        assert states[unsupported] is EntryStatus.UNSUPPORTED, unsupported
        assert entry(session, unsupported).status_reason
    assert "program" in entry(session, SOFTWARE).status_reason
    assert "ZIP and CBZ" in entry(session, RAR).status_reason
    assert states[DAMAGED] is EntryStatus.FAILED
    assert entry(session, DAMAGED).last_error

    intake_states = {
        e.file_name: e.status
        for e in session.execute(
            select(CatalogEntry).where(CatalogEntry.root_key == INTAKE)
        ).scalars()
    }
    assert intake_states[INTAKE_INSTALLER] is EntryStatus.UNSUPPORTED
    assert len(intake_states) == len(list(world.intake.iterdir()))
    assert (snapshot(world.vault), snapshot(world.intake)) == before


def test_archives_become_chapters_and_episodes_with_honest_identification(
    world: Phase15World, settings: Settings, worker: Worker, session: Session
) -> None:
    scan(settings, worker, VAULT)

    volume = entry(session, VOLUME)
    assert volume.archive_view == "pages"
    assert (volume.member_count, volume.image_count, volume.video_count) == (7, 6, 0)
    assert volume.series_key == "demo-orbit" and volume.material_class is MaterialClass.MANGA
    chapters = units_of(session, VOLUME)
    assert [(u.kind, u.label, u.first_page_index, u.page_count) for u in chapters] == [
        (UnitKind.MANGA_CHAPTER, "Chapter 1", 0, 2),
        (UnitKind.MANGA_CHAPTER, "Chapter 1.5", 2, 1),
        (UnitKind.MANGA_CHAPTER, "Chapter 2", 3, 3),
    ]
    # First page indices are the Library reader's own page positions.
    media = MediaLibrary(AcquisitionStore(str(world.acquisition)), str(world.vault))
    listing = media.archive_listing(media_id_for(VOLUME))
    assert [c[1] for c in listing.chapters] == [0, 2, 3]

    part = entry(session, SEASON_PART_1)
    assert part.archive_view == "bundle" and part.material_class is MaterialClass.ANIME
    members = list(
        session.execute(
            select(CatalogMember)
            .where(CatalogMember.entry_id == part.id)
            .order_by(CatalogMember.position)
        ).scalars()
    )
    assert [m.name.rsplit(" - ", 1)[1] for m in members] == ["S02E01.mkv", "S02E02.mkv"]
    assert all(m.compress_type == zipfile.ZIP_DEFLATED and m.crc32 is not None for m in members)
    episodes = units_of(session, SEASON_PART_1) + units_of(session, SEASON_PART_2)
    assert [(u.season, u.episode, u.episode_kind) for u in episodes] == [
        (2, 1, EpisodeKind.REGULAR),
        (2, 2, EpisodeKind.REGULAR),
        (2, 3, EpisodeKind.RECAP),
    ]
    # The file names use another title; the works catalog knows it as the series.
    assert all(u.confidence is Confidence.HIGH for u in episodes)
    assert any(ALIAS in e for e in episodes[0].evidence)

    good = units_of(session, EPISODE_GOOD)[0]
    assert (good.season, good.episode, good.confidence) == (1, 1, Confidence.HIGH)
    poor = units_of(session, EPISODE_POOR)[0]
    assert poor.episode == 7 and poor.season is None
    assert poor.confidence is Confidence.LOW
    assert any("does not match" in f for f in poor.flags)
    movie = units_of(session, MOVIE)[0]
    assert movie.episode_kind is EpisodeKind.MOVIE and movie.episode is None

    mixed = entry(session, MIXED)
    assert mixed.archive_view == "mixed"
    assert {u.kind for u in units_of(session, MIXED)} == {UnitKind.ARCHIVE_PAGES, UnitKind.VIDEO}
    loose = entry(session, LOOSE)
    assert loose.material_class is MaterialClass.UNKNOWN or loose.series_key is None
    assert any("no series folder" in f for f in loose.facts["placement_flags"])


def test_engine_hashes_are_reused_and_the_hash_pass_runs_once(
    world: Phase15World, settings: Settings, worker: Worker, session: Session
) -> None:
    scan(settings, worker, VAULT, hash_after=False)
    assert entry(session, VOLUME).hash_source is HashSource.ENGINE_INDEX
    assert entry(session, SEASON_PART_1).content_hash is None

    scan(settings, worker, VAULT)
    session.expire_all()
    hashed = {
        e.relative_path: e
        for e in session.execute(
            select(CatalogEntry).where(
                CatalogEntry.root_key == VAULT, CatalogEntry.status == EntryStatus.CATALOGUED
            )
        ).scalars()
    }
    assert all(e.content_hash for e in hashed.values())
    assert hashed[SEASON_PART_1].hash_source is HashSource.COMPUTED
    assert hashed[SEASON_PART_1].content_hash == world.sha256(SEASON_PART_1)
    assert hashed[VOLUME].hash_source is HashSource.ENGINE_INDEX
    # The byte-identical copy is linked to its first copy, and kept.
    assert entry(session, VOLUME_COPY).duplicate_of_id == entry(session, VOLUME).id
    assert (world.vault / VOLUME_COPY).is_file()

    # A second hash pass has nothing to do: no unit hashes a file again.
    scan(settings, worker, VAULT)
    session.expire_all()
    last_hash_job = (
        session.execute(
            select(Job)
            .where(Job.job_type == "library.catalog_hash")
            .order_by(Job.created_at.desc())
        )
        .scalars()
        .first()
    )
    assert last_hash_job is not None
    steps = list(
        session.execute(
            select(JobStep.unit_key).where(JobStep.job_id == last_hash_job.id)
        ).scalars()
    )
    assert steps == ["duplicates"]


def test_a_rescan_reopens_nothing_unchanged_and_handles_changes_incrementally(
    world: Phase15World, settings: Settings, worker: Worker, session: Session
) -> None:
    from continuum_library import vault_catalog

    scan(settings, worker, VAULT, hash_after=False)
    first = {
        e.relative_path: (e.id, e.updated_at)
        for e in session.execute(select(CatalogEntry)).scalars()
    }

    # Unchanged Vault: every file is "unchanged"; only the failed one is reopened.
    opened: list[str] = []
    original_probe = vault_catalog.probe_file

    def counting_probe(root, relative):  # type: ignore[no-untyped-def]
        opened.append(relative)
        return original_probe(root, relative)

    vault_catalog.probe_file = counting_probe  # type: ignore[assignment]
    try:
        scan(settings, worker, VAULT, hash_after=False)
    finally:
        vault_catalog.probe_file = original_probe  # type: ignore[assignment]
    assert opened == [DAMAGED]
    session.expire_all()
    latest = (
        session.execute(
            select(CatalogScan)
            .where(CatalogScan.root_key == VAULT)
            .order_by(CatalogScan.started_at.desc())
        )
        .scalars()
        .first()
    )
    assert latest is not None
    assert (
        latest.counts.get("unchanged") == latest.survey["files"] - 1
    )  # the damaged file is retried
    assert latest.counts.get("failed") == 1 and "new" not in latest.counts
    second = {
        e.relative_path: (e.id, e.updated_at)
        for e in session.execute(select(CatalogEntry)).scalars()
    }
    assert {k: v for k, v in second.items() if k != DAMAGED} == {
        k: v for k, v in first.items() if k != DAMAGED
    }

    # Change one file, add one, remove one, repair the damaged one.
    progress_key = units_of(session, EPISODE_GOOD)[0].unit_key
    (world.vault / EPISODE_GOOD).write_bytes(b"\x00\x00\x00\x18ftypisom" + b"changed" * 100)
    os.utime(world.vault / EPISODE_GOOD, ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
    added = f"{SERIES}/anime/{SERIES} - S01E02.mp4"
    (world.vault / added).write_bytes(b"\x00\x00\x00\x18ftypisom" + b"new" * 100)
    (world.vault / MOVIE).unlink()
    with zipfile.ZipFile(world.vault / DAMAGED, "w") as archive:
        archive.writestr("Ch0009/001.png", (world.vault / LOOSE).read_bytes())

    scan(settings, worker, VAULT, hash_after=False)
    session.expire_all()
    latest = (
        session.execute(
            select(CatalogScan)
            .where(CatalogScan.root_key == VAULT)
            .order_by(CatalogScan.started_at.desc())
        )
        .scalars()
        .first()
    )
    assert latest is not None
    assert latest.counts.get("new") == 1
    assert latest.counts.get("changed") == 2  # the edited episode and the repaired archive
    assert latest.counts.get("missing") == 1
    assert entry(session, MOVIE).status is EntryStatus.MISSING
    assert entry(session, DAMAGED).status is EntryStatus.CATALOGUED
    assert entry(session, added).status is EntryStatus.CATALOGUED
    # Identity of the changed episode's unit is its location, so it is unchanged.
    assert units_of(session, EPISODE_GOOD)[0].unit_key == progress_key

    # A file that comes back is catalogued again, not duplicated.
    (world.vault / MOVIE).write_bytes(b"\x1a\x45\xdf\xa3" + b"back" * 50)
    scan(settings, worker, VAULT, hash_after=False)
    assert entry(session, MOVIE).status is EntryStatus.CATALOGUED
    assert (
        session.execute(
            select(func.count()).where(CatalogEntry.relative_path == MOVIE)
        ).scalar_one()
        == 1
    )


def test_an_interrupted_scan_resumes_without_repeating_finished_batches(
    world: Phase15World, settings: Settings, worker: Worker, session: Session
) -> None:
    from continuum_jobs import request_pause, resume_job
    from continuum_worker.handlers import catalog as handlers

    many = world.vault / SERIES / "manga" / "many"
    many.mkdir(parents=True)
    for index in range(60):
        (many / f"page-{index:03d}.png").write_bytes(
            (world.vault / LOOSE).read_bytes()[:-1] + bytes([index])
        )

    with session_scope(settings) as s:
        jobs = request_scan(s, [VAULT], hash_after=False)
        job_id = jobs[0].scan.id
        s.commit()

    calls: list[str] = []
    original = handlers.CatalogScanHandler.execute_unit

    def pausing(self, ctx, unit):  # type: ignore[no-untyped-def]
        calls.append(unit.unit_key)
        outcome = original(self, ctx, unit)
        if len(calls) == 2:
            with session_scope(settings) as other:
                request_pause(other, other.get(Job, job_id))
                other.commit()
        return outcome

    handlers.CatalogScanHandler.execute_unit = pausing  # type: ignore[method-assign]
    try:
        drain(worker)
        with session_scope(settings) as s:
            job = s.get(Job, job_id)
            assert job is not None and job.status.value == "PAUSED"
            done_before = s.execute(
                select(func.count()).where(JobStep.job_id == job_id, JobStep.status == "SUCCEEDED")
            ).scalar_one()
            resume_job(s, job)
            s.commit()
        calls.clear()
        drain(worker)
    finally:
        handlers.CatalogScanHandler.execute_unit = original  # type: ignore[method-assign]

    with session_scope(settings) as s:
        job = s.get(Job, job_id)
        assert job is not None and job.status.value == "SUCCEEDED"
        total = s.execute(select(func.count()).where(JobStep.job_id == job_id)).scalar_one()
    assert done_before >= 2
    assert len(calls) == total - done_before
    assert entry(session, f"{SERIES}/manga/many/page-059.png").status is EntryStatus.CATALOGUED


def test_catalogued_files_the_engine_never_listed_open_in_the_library(
    world: Phase15World, settings: Settings, worker: Worker
) -> None:
    scan(settings, worker, VAULT, hash_after=False)
    plain = MediaLibrary(AcquisitionStore(str(world.acquisition)), str(world.vault))
    from continuum_storage import MediaUnavailableError

    with pytest.raises(MediaUnavailableError):
        plain.describe(media_id_for(SEASON_PART_1))

    supplement = CatalogRecordSupplement(lambda: session_scope(settings))
    media = MediaLibrary(
        AcquisitionStore(str(world.acquisition)), str(world.vault), supplement=supplement
    )
    part = media.describe(media_id_for(SEASON_PART_1))
    assert part.view == "bundle" and part.archive_videos == 2
    assert [v["name"] for v in part.archive_video_entries] == [
        f"[Group] {ALIAS} - S02E01.mkv",
        f"[Group] {ALIAS} - S02E02.mkv",
    ]
    assert media.describe(media_id_for(MIXED)).view == "mixed"
    assert media.describe(media_id_for(SOFTWARE)).kind == "software"
    # The engine's own records still win for files it listed.
    assert media.describe(media_id_for(VOLUME)).view == "pages"
    # Nothing escapes: a hostile relative path in the catalog is never opened.
    with session_scope(settings) as s:
        s.add(
            CatalogEntry(
                root_key=VAULT,
                relative_path="Demo Orbit/../../outside.png",
                file_name="outside.png",
                byte_size=1,
                mtime_ns=1,
                detected_kind=DetectedKind.IMAGE,
                status=EntryStatus.CATALOGUED,
                material_class=MaterialClass.REFERENCE,
                scanner_version=1,
            )
        )
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError, match="relative_path_is_relative"):
            s.commit()
        s.rollback()


def test_the_coverage_report_accounts_for_every_file_and_names_every_exclusion(
    world: Phase15World, settings: Settings, worker: Worker, session: Session
) -> None:
    scan(settings, worker)
    from continuum_storage import ProjectLibrary

    report = build_coverage(session, catalog_roots(settings), projects=ProjectLibrary([]))
    totals = report["totals"]
    on_disk = sum(1 for p in world.vault.rglob("*") if p.is_file()) + sum(
        1 for p in world.intake.iterdir() if p.is_file()
    )
    assert totals["files_discovered"] + totals["skipped_by_scan"] == on_disk
    assert totals["unaccounted"] == 0
    assert totals["entries"] == totals["files_discovered"]
    vault = next(r for r in report["roots"] if r["root_key"] == VAULT)
    reasons = {row["relative"]: row["reason"] for row in vault["unsupported"]}
    assert set(reasons) == {SOFTWARE, NOTES, RAR, EMPTY}
    assert all(reasons.values())
    assert [row["relative"] for row in vault["failed"]] == [DAMAGED]
    assert vault["archives"]["by_view"] == {"pages": 2, "bundle": 2, "mixed": 1, "none": 1}
    assert vault["units"]["episodes_by_series"][SERIES] >= 5
    assert vault["duplicates"]["extra_copies"] == 1
    assert any(row["relative"] == EPISODE_POOR for row in vault["units"]["low_confidence"])

    markdown = render_coverage_markdown(report)
    assert "## Totals" in markdown and "Not searchable, and why" in markdown
    written = sorted((world.data_home / "generated" / "reports" / "catalog").glob("coverage-*"))
    assert {p.name for p in written} >= {"coverage-latest.json", "coverage-latest.md"}
    stored = json.loads(
        (world.data_home / "generated" / "reports" / "catalog" / "coverage-latest.json").read_text(
            "utf-8"
        )
    )
    assert stored["schema"] == "continuum.catalog-coverage/1"


def test_the_intake_folder_is_catalogued_as_fan_art_with_name_facts(
    world: Phase15World, settings: Settings, worker: Worker, session: Session
) -> None:
    scan(settings, worker, INTAKE)
    clip = entry(session, INTAKE_CLIP, INTAKE)
    assert clip.material_class is MaterialClass.FAN_ART and clip.collection == "Sketchbook"
    assert clip.facts["creator_handle"] == "@orbit.sketches"
    assert clip.facts["posted_at"].startswith("2023-11-")
    disguised = entry(session, "moon_painter_1700500000_3100000000000000003_7700.heic", INTAKE)
    assert disguised.detected_format == "JPEG"
    assert "bytes are a JPEG image" in disguised.facts["extension_mismatch"]
    duplicate = entry(session, "orbit.sketches_1700000300_3100000000000000002_4200 (1).jpg", INTAKE)
    original = entry(session, "orbit.sketches_1700000000_3100000000000000001_4200.jpg", INTAKE)
    assert duplicate.duplicate_of_id == original.id
