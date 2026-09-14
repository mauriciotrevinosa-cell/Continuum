"""Manga source access: held media as content-addressed, read-only reference units.

Under test (Phase 1 plan M1a, expansion section 17):

* an archive page is named by the archive's content hash plus the **entry
  name**, chosen at its reading-order position; an image by its own hash; a
  PDF by hash and page; a video instant by hash and time;
* the engine's recorded SHA-256 is reused only while size and mtime still
  match, and an unrecorded file hashes to the same value;
* a unit's bytes are read back exactly, and refused once the file changed;
* hostile entries, unknown ids and unsupported media are not addressable;
* nothing in the Vault changes.

No database. All content is invented (D-18 / A-05).
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest
from continuum_core import SourceLocator, parse_locator
from continuum_core.locators import LocatorMedium
from continuum_core.references import AssetMedium
from continuum_storage import SourceChangedError, SourceUnavailableError

from tests.phase1_world import (
    ART,
    EPISODE,
    GUIDE,
    HOSTILE,
    MANGA,
    MANGA_ENTRIES,
    World,
    build_world,
    snapshot,
)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return build_world(tmp_path)


class TestSelectingUnits:
    def test_archive_page_is_named_by_entry_in_reading_order(self, world: World) -> None:
        sources = world.sources()
        for index, entry in enumerate(MANGA_ENTRIES):
            unit = sources.select(world.id_of(MANGA), page_index=index)
            assert unit.medium is AssetMedium.ARCHIVE
            assert unit.unit_index == index
            assert unit.content_hash == world.sha256_of(MANGA)
            assert unit.locator == SourceLocator.archive_entry(world.sha256_of(MANGA), entry)
            assert parse_locator(unit.locator.render()) == unit.locator

    def test_image_pdf_and_video_units(self, world: World) -> None:
        sources = world.sources()
        image = sources.select(world.id_of(ART))
        assert image.medium is AssetMedium.IMAGE
        assert image.locator.render() == f"image:sha256:{world.sha256_of(ART)}"

        page = sources.select(world.id_of(GUIDE), pdf_page=2)
        assert page.medium is AssetMedium.PDF
        assert page.locator.page == 2 and page.unit_index == 1

        instant = sources.video_instant(world.id_of(EPISODE), 83_250)
        assert instant.locator.medium is LocatorMedium.VIDEO
        assert instant.locator.time_ms == 83_250
        assert instant.content_hash == world.sha256_of(EPISODE)

    def test_unrecorded_files_hash_to_the_same_content(self, tmp_path: Path) -> None:
        recorded = build_world(tmp_path / "a")
        unrecorded = build_world(tmp_path / "b", record_engine_hash=False)
        a = recorded.sources().select(recorded.id_of(ART))
        b = unrecorded.sources().select(unrecorded.id_of(ART))
        assert a.content_hash == b.content_hash == recorded.sha256_of(ART)

    def test_a_stale_engine_hash_is_not_trusted(self, world: World) -> None:
        # The file changes after the scan; its recorded size/mtime no longer match.
        path = world.vault / ART
        path.write_bytes(path.read_bytes() + b"\0")
        unit = world.sources().select(world.id_of(ART))
        assert unit.content_hash == world.sha256_of(ART)

    @pytest.mark.parametrize(
        ("relative", "kwargs"),
        [
            (MANGA, {}),  # an archive needs a page
            (MANGA, {"page_index": 3}),  # out of range
            (MANGA, {"page_index": -1}),
            (MANGA, {"pdf_page": 1}),
            (ART, {"page_index": 2}),
            (GUIDE, {}),  # a PDF needs a page
            (GUIDE, {"pdf_page": 0}),
            (EPISODE, {}),  # video is referenced by instant, not selected
        ],
    )
    def test_invalid_unit_choices_are_refused(
        self, world: World, relative: str, kwargs: dict[str, int]
    ) -> None:
        with pytest.raises(SourceUnavailableError):
            world.sources().select(world.id_of(relative), **kwargs)

    def test_hostile_and_unknown_media_are_not_addressable(self, world: World) -> None:
        sources = world.sources()
        with pytest.raises(SourceUnavailableError):
            sources.select(world.id_of(HOSTILE), page_index=0)
        with pytest.raises(SourceUnavailableError):
            sources.select("m1_" + "0" * 32, page_index=0)
        with pytest.raises(SourceUnavailableError):
            sources.select("../" + MANGA, page_index=0)
        with pytest.raises(SourceUnavailableError):
            sources.video_instant(world.id_of(ART), 10)
        with pytest.raises(SourceUnavailableError):
            sources.video_instant(world.id_of(EPISODE), -1)


class TestReadingUnits:
    def test_page_bytes_roundtrip_exactly(self, world: World) -> None:
        sources = world.sources()
        for index, entry in enumerate(MANGA_ENTRIES):
            unit = sources.select(world.id_of(MANGA), page_index=index)
            data = sources.read_unit(
                unit.relative,
                byte_size=unit.byte_size,
                mtime_ns=unit.mtime_ns,
                locator=unit.locator,
            )
            assert data.data == world.page_bytes[entry]
            assert data.mime == "image/png"

    def test_image_bytes_roundtrip_exactly(self, world: World) -> None:
        sources = world.sources()
        unit = sources.select(world.id_of(ART))
        data = sources.read_unit(
            unit.relative, byte_size=unit.byte_size, mtime_ns=unit.mtime_ns, locator=unit.locator
        )
        assert data.data == world.art_bytes

    def test_a_changed_source_is_refused(self, world: World) -> None:
        sources = world.sources()
        unit = sources.select(world.id_of(MANGA), page_index=0)
        # Someone replaces the archive's content (the harness writes; Continuum never does).
        with zipfile.ZipFile(world.vault / MANGA, "a") as archive:
            archive.writestr("Ch0003/004.png", b"x")
        with pytest.raises(SourceChangedError):
            sources.read_unit(
                unit.relative,
                byte_size=unit.byte_size,
                mtime_ns=unit.mtime_ns,
                locator=unit.locator,
            )

    def test_a_touched_but_identical_file_is_still_readable(self, world: World) -> None:
        sources = world.sources()
        unit = sources.select(world.id_of(ART))
        os.utime(world.vault / ART, ns=(unit.mtime_ns + 5_000_000_000,) * 2)
        data = sources.read_unit(
            unit.relative, byte_size=unit.byte_size, mtime_ns=unit.mtime_ns, locator=unit.locator
        )
        assert data.data == world.art_bytes

    def test_pdf_pages_have_no_image_bytes_yet(self, world: World) -> None:
        sources = world.sources()
        unit = sources.select(world.id_of(GUIDE), pdf_page=1)
        with pytest.raises(SourceUnavailableError):
            sources.read_unit(
                unit.relative,
                byte_size=unit.byte_size,
                mtime_ns=unit.mtime_ns,
                locator=unit.locator,
            )

    def test_navigation_back_to_the_page(self, world: World) -> None:
        sources = world.sources()
        unit = sources.select(world.id_of(MANGA), page_index=2)
        assert sources.media_id_for(unit.relative) == world.id_of(MANGA)
        assert sources.page_index_of(unit.media_id, unit.relative, str(unit.locator.entry)) == 2
        assert sources.page_index_of(unit.media_id, unit.relative, "Ch9999/404.png") is None
        assert sources.media_id_for("../outside/secret.txt") is None


def test_nothing_in_the_vault_changes(world: World) -> None:
    before = snapshot(world.vault)
    sources = world.sources()
    for index in range(len(MANGA_ENTRIES)):
        unit = sources.select(world.id_of(MANGA), page_index=index)
        sources.read_unit(
            unit.relative, byte_size=unit.byte_size, mtime_ns=unit.mtime_ns, locator=unit.locator
        )
        sources.page_index_of(unit.media_id, unit.relative, str(unit.locator.entry))
    sources.select(world.id_of(ART))
    sources.select(world.id_of(GUIDE), pdf_page=1)
    sources.video_instant(world.id_of(EPISODE), 1000)
    assert snapshot(world.vault) == before
