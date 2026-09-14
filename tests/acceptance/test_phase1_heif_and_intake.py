"""HEIC/HEIF intake, content sniffing, duplicates and download-name provenance.

Under test (Phase 1 audit correction, local-media reality):

* bytes are classified by signature, never by name: a JPEG named ``.heic`` is
  a JPEG, an ``ftyp`` box may be MP4 video or a HEIC still, installers and
  documents are refused before anything is written;
* a real HEIC decodes through the HEIF decoder; the original bytes are kept
  exactly as received and a deterministic PNG rendition is what the vault
  works with, with the original's hash, format and decoder recorded;
* corrupt, truncated, oversized and unsupported HEIF-family inputs are
  refused, and a missing decoder is a clear refusal - never a silent drop;
* exact duplicate bytes create no second candidate and name what already
  holds them, whatever the file is called;
* ``<handle>_<unix time>_<post id>_<owner id>.<ext>`` names yield the creator
  handle and posting time, labelled as coming from the file name.

The HEIC fixture is synthetic (``fixtures/images/README.md``). All content is invented.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterator
from pathlib import Path

import continuum_imaging
import pytest
from continuum_config import Settings
from continuum_core.references import IntakeKind, ReferenceClass, ReferenceOrigin
from continuum_db.session import session_scope
from continuum_imaging import (
    HeifDecoderUnavailableError,
    UnsupportedImageError,
    open_image,
    preview,
    probe,
    sniff,
    working_rendition,
)
from continuum_library import (
    AcceptSpec,
    CatalogInputError,
    ReferenceCatalog,
    ReferenceInbox,
    ReferenceSpec,
    download_name_facts,
)
from PIL import Image
from sqlalchemy.orm import Session

from tests.conftest import REPO_ROOT
from tests.phase1_world import World, build_world, clean_domain_tables, mp4_bytes, picture

HEIC = (REPO_ROOT / "fixtures" / "images" / "synthetic-gradient.heic").read_bytes()
HEIC_SHA256 = "383893524908673794162468cb41fbc46401c545dc81dd582aa1896513ac68d3"
NAME = "some.artist_1780592554_3912216330897723290_59369363259.heic"


def _ftyp(major: bytes, *compatible: bytes) -> bytes:
    body = major + b"\x00\x00\x00\x00" + b"".join(compatible)
    return (8 + len(body)).to_bytes(4, "big") + b"ftyp" + body + b"\x00" * 64


def _oversized_heic() -> bytes:
    """The fixture with its declared ``ispe`` dimensions raised to 60000 x 60000."""
    at = HEIC.find(b"ispe")
    assert at > 0
    patched = bytearray(HEIC)
    patched[at + 8 : at + 16] = (60000).to_bytes(4, "big") * 2
    return bytes(patched)


def _library_files(world: World) -> set[str]:
    return {p.name for p in (world.data_home / "library").rglob("*") if p.is_file()}


# ---------------------------------------------------------------------------
# Imaging: sniffing and HEIF decoding (no database)
# ---------------------------------------------------------------------------
class TestSniffing:
    @pytest.mark.parametrize(
        ("data", "kind", "fmt"),
        [
            (picture(1), "image", "PNG"),
            (picture(1, fmt="JPEG"), "image", "JPEG"),
            (picture(1, fmt="WEBP"), "image", "WEBP"),
            (picture(1, fmt="GIF"), "image", "GIF"),
            (HEIC, "image", "HEIF"),
            (_ftyp(b"mif1", b"mif1", b"heic"), "image", "HEIF"),
            (_ftyp(b"avif", b"mif1", b"avif"), "image", "AVIF"),
            (_ftyp(b"isom", b"isom", b"avc1", b"mp41"), "video", "MP4"),
            (_ftyp(b"qt  "), "video", "QUICKTIME"),
            (mp4_bytes(1), "video", "MP4"),
            (b"\x1a\x45\xdf\xa3" + b"\x00" * 60, "video", "MATROSKA"),
            (b"MZ\x90\x00\x03" + b"\x00" * 200, "other", "EXECUTABLE"),
            (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64, "other", "OLE"),
            (b"PK\x03\x04" + b"\x00" * 64, "other", "ZIP"),
            (b"%PDF-1.7\n", "other", "PDF"),
            (b"", "other", "EMPTY"),
            (b"just some text", "other", "UNKNOWN"),
        ],
    )
    def test_bytes_decide_what_a_file_is(self, data: bytes, kind: str, fmt: str) -> None:
        sniffed = sniff(data)
        assert (sniffed.kind, sniffed.format) == (kind, fmt)


class TestHeif:
    def test_heic_decodes_and_renders_deterministically(self) -> None:
        assert continuum_imaging.HEIF_DECODER, "the HEIF decoder must be installed for this suite"
        assert hashlib.sha256(HEIC).hexdigest() == HEIC_SHA256
        info = probe(HEIC)
        assert (info.format, info.width, info.height) == ("HEIF", 96, 64)
        image = open_image(HEIC)
        assert image.mode == "RGB" and image.size == (96, 64)
        first, second = working_rendition(HEIC), working_rendition(HEIC)
        assert first is not None and second is not None
        assert first.image.data == second.image.data
        assert first.image.mime == "image/png" and first.original_format == "HEIF"
        assert "libheif" in first.converter
        # The rendition is a faithful decode: the left edge is blue-ish, the right red-ish.
        png = Image.open(io.BytesIO(first.image.data)).convert("RGB")
        assert png.getpixel((2, 5))[2] > png.getpixel((2, 5))[0]
        assert png.getpixel((93, 5))[0] > png.getpixel((93, 5))[2]
        assert HEIC == (REPO_ROOT / "fixtures/images/synthetic-gradient.heic").read_bytes()

    def test_formats_used_directly_have_no_rendition(self) -> None:
        assert working_rendition(picture(2)) is None
        assert working_rendition(picture(2, fmt="JPEG")) is None

    @pytest.mark.parametrize(
        "data",
        [
            HEIC[:40] + b"\x00" * 400,  # a HEIC header with no image in it
            HEIC[: len(HEIC) // 2],  # truncated
            _oversized_heic(),  # declares 3.6 billion pixels
            _ftyp(b"avif", b"mif1", b"avif"),  # AVIF is not an allowed format
        ],
        ids=["corrupt", "truncated", "oversized", "avif"],
    )
    def test_hostile_heif_family_inputs_are_refused(self, data: bytes) -> None:
        with pytest.raises(UnsupportedImageError):
            open_image(data)
        with pytest.raises(UnsupportedImageError):
            working_rendition(data)

    def test_without_the_decoder_heic_is_refused_with_remediation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(continuum_imaging, "HEIF_DECODER", None)
        with pytest.raises(HeifDecoderUnavailableError) as refused:
            probe(HEIC)
        assert refused.value.remediation and "pi-heif" in refused.value.remediation
        assert probe(picture(3)).format == "PNG"


def test_download_names_carry_handle_and_time() -> None:
    facts = download_name_facts(NAME)
    assert facts == {
        "creator_handle": "@some.artist",
        "posted_at": "2026-06-04T17:02:34+00:00",
        "source_post_id": "3912216330897723290",
    }
    assert (
        download_name_facts("ink_fox__1786046800_3957969574809257297_70622007632 (1).jpg")[
            "creator_handle"
        ]
        == "@ink_fox_"
    )
    for name in (
        "IMG_0042.heic",
        "reel.mp4",
        "a_123_456_789.jpg",
        "x_0000000001_1234567890123456_1.jpg",
    ):
        assert download_name_facts(name) == {}


# ---------------------------------------------------------------------------
# Inbox: conversion, duplicates, refusals, provenance (PostgreSQL)
# ---------------------------------------------------------------------------
@pytest.fixture
def world(tmp_path: Path) -> World:
    return build_world(tmp_path)


@pytest.fixture
def session(db_settings: Settings) -> Iterator[Session]:
    with session_scope(db_settings) as s:
        clean_domain_tables(s)
        yield s


@pytest.fixture
def catalog(session: Session, world: World) -> ReferenceCatalog:
    return ReferenceCatalog(session, sources=world.sources(), derived=world.derived())


@pytest.fixture
def inbox(catalog: ReferenceCatalog) -> ReferenceInbox:
    return ReferenceInbox(catalog)


class TestHeicIntake:
    def test_heic_is_kept_as_original_and_worked_as_png(
        self, inbox: ReferenceInbox, catalog: ReferenceCatalog, world: World
    ) -> None:
        result = inbox.add_file(HEIC, IntakeKind.IMAGE, display_name=NAME)
        candidate = result.candidate
        assert candidate is not None and not result.duplicate
        capture = candidate.capture
        assert capture["detected_format"] == "HEIF"
        assert capture["original_sha256"] == HEIC_SHA256
        assert capture["original_format"] == "HEIF" and capture["original_bytes"] == len(HEIC)
        assert "libheif" in capture["converted_with"]

        derived = world.derived()
        # The original is stored exactly as received; the working copy is the PNG.
        assert derived.get_bytes("library", HEIC_SHA256) == HEIC
        working, _medium = inbox.candidate_bytes(candidate)
        assert probe(working).format == "PNG"
        assert hashlib.sha256(working).hexdigest() == capture["rendition_sha256"]
        assert preview(working).mime == "image/webp"

        item = inbox.accept(candidate.id, candidate.row_version, AcceptSpec(ReferenceClass.MOOD))
        assert item.provenance["conversion"]["original_sha256"] == HEIC_SHA256
        assert catalog.unit_bytes(item) == working

    def test_direct_uploads_convert_the_same_way(self, catalog: ReferenceCatalog) -> None:
        item = catalog.add_upload(
            HEIC,
            ReferenceSpec(reference_class=ReferenceClass.CANON, origin=ReferenceOrigin.FAN_ART),
        )
        assert item.provenance["conversion"]["original_sha256"] == HEIC_SHA256
        assert probe(catalog.unit_bytes(item)).format == "PNG"

    def test_a_jpeg_named_heic_is_a_jpeg(self, inbox: ReferenceInbox) -> None:
        candidate = inbox.add_file(
            picture(4, fmt="JPEG"), IntakeKind.IMAGE, display_name=NAME
        ).candidate
        assert candidate is not None
        assert candidate.display_name == NAME
        assert candidate.capture["detected_format"] == "JPEG"
        assert "original_sha256" not in candidate.capture

    def test_without_the_decoder_heic_is_refused_and_nothing_is_written(
        self, inbox: ReferenceInbox, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(continuum_imaging, "HEIF_DECODER", None)
        with pytest.raises(HeifDecoderUnavailableError):
            inbox.add_file(HEIC, IntakeKind.IMAGE, display_name=NAME)
        assert inbox.candidates() == [] and _library_files(world) == set()


class TestContentDecides:
    @pytest.mark.parametrize(
        ("data", "message"),
        [
            (b"MZ\x90\x00\x03\x00\x00\x00\x04" + b"\x00" * 4096, "installer"),
            (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 4096, "installer"),
            (b"PK\x03\x04" + b"\x00" * 4096, "archive"),
            (b"%PDF-1.7\n" + b"\x00" * 64, "PDF"),
        ],
    )
    @pytest.mark.parametrize("kind", [IntakeKind.IMAGE, IntakeKind.VIDEO, IntakeKind.SCREENSHOT])
    def test_non_media_is_refused_before_anything_is_stored(
        self, inbox: ReferenceInbox, world: World, data: bytes, message: str, kind: IntakeKind
    ) -> None:
        with pytest.raises(CatalogInputError, match=message):
            inbox.add_file(data, kind, display_name="Some Installer (1).exe")
        assert inbox.candidates() == [] and _library_files(world) == set()

    def test_a_valid_header_over_broken_pixels_is_refused(
        self, inbox: ReferenceInbox, world: World
    ) -> None:
        jpeg = picture(11, fmt="JPEG")
        with pytest.raises(UnsupportedImageError):
            inbox.add_file(jpeg[: len(jpeg) // 3], IntakeKind.IMAGE, display_name="cut.jpg")
        with pytest.raises(UnsupportedImageError):
            inbox.add_file(HEIC[: len(HEIC) // 2], IntakeKind.IMAGE, display_name="cut.heic")
        assert inbox.candidates() == [] and _library_files(world) == set()

    def test_the_kind_hint_is_corrected_by_content(self, inbox: ReferenceInbox) -> None:
        clip = inbox.add_file(mp4_bytes(5), IntakeKind.IMAGE, display_name="reel.jpg").candidate
        still = inbox.add_file(HEIC, IntakeKind.VIDEO, display_name="photo.mp4").candidate
        assert clip is not None and clip.intake_kind is IntakeKind.VIDEO
        assert still is not None and still.intake_kind is IntakeKind.IMAGE


class TestDuplicates:
    def test_exact_duplicates_name_the_existing_candidate(
        self, inbox: ReferenceInbox, world: World
    ) -> None:
        first = inbox.add_file(
            picture(6, fmt="JPEG"), IntakeKind.IMAGE, display_name=NAME
        ).candidate
        heic = inbox.add_file(HEIC, IntakeKind.IMAGE, display_name="photo.heic").candidate
        assert first is not None and heic is not None
        files = _library_files(world)

        again = inbox.add_file(
            picture(6, fmt="JPEG"),
            IntakeKind.SCREENSHOT,
            display_name=NAME.replace(".heic", " (1).heic"),
        )
        assert again.duplicate and again.candidate is None
        assert again.duplicate_of is not None and again.duplicate_of.id == first.id
        heic_again = inbox.add_file(HEIC, IntakeKind.IMAGE, display_name="copy of photo.heic")
        assert heic_again.duplicate_of is not None and heic_again.duplicate_of.id == heic.id
        # Nothing new stored, nothing removed, one candidate each.
        assert _library_files(world) == files
        assert len(inbox.candidates()) == 2

    def test_bytes_already_in_the_library_are_named(
        self, inbox: ReferenceInbox, catalog: ReferenceCatalog
    ) -> None:
        item = catalog.add_upload(
            picture(7),
            ReferenceSpec(reference_class=ReferenceClass.CANON, origin=ReferenceOrigin.FAN_ART),
        )
        result = inbox.add_file(picture(7), IntakeKind.IMAGE, display_name="saved.png")
        assert result.duplicate and result.duplicate_of is None
        assert result.duplicate_reference_id == item.id

        converted = catalog.add_upload(
            HEIC,
            ReferenceSpec(reference_class=ReferenceClass.CANON, origin=ReferenceOrigin.FAN_ART),
        )
        assert inbox.add_file(HEIC, IntakeKind.IMAGE).duplicate_reference_id == converted.id


class TestNameProvenance:
    def test_handle_and_time_come_from_the_name_and_say_so(self, inbox: ReferenceInbox) -> None:
        derived = inbox.add_file(picture(8), IntakeKind.IMAGE, display_name=NAME).candidate
        assert derived is not None
        assert derived.creator_handle == "@some.artist"
        assert derived.capture["creator_handle_source"] == "filename"
        assert derived.capture["posted_at"] == "2026-06-04T17:02:34+00:00"
        assert derived.capture["source_post_id"] == "3912216330897723290"

        stated = inbox.add_file(
            picture(9), IntakeKind.IMAGE, display_name=NAME, creator_handle="@the_real_artist"
        ).candidate
        assert stated is not None and stated.creator_handle == "@the_real_artist"
        assert stated.capture["creator_handle_source"] == "user"

        plain = inbox.add_file(
            picture(10), IntakeKind.IMAGE, display_name="Instagram/some.artist/IMG_0042.png"
        ).candidate
        assert plain is not None and plain.creator_handle is None
        assert plain.display_name == "IMG_0042.png"
        assert "creator_handle_source" not in plain.capture
