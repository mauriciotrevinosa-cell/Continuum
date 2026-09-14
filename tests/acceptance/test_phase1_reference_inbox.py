"""The Reference Inbox: batch intake of links, images, clips and screenshots.

Under test (Phase 1 expansion: Reference/Inspiration Inbox):

* a paste of links becomes candidates, deduplicated, and **nothing is
  fetched** - a link is accepted only once the user attaches an image;
* bulk images, clips and screenshots land under the writable library root,
  never the Source Vault, and keep what the user knows (creator, link, tags,
  intended use, suggested class, origin);
* a clip is never a reference: a captured frame is, and it remembers the clip
  (or the held episode) and the instant;
* triage - update, bulk update, dismiss, restore, accept, bulk accept - is
  explicit, conflicts on stale versions, and cannot re-triage;
* accepted tags become USER TAGGED descriptors.

PostgreSQL (the isolated test database). All content is invented.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from continuum_config import Settings
from continuum_core.references import (
    CandidateStatus,
    CharacterAspect,
    IntakeKind,
    ReferenceClass,
    ReferenceOrigin,
    ReferenceUse,
)
from continuum_db.session import session_scope
from continuum_imaging import UnsupportedImageError
from continuum_library import (
    AcceptSpec,
    CandidateDefaults,
    CatalogConflictError,
    CatalogInputError,
    CharacterLink,
    FileIntake,
    ReferenceCatalog,
    ReferenceInbox,
    ReferenceSpec,
    UrlEntry,
    candidate_view,
    reference_view,
)
from sqlalchemy.orm import Session

from tests.phase1_world import (
    EPISODE,
    MANGA,
    World,
    build_world,
    clean_domain_tables,
    mp4_bytes,
    picture,
    snapshot,
)


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


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any attempt to resolve or open an Internet connection fails the test."""

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the inbox tried to use the network")

    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


class TestLinkIntake:
    def test_links_are_stored_deduplicated_and_never_fetched(
        self, inbox: ReferenceInbox, no_network: None
    ) -> None:
        result = inbox.add_urls(
            [
                UrlEntry("https://art.example.org/p/1", "@inkfox", "cold palette", ("winter",)),
                UrlEntry("https://art.example.org/p/2"),
                UrlEntry("https://art.example.org/p/1"),  # duplicate in the paste
                UrlEntry("ftp://files.example.org/x.png"),
                UrlEntry("javascript:alert(1)"),
                UrlEntry("   "),
            ],
            label="Saturday collection",
            defaults=CandidateDefaults(
                origin=ReferenceOrigin.FAN_ART,
                suggested_class=ReferenceClass.MOOD,
                intended_uses=(ReferenceUse.OUTFIT, ReferenceUse.MONSTER_DESIGN),
                tags=("collection",),
            ),
        )
        assert [c.source_url for c in result.created] == [
            "https://art.example.org/p/1",
            "https://art.example.org/p/2",
        ]
        assert len(result.skipped) == 3
        first = candidate_view(result.created[0])
        assert first["creator_handle"] == "@inkfox"
        assert first["tags"] == ["collection", "winter"]
        assert first["intended_uses"] == ["OUTFIT", "MONSTER_DESIGN"]
        assert first["has_file"] is False and first["status"] == "INBOX"

        again = inbox.add_urls([UrlEntry("https://art.example.org/p/2")])
        assert again.created == []
        assert again.skipped[0]["reason"] == "already in the inbox or library"
        counts = {str(batch.id): c for batch, c in inbox.batches()}
        assert counts[str(result.batch.id)] == {"INBOX": 2}

    def test_a_link_is_accepted_only_with_an_attached_image(
        self, inbox: ReferenceInbox, catalog: ReferenceCatalog, no_network: None
    ) -> None:
        link = inbox.add_urls(
            [UrlEntry("https://art.example.org/p/9", "@quill")],
            defaults=CandidateDefaults(suggested_class=ReferenceClass.CANON),
        ).created[0]
        with pytest.raises(CatalogInputError, match="not fetched"):
            inbox.accept(link.id, link.row_version)
        attached = inbox.attach_image(link.id, link.row_version, picture(11))
        item = inbox.accept(attached.id, attached.row_version)
        assert item.origin is ReferenceOrigin.FAN_ART
        assert item.source_url == "https://art.example.org/p/9"
        assert item.creator_handle == "@quill"
        assert item.provenance["kind"] == "inbox"
        assert inbox.candidate(link.id).status is CandidateStatus.ACCEPTED
        # Once in the library, the same link is not taken in again.
        assert inbox.add_urls([UrlEntry("https://art.example.org/p/9")]).created == []

    def test_a_link_candidate_keeps_its_link(self, inbox: ReferenceInbox) -> None:
        link = inbox.add_urls([UrlEntry("https://art.example.org/p/3")]).created[0]
        with pytest.raises(CatalogInputError):
            inbox.update(link.id, link.row_version, source_url="")
        with pytest.raises(CatalogInputError):
            inbox.attach_image(link.id, link.row_version, b"not an image")


