"""Held ZIP/CBZ archives are classified by what they hold - never "ZIP == manga".

Under test (Phase 1 audit correction; the real Vault holds image-only manga
archives, video-only anime archives and a software archive):

* image-only archive -> ``pages``: readable, pages referenceable;
* video-only archive -> ``bundle``: its videos listed, nothing passed off as pages;
* mixed archive (images and videos) -> ``mixed``: images do not win over
  video; the images are readable and referenceable, the videos listed;
* software archive -> ``none`` whatever else it holds; other non-media -> ``none``;
* classification, listing and page reads never modify the archive.

All content is invented (D-18 / A-05).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import pytest
from continuum_api import create_app
from continuum_config import Settings
from continuum_core.references import AssetMedium
from continuum_storage import (
    AcquisitionStore,
    MediaLibrary,
    SourceAccess,
    SourceUnavailableError,
    media_id_for,
)
from continuum_storage.media import IMAGE_TYPES, is_video_entry
from fastapi.testclient import TestClient

from tests.phase1_world import mp4_bytes, picture, snapshot

ARCHIVES: dict[str, dict[str, bytes]] = {
    "Demo Orbit/manga/volume-01.cbz": {
        "Ch0001/001.png": picture(1),
        "Ch0001/002.png": picture(2),
        "ComicInfo.xml": b"<ComicInfo/>",
    },
    "Demo Orbit/anime/season-1.zip": {
        "S1/Demo Orbit - S01E01.mp4": mp4_bytes(1),
        "S1/Demo Orbit - S01E02.mkv": b"\x1a\x45\xdf\xa3" + b"\x00" * 64,
    },
    "Demo Orbit/extras/bonus-disc.zip": {
        "Booklet/01.png": picture(3),
        "Booklet/02.png": picture(4),
        "Booklet/03.png": picture(5),
        "Video/Making-of.mp4": mp4_bytes(2),
    },
    "Demo Orbit/tools/reader-win64.zip": {
        "app/reader.exe": b"MZ\x90\x00",
        "app/icon.png": picture(6),
        "app/intro.mp4": mp4_bytes(3),
    },
    "Demo Orbit/extras/subtitles.zip": {"S1E01.ass": b"[Script Info]", "notes.txt": b"hello"},
}
EXPECTED = {
    "Demo Orbit/manga/volume-01.cbz": "pages",
    "Demo Orbit/anime/season-1.zip": "bundle",
    "Demo Orbit/extras/bonus-disc.zip": "mixed",
    "Demo Orbit/tools/reader-win64.zip": "none",
    "Demo Orbit/extras/subtitles.zip": "none",
}


def _engine_record(path: Path) -> dict[str, Any]:
    """What the acquisition scan records: counts taken from the central directory."""
    with zipfile.ZipFile(path) as archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
    names = [(i.filename, i.file_size) for i in infos]
    videos = [{"name": n, "size": s} for n, s in names if is_video_entry(n, s)]
    info = path.stat()
    return {
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "kind": "archive",
        "ext": path.suffix,
        "archive": {
            "images": sum(1 for n, _ in names if os.path.splitext(n)[1].lower() in IMAGE_TYPES),
            "videos": len(videos),
            "video_entries": videos,
            "executables": sum(1 for n, _ in names if n.lower().endswith(".exe")),
        },
    }


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Path]:
    vault = tmp_path / "vault"
    data = tmp_path / "acquisition"
    data.mkdir()
    files = {}
    for rel, entries in ARCHIVES.items():
        path = vault / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            for name, body in entries.items():
                archive.writestr(name, body)
        files[rel] = _engine_record(path)
    now = dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds")
    (data / "vault-index.json").write_text(
        json.dumps({"vault_root": str(vault), "generated_at": now, "files": files}),
        encoding="utf-8",
    )
    return {"vault": vault, "data": data, "home": tmp_path / "home"}


def _media(world: dict[str, Path]) -> MediaLibrary:
    return MediaLibrary(AcquisitionStore(str(world["data"])), str(world["vault"]))


@pytest.mark.parametrize(("relative", "view"), EXPECTED.items())
def test_each_archive_is_described_by_its_contents(
    world: dict[str, Path], relative: str, view: str
) -> None:
    described = _media(world).describe(media_id_for(relative))
    assert described.view == view


def test_mixed_archives_are_not_passed_off_as_manga(world: dict[str, Path]) -> None:
    media = _media(world)
    mixed = media.describe(media_id_for("Demo Orbit/extras/bonus-disc.zip"))
    assert (mixed.archive_images, mixed.archive_videos) == (3, 1)
    listing = media.archive_listing(mixed.id)
    assert [p.label for p in listing.pages] == ["01.png", "02.png", "03.png"]
    assert [v["name"] for v in mixed.archive_video_entries] == ["Making-of.mp4"]
    data, mime = media.archive_page(mixed.id, 1)
    assert data == picture(4) and mime == "image/png"

    bundle = media.archive_listing(media_id_for("Demo Orbit/anime/season-1.zip"))
    assert bundle.pages == ()
    software = media_id_for("Demo Orbit/tools/reader-win64.zip")
    assert media.describe(software).kind == "software"


def test_pages_of_image_and_mixed_archives_are_referenceable_only(world: dict[str, Path]) -> None:
    sources = SourceAccess(_media(world), str(world["vault"]))
    page = sources.select(media_id_for("Demo Orbit/extras/bonus-disc.zip"), page_index=2)
    assert page.medium is AssetMedium.ARCHIVE
    assert page.locator.entry == "Booklet/03.png"
    assert (
        sources.select(media_id_for("Demo Orbit/manga/volume-01.cbz"), page_index=0).unit_index == 0
    )
    for relative in (
        "Demo Orbit/anime/season-1.zip",
        "Demo Orbit/tools/reader-win64.zip",
        "Demo Orbit/extras/subtitles.zip",
    ):
        with pytest.raises(SourceUnavailableError):
            sources.select(media_id_for(relative), page_index=0)


def test_the_api_reports_the_same_views_and_leaves_archives_untouched(
    world: dict[str, Path],
) -> None:
    before = snapshot(world["vault"])
    settings = Settings(
        _env_file=None,
        data_home=str(world["home"]),
        source_vault_root=str(world["vault"]),
        acquisition_data_dir=str(world["data"]),
    )
    with TestClient(create_app(settings)) as client:
        for relative, view in EXPECTED.items():
            media_id = media_id_for(relative)
            unit = client.get(f"/library/media/{media_id}").json()["unit"]
            assert unit["view"] == view, relative
            pages = client.get(f"/library/media/{media_id}/pages")
            assert pages.status_code == (200 if view in ("pages", "bundle", "mixed") else 404)
        mixed = media_id_for("Demo Orbit/extras/bonus-disc.zip")
        unit = client.get(f"/library/media/{mixed}").json()["unit"]
        assert (unit["pages"], unit["contained_videos"]) == (3, 1)
        assert client.get(f"/library/media/{mixed}/pages/0").content == picture(3)
    assert snapshot(world["vault"]) == before