def new(result: FileIntake) -> Any:
    """The candidate a file intake created (it must not be a duplicate)."""
    assert not result.duplicate, "expected a new candidate, got a duplicate"
    return result.candidate


class TestFileIntake:
    def test_bulk_images_land_in_the_library_root_not_the_vault(
        self, inbox: ReferenceInbox, catalog: ReferenceCatalog, world: World
    ) -> None:
        vault_before = snapshot(world.vault)
        batch = inbox.create_batch(IntakeKind.IMAGE, label="folder drop")
        candidates = [
            new(
                inbox.add_file(
                    picture(seed),
                    IntakeKind.IMAGE,
                    batch_id=batch.id,
                    display_name=f"C:\\Users\\someone\\Pictures\\ref-{seed}.png",
                    creator_handle="@inkfox",
                    defaults=CandidateDefaults(tags=("wardrobe",)),
                )
            )
            for seed in range(1, 6)
        ]
        # Only the last segment of a client-supplied name is kept, for display.
        assert candidates[0].display_name == "ref-1.png"
        library = world.data_home / "library"
        assert sum(1 for p in library.rglob("*") if p.is_file()) == 5
        assert snapshot(world.vault) == vault_before
        data, _medium = inbox.candidate_bytes(candidates[2])
        assert data == picture(3)

        accepted, skipped = inbox.bulk_accept(
            [c.id for c in candidates[:3]],
            AcceptSpec(reference_class=ReferenceClass.CANON, uses=(ReferenceUse.OUTFIT,)),
        )
        assert len(accepted) == 3 and skipped == []
        view = reference_view(catalog, accepted[0])
        assert [(d["value"], d["origin_label"]) for d in view["descriptors"]] == [
            ("wardrobe", "USER TAGGED")
        ]
        assert view["uses"] == ["OUTFIT"]
        assert view["provenance"]["batch_id"] == str(batch.id)

        # Already-triaged candidates are skipped, not accepted twice.
        again, skipped = inbox.bulk_accept(
            [candidates[0].id, candidates[3].id], AcceptSpec(reference_class=ReferenceClass.MOOD)
        )
        assert len(again) == 1
        assert skipped == [{"id": str(candidates[0].id), "reason": "not in the inbox"}]

    def test_accepting_needs_a_class(self, inbox: ReferenceInbox) -> None:
        unsure = new(inbox.add_file(picture(12), IntakeKind.SCREENSHOT))
        accepted, skipped = inbox.bulk_accept([unsure.id])
        assert accepted == [] and "canon, technique" in skipped[0]["reason"]
        assert inbox.candidate(unsure.id).status is CandidateStatus.INBOX

    def test_accepting_with_a_full_spec_links_characters(
        self, inbox: ReferenceInbox, catalog: ReferenceCatalog
    ) -> None:
        hero = catalog.create_character("Aster Vale")
        shot = new(
            inbox.add_file(picture(13), IntakeKind.SCREENSHOT, source_url="https://x.example/1")
        )
        item = inbox.accept(
            shot.id,
            shot.row_version,
            AcceptSpec(
                base=ReferenceSpec(
                    reference_class=ReferenceClass.CANON,
                    origin=ReferenceOrigin.OFFICIAL_ART,
                    characters=(CharacterLink(hero.id, CharacterAspect.EXPRESSION),),
                ),
                label="Surprised",
            ),
        )
        assert item.origin is ReferenceOrigin.FAN_ART  # the candidate's declared origin wins
        assert item.label == "Surprised"
        assert catalog.list_references(character_id=hero.id) == [item]

    def test_clips_are_kept_and_frames_become_references(
        self, inbox: ReferenceInbox, catalog: ReferenceCatalog, world: World
    ) -> None:
        clip = new(
            inbox.add_file(
                mp4_bytes(7),
                IntakeKind.VIDEO,
                display_name="fight-reel.mp4",
                source_url="https://video.example.org/v/42",
                creator_handle="@animator",
                defaults=CandidateDefaults(
                    suggested_class=ReferenceClass.TECHNIQUE, intended_uses=(ReferenceUse.POSE,)
                ),
            )
        )
        with pytest.raises(CatalogInputError, match="Capture a frame"):
            inbox.accept(clip.id, clip.row_version)

        frame = new(inbox.add_clip_frame(clip.id, 61_500, picture(14, (320, 180))))
        assert frame.intake_kind is IntakeKind.SCREENSHOT
        assert frame.capture["kind"] == "clip_frame"
        assert frame.capture["video_locator"].endswith("#t=00:01:01.500")
        assert frame.creator_handle == "@animator" and frame.batch_id == clip.batch_id

        item = inbox.accept(frame.id, frame.row_version)
        assert item.reference_class is ReferenceClass.TECHNIQUE
        assert item.provenance["capture"]["from_candidate"] == str(clip.id)
        assert [u.use for u in catalog.uses(item.id)] == [ReferenceUse.POSE]
        # The clip itself stays in the inbox, untouched.
        assert inbox.candidate(clip.id).status is CandidateStatus.INBOX

    def test_frames_from_held_episodes_keep_their_source(
        self, inbox: ReferenceInbox, catalog: ReferenceCatalog, world: World
    ) -> None:
        vault_before = snapshot(world.vault)
        shot = new(
            inbox.add_held_frame(
                world.id_of(EPISODE),
                5_000,
                picture(15, (320, 180)),
                defaults=CandidateDefaults(
                    origin=ReferenceOrigin.SOURCE, suggested_class=ReferenceClass.CONTINUITY
                ),
            )
        )
        assert shot.capture["kind"] == "held_video_frame"
        assert shot.display_name.endswith("@ 00:00:05.000")
        item = inbox.accept(shot.id, shot.row_version)
        assert item.provenance["kind"] == "source_frame"
        position = catalog.source_position(item)
        assert position["media_id"] == world.id_of(EPISODE) and position["time_ms"] == 5_000
        assert snapshot(world.vault) == vault_before

        with pytest.raises(CatalogInputError):
            new(inbox.add_held_frame(world.id_of(MANGA), 0, picture(16)))

    @pytest.mark.parametrize(
        ("data", "kind", "error"),
        [
            (b"\x00\x00\x00\x18nope" + b"\0" * 64, IntakeKind.VIDEO, CatalogInputError),
            (b"<html></html>", IntakeKind.IMAGE, CatalogInputError),
            (b"MZ\x90\x00", IntakeKind.SCREENSHOT, CatalogInputError),
            (b"%PDF-1.4", IntakeKind.IMAGE, CatalogInputError),
            # Claims to be a JPEG, is not decodable.
            (b"\xff\xd8\xff\xe0" + b"\0" * 64, IntakeKind.IMAGE, UnsupportedImageError),
        ],
    )
    def test_only_images_and_clips_are_taken_in(
        self, inbox: ReferenceInbox, data: bytes, kind: IntakeKind, error: type[Exception]
    ) -> None:
        with pytest.raises(error):
            new(inbox.add_file(data, kind))
        assert inbox.candidates() == []

    def test_capture_metadata_is_bounded_and_pathless(self, inbox: ReferenceInbox) -> None:
        shot = new(
            inbox.add_file(
                picture(17),
                IntakeKind.SCREENSHOT,
                capture={
                    "kind": "screen",
                    "path": "C:\\ContinuumVault\\x.png",
                    "note": "x" * 900,
                    "nested": {"a": 1},
                },
            )
        )
        assert shot.capture == {"kind": "screen", "detected_format": "PNG"}

    def test_production_origins_cannot_be_declared(self, inbox: ReferenceInbox) -> None:
        with pytest.raises(CatalogInputError):
            new(
                inbox.add_file(
                    picture(18),
                    IntakeKind.IMAGE,
                    defaults=CandidateDefaults(origin=ReferenceOrigin.GENERATED),
                )
            )


class TestTriage:
    def test_update_dismiss_restore_and_conflicts(
        self, inbox: ReferenceInbox, session: Session
    ) -> None:
        a = new(inbox.add_file(picture(20), IntakeKind.IMAGE))
        b = new(inbox.add_file(picture(21), IntakeKind.IMAGE))
        session.commit()

        stale = a.row_version
        a = inbox.update(a.id, a.row_version, tags=["night"], suggested_class="MOOD")
        session.commit()
        with pytest.raises(CatalogConflictError):
            inbox.update(a.id, stale, notes="from an old tab")

        assert inbox.bulk_update([a.id, b.id], add_tags=["batch-2"], intended_uses=["STYLE"]) == 2
        assert inbox.candidate(a.id).tags == ["night", "batch-2"]
        assert inbox.candidate(b.id).intended_uses == ["STYLE"]
        with pytest.raises(CatalogInputError):
            inbox.update(b.id, inbox.candidate(b.id).row_version, asset_id=None)

        dismissed = inbox.dismiss(b.id, inbox.candidate(b.id).row_version)
        assert inbox.candidates() == [inbox.candidate(a.id)]
        assert inbox.candidates(status=CandidateStatus.DISMISSED) == [dismissed]
        with pytest.raises(CatalogConflictError):
            inbox.accept(b.id, dismissed.row_version, AcceptSpec(ReferenceClass.MOOD))
        restored = inbox.restore(b.id, dismissed.row_version)
        assert restored.status is CandidateStatus.INBOX

        item = inbox.accept(a.id, inbox.candidate(a.id).row_version)
        assert item.reference_class is ReferenceClass.MOOD
        with pytest.raises(CatalogConflictError):
            inbox.dismiss(a.id, inbox.candidate(a.id).row_version)
        assert inbox.bulk_update([a.id], notes="late") == 0
