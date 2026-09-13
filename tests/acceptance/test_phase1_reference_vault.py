"""The reference vault: held pages to references, Character Vault, Style Vault.

Under test (Phase 1 M1, expansion sections 17-20, 25, 28, 30):

* a page or a region of a held manga page becomes a reference named by
  content; its crop is a region beside the locator, never copied bytes;
* the reference navigates back to the exact page it came from;
* the same page serves many roles, over one observed asset;
* identity, wardrobe, acting and technique stay separate;
* user tags are USER TAGGED, analyzer output ANALYSIS DERIVED;
* fan art is recorded as fan art, with its link and creator, never fetched;
* visual modes reach characters only through project-scoped assignments;
* removing records never touches the source; stale edits conflict;
* hostile input is refused.

PostgreSQL (the isolated test database). All content is invented.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from continuum_config import Settings
from continuum_core import NormalizedRegion
from continuum_core.references import (
    CharacterAspect,
    DescriptorFacet,
    DescriptorOrigin,
    ModeScope,
    ModeTrigger,
    OutfitKind,
    PanelSourceRole,
    ProjectStanding,
    ReferenceClass,
    ReferenceOrigin,
    ReferenceUse,
    SubjectKind,
    TechniqueFacet,
    VisualModeCategory,
)
from continuum_db.models import LibraryAsset, LibraryAssetLocation, ReferenceItem
from continuum_db.session import session_scope
from continuum_imaging import probe
from continuum_library import (
    CatalogConflictError,
    CatalogInputError,
    CatalogNotFoundError,
    CharacterLink,
    DescriptorSpec,
    PanelSourceSpec,
    ReferenceCatalog,
    ReferenceSpec,
    StandingSpec,
    TechniqueLink,
    character_vault,
    reference_view,
    style_vault,
)
from continuum_storage import SourceChangedError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.phase1_world import (
    ART,
    EPISODE,
    GUIDE,
    MANGA,
    MANGA_ENTRIES,
    World,
    build_world,
    clean_domain_tables,
    picture,
    snapshot,
)

PROJECT = "demo-project"


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


def canon(**kwargs: object) -> ReferenceSpec:
    return ReferenceSpec(
        reference_class=ReferenceClass.CANON,
        origin=kwargs.pop("origin", ReferenceOrigin.SOURCE),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


class TestReferencesFromHeldPages:
    def test_region_of_a_page_roundtrips_to_the_exact_page(
        self, catalog: ReferenceCatalog, world: World
    ) -> None:
        region = NormalizedRegion(0.1, 0.2, 0.5, 0.25)
        item = catalog.add_from_source(world.id_of(MANGA), canon(region=region), page_index=1)

        assert item.locator == (f"zip:sha256:{world.sha256_of(MANGA)}#entry={MANGA_ENTRIES[1]}")
        assert item.unit_index == 1
        assert item.provenance["kind"] == "source_locator"
        assert "vault" not in str(item.provenance).lower()

        # The crop is a view: the full unit is the original page's exact bytes.
        assert catalog.unit_bytes(item) == world.page_bytes[MANGA_ENTRIES[1]]
        cropped = catalog.reference_image(item.id)
        whole = catalog.reference_image(item.id, crop=False)
        assert (cropped.width, cropped.height) == (150, 105)
        assert (whole.width, whole.height) == (300, 420)
        assert probe(cropped.data).mime == "image/webp"

        position = catalog.source_position(item)
        assert position == {
            "available": True,
            "media_id": world.id_of(MANGA),
            "page_index": 1,
            "time_ms": None,
            "held_name": MANGA.rsplit("/", 1)[-1],
        }

    def test_the_same_page_serves_many_roles_over_one_asset(
        self, catalog: ReferenceCatalog, session: Session, world: World
    ) -> None:
        hero = catalog.create_character("Aster Vale")
        face = catalog.add_from_source(
            world.id_of(MANGA),
            canon(
                region=NormalizedRegion(0.3, 0.1, 0.2, 0.2),
                characters=(CharacterLink(hero.id, CharacterAspect.FACE, preferred=True),),
                uses=(ReferenceUse.IDENTITY, ReferenceUse.EXPRESSION),
            ),
            page_index=0,
        )
        composition = catalog.add_from_source(
            world.id_of(MANGA),
            ReferenceSpec(
                reference_class=ReferenceClass.TECHNIQUE,
                origin=ReferenceOrigin.SOURCE,
                techniques=(TechniqueLink(TechniqueFacet.PAGE_COMPOSITION),),
                uses=(ReferenceUse.STYLE,),
            ),
            page_index=0,
        )
        plate = catalog.add_from_source(
            world.id_of(MANGA),
            canon(
                uses=(ReferenceUse.SOURCE_PLATE,),
                panel_sources=(
                    PanelSourceSpec(PROJECT, "S1E1", 1, PanelSourceRole.SOURCE_PLATE, chapter=1),
                ),
            ),
            page_index=0,
        )
        assert face.locator == composition.locator == plate.locator
        assert len({face.id, composition.id, plate.id}) == 3
        assert session.scalar(select(func.count()).select_from(LibraryAsset)) == 1
        assert session.scalar(select(func.count()).select_from(LibraryAssetLocation)) == 1
        assert [s.reference_id for s in catalog.panel_sources(PROJECT, episode="S1E1")] == [
            plate.id
        ]
        assert {u.use for u in catalog.uses(face.id)} == {
            ReferenceUse.IDENTITY,
            ReferenceUse.EXPRESSION,
        }

    def test_standalone_image_and_pdf_page(self, catalog: ReferenceCatalog, world: World) -> None:
        art = catalog.add_from_source(world.id_of(ART), canon(origin=ReferenceOrigin.OFFICIAL_ART))
        assert catalog.unit_bytes(art) == world.art_bytes
        assert catalog.source_position(art)["media_id"] == world.id_of(ART)

        page = catalog.add_from_source(world.id_of(GUIDE), canon(), pdf_page=3)
        assert page.locator.endswith("#page=3")
        assert catalog.source_position(page)["page_index"] == 2
        with pytest.raises(CatalogInputError):
            catalog.reference_image(page.id)
        with pytest.raises(CatalogInputError):
            catalog.add_from_source(
                world.id_of(GUIDE), canon(region=NormalizedRegion(0, 0, 0.5, 0.5)), pdf_page=1
            )
        with pytest.raises(CatalogInputError):
            catalog.add_panel_source(
                page.id, PanelSourceSpec(PROJECT, "S1E1", 2, PanelSourceRole.SOURCE_PLATE)
            )

    def test_frame_from_held_video_keeps_the_episode_and_instant(
        self, catalog: ReferenceCatalog, world: World
    ) -> None:
        frame = picture(21, (320, 180))
        item = catalog.add_from_frame(world.id_of(EPISODE), 754_120, frame, canon())
        assert item.locator.startswith("image:sha256:")
        assert item.provenance["video_locator"] == (
            f"video:sha256:{world.sha256_of(EPISODE)}#t=00:12:34.120"
        )
        assert catalog.unit_bytes(item) == frame
        position = catalog.source_position(item)
        assert position["media_id"] == world.id_of(EPISODE)
        assert position["time_ms"] == 754_120
        # The video was observed, not copied.
        assert not any((world.data_home / "library").rglob("*.mp4"))

    def test_removing_references_never_touches_the_source(
        self, catalog: ReferenceCatalog, session: Session, world: World
    ) -> None:
        before = snapshot(world.vault)
        items = [
            catalog.add_from_source(world.id_of(MANGA), canon(), page_index=i)
            for i in range(len(MANGA_ENTRIES))
        ]
        for item in items:
            catalog.remove_reference(item.id, item.row_version)
        session.commit()

        assert catalog.list_references() == []
        with pytest.raises(CatalogNotFoundError):
            catalog.reference(items[0].id)
        kept = catalog.reference(items[0].id, include_removed=True)
        assert kept.removed_at is not None
        assert reference_view(catalog, kept)["removed"] is True
        # Still viewable from history, and the source is byte-identical.
        assert catalog.unit_bytes(kept) == world.page_bytes[MANGA_ENTRIES[0]]
        assert session.scalar(select(func.count()).select_from(LibraryAsset)) == 1
        assert snapshot(world.vault) == before

    def test_a_changed_source_is_reported_not_served(
        self, catalog: ReferenceCatalog, world: World
    ) -> None:
        item = catalog.add_from_source(world.id_of(ART), canon())
        (world.vault / ART).write_bytes(picture(99))
        with pytest.raises(SourceChangedError):
            catalog.unit_bytes(item)
        (world.vault / ART).unlink()
        with pytest.raises(CatalogNotFoundError):
            catalog.unit_bytes(item)

    def test_unknown_media_and_bad_pages_are_input_errors(
        self, catalog: ReferenceCatalog, world: World
    ) -> None:
        with pytest.raises(CatalogInputError):
            catalog.add_from_source("m1_" + "f" * 32, canon(), page_index=0)
        with pytest.raises(CatalogInputError):
            catalog.add_from_source(world.id_of(MANGA), canon(), page_index=99)
        with pytest.raises(CatalogInputError):
            catalog.add_from_source(world.id_of(MANGA), canon(origin=ReferenceOrigin.GENERATED))


class TestUserAddedReferences:
    def test_fan_art_is_first_class_and_distinguishable(
        self, catalog: ReferenceCatalog, world: World
    ) -> None:
        hero = catalog.create_character("Aster Vale")
        winter = catalog.create_outfit(hero.id, "Winter coat", kind=OutfitKind.SOURCE_ALTERNATE)
        item = catalog.add_upload(
            picture(5),
            ReferenceSpec(
                reference_class=ReferenceClass.MOOD,
                origin=ReferenceOrigin.FAN_ART,
                source_url="https://art.example.org/works/123",
                creator_handle="@inkfox",
                uses=(ReferenceUse.OUTFIT, ReferenceUse.STYLE),
                characters=(CharacterLink(hero.id, CharacterAspect.OUTFIT, outfit_id=winter.id),),
            ),
        )
        assert item.origin is ReferenceOrigin.FAN_ART
        assert item.provenance["kind"] == "user_assertion"
        assert catalog.list_references(origin=ReferenceOrigin.FAN_ART) == [item]
        assert catalog.list_references(origin=ReferenceOrigin.SOURCE) == []
        view = reference_view(catalog, item)
        assert view["source_url"] == "https://art.example.org/works/123"
        assert view["creator_handle"] == "@inkfox"
        assert view["asset_origin"] == "USER_ADDED"
        # Stored under the writable library root, content-addressed.
        stored = list((world.data_home / "library").rglob("*"))
        assert any(p.is_file() for p in stored)

    @pytest.mark.parametrize(
        "url",
        [
            "javascript:alert(1)",
            "file:///C:/secret.png",
            "https://user:pass@example.org/x",
            "https://example.org/a b",
            "not a url",
        ],
    )
    def test_links_are_validated(self, catalog: ReferenceCatalog, url: str) -> None:
        with pytest.raises(CatalogInputError):
            catalog.add_upload(picture(6), canon(origin=ReferenceOrigin.FAN_ART, source_url=url))

    def test_only_images_are_accepted(self, catalog: ReferenceCatalog) -> None:
        from continuum_imaging import UnsupportedImageError

        with pytest.raises(UnsupportedImageError):
            catalog.add_upload(b"<svg xmlns='http://www.w3.org/2000/svg'/>", canon())
        with pytest.raises(UnsupportedImageError):
            catalog.add_upload(b"MZ\x90\x00", canon())


class TestCharacterVault:
    def test_identity_wardrobe_and_acting_are_organized_apart(
        self, catalog: ReferenceCatalog, world: World
    ) -> None:
        hero = catalog.create_character(
            "Aster Vale", scale_notes="a head shorter than her mentor", posture_notes="upright"
        )
        uniform = catalog.create_outfit(hero.id, "Guild uniform")
        festival = catalog.create_outfit(
            hero.id, "Festival yukata", kind=OutfitKind.PROJECT, project_key=PROJECT
        )

        def page(
            index: int, *links: CharacterLink, origin: ReferenceOrigin = ReferenceOrigin.SOURCE
        ):
            return catalog.add_from_source(
                world.id_of(MANGA),
                ReferenceSpec(
                    reference_class=ReferenceClass.CANON, origin=origin, characters=links
                ),
                page_index=index,
            )

        face = page(0, CharacterLink(hero.id, CharacterAspect.FACE, preferred=True))
        second_face = page(1, CharacterLink(hero.id, CharacterAspect.FACE))
        body = page(2, CharacterLink(hero.id, CharacterAspect.FULL_BODY))
        outfit = page(
            1, CharacterLink(hero.id, CharacterAspect.OUTFIT, outfit_id=uniform.id, preferred=True)
        )
        smile = page(0, CharacterLink(hero.id, CharacterAspect.EXPRESSION))
        fan = catalog.add_upload(
            picture(7),
            ReferenceSpec(
                reference_class=ReferenceClass.MOOD,
                origin=ReferenceOrigin.FAN_ART,
                characters=(CharacterLink(hero.id, CharacterAspect.OUTFIT, outfit_id=festival.id),),
            ),
        )
        catalog.set_standing(
            face.id, StandingSpec(PROJECT, ProjectStanding.CANONICAL_FOR_PROJECT, hero.id)
        )
        catalog.set_standing(
            outfit.id, StandingSpec(PROJECT, ProjectStanding.PREFERRED_FOR_CURRENT_LOOK, hero.id)
        )

        vault = character_vault(catalog, hero.id)
        identity = vault["identity"]
        assert [c["reference"]["id"] for c in identity["FACE"]] == [
            str(face.id),
            str(second_face.id),
        ]
        assert identity["FACE"][0]["preferred"] is True
        assert [c["reference"]["id"] for c in identity["FULL_BODY"]] == [str(body.id)]
        assert [c["reference"]["id"] for c in vault["acting"]["EXPRESSION"]] == [str(smile.id)]
        assert "OUTFIT" not in identity and "FACE" not in vault["acting"]

        outfits = {o["name"]: o for o in vault["wardrobe"]["outfits"]}
        assert [c["reference"]["id"] for c in outfits["Guild uniform"]["references"]] == [
            str(outfit.id)
        ]
        assert outfits["Festival yukata"]["kind"] == "PROJECT"
        assert outfits["Festival yukata"]["references"][0]["reference"]["origin"] == "FAN_ART"
        assert {c["reference"]["id"] for c in vault["preferred"]} == {str(face.id), str(outfit.id)}
        assert vault["sources"] == {"SOURCE": 5, "FAN_ART": 1}
        assert vault["project_standing"][PROJECT] == {
            "CANONICAL_FOR_PROJECT": [str(face.id)],
            "PREFERRED_FOR_CURRENT_LOOK": [str(outfit.id)],
        }
        assert vault["character"]["scale_notes"] == "a head shorter than her mentor"
        assert vault["reference_count"] == 6

        # Filters answer production questions directly.
        assert catalog.list_references(character_id=hero.id, aspect=CharacterAspect.FACE) == [
            second_face,
            face,
        ]
        assert catalog.list_references(outfit_id=festival.id) == [fan]
        assert catalog.list_references(
            project_key=PROJECT, standing=ProjectStanding.CANONICAL_FOR_PROJECT
        ) == [face]

    def test_outfits_belong_to_their_character(
        self, catalog: ReferenceCatalog, world: World
    ) -> None:
        hero = catalog.create_character("Aster Vale")
        mentor = catalog.create_character("Orin Holt")
        coat = catalog.create_outfit(mentor.id, "Travel coat")
        item = catalog.add_from_source(world.id_of(MANGA), canon(), page_index=0)
        with pytest.raises(CatalogInputError):
            catalog.link_character(
                item.id, CharacterLink(hero.id, CharacterAspect.OUTFIT, outfit_id=coat.id)
            )
        with pytest.raises(CatalogInputError):
            catalog.create_outfit(hero.id, "Stray", project_key=PROJECT)
        with pytest.raises(CatalogInputError):
            catalog.create_outfit(hero.id, "Project look", kind=OutfitKind.PROJECT)

    def test_monsters_are_subjects_too(self, catalog: ReferenceCatalog) -> None:
        catalog.create_character("Aster Vale")
        beast = catalog.create_character("Hollow Stag", subject_kind=SubjectKind.MONSTER)
        assert catalog.list_characters(SubjectKind.MONSTER) == [beast]

    def test_stale_edits_conflict(self, catalog: ReferenceCatalog, session: Session) -> None:
        hero = catalog.create_character("Aster Vale")
        session.commit()
        version = hero.row_version
        catalog.update_character(hero.id, version, summary="first edit")
        session.commit()
        with pytest.raises(CatalogConflictError):
            catalog.update_character(hero.id, version, summary="edit from a stale form")
        with pytest.raises(CatalogConflictError):
            catalog.remove_character(hero.id, version)
        with pytest.raises(CatalogInputError):
            catalog.update_character(hero.id, hero.row_version, id=str(uuid.uuid4()))


class TestStyleVaultAndVisualModes:
    def test_technique_references_by_mode_and_facet(
        self, catalog: ReferenceCatalog, world: World
    ) -> None:
        horror = catalog.create_visual_mode("Threat close-ups", VisualModeCategory.HORROR_THREAT)
        chibi = catalog.create_visual_mode("Comic squash", VisualModeCategory.COMEDIC_DEFORMATION)
        page = catalog.add_from_source(
            world.id_of(MANGA),
            ReferenceSpec(
                reference_class=ReferenceClass.TECHNIQUE,
                origin=ReferenceOrigin.SOURCE,
                techniques=(
                    TechniqueLink(TechniqueFacet.SCREENTONE, horror.id),
                    TechniqueLink(TechniqueFacet.PAGE_COMPOSITION),
                ),
            ),
            page_index=2,
        )
        squash = catalog.add_upload(
            picture(8),
            ReferenceSpec(
                reference_class=ReferenceClass.TECHNIQUE,
                origin=ReferenceOrigin.FAN_ART,
                techniques=(TechniqueLink(TechniqueFacet.COMEDY, chibi.id),),
            ),
        )
        vault = style_vault(catalog)
        modes = {m["name"]: m for m in vault["modes"]}
        assert [c["reference"]["id"] for c in modes["Threat close-ups"]["references"]] == [
            str(page.id)
        ]
        assert [c["reference"]["id"] for c in modes["Comic squash"]["references"]] == [
            str(squash.id)
        ]
        assert set(vault["by_facet"]) == {"SCREENTONE", "PAGE_COMPOSITION", "COMEDY"}
        assert catalog.list_references(visual_mode_id=chibi.id) == [squash]

    def test_modes_apply_to_scopes_without_rewriting_identity(
        self, catalog: ReferenceCatalog, session: Session
    ) -> None:
        hero = catalog.create_character("Aster Vale")
        session.commit()
        identity_version = hero.row_version
        night = catalog.create_visual_mode("Intimate night", VisualModeCategory.INTIMATE)
        chibi = catalog.create_visual_mode("Comic squash", VisualModeCategory.COMEDIC_DEFORMATION)
        dream = catalog.create_visual_mode("Memory haze", VisualModeCategory.MEMORY_DREAM)

        catalog.assign_visual_mode(PROJECT, dream.id, ModeScope.EPISODE, episode="S1E1")
        catalog.assign_visual_mode(
            PROJECT, night.id, ModeScope.SEQUENCE, episode="S1E1", page_from=30, page_to=36
        )
        involuntary = catalog.assign_visual_mode(
            PROJECT,
            chibi.id,
            ModeScope.PANEL,
            trigger=ModeTrigger.SCENE_TONE,
            episode="S1E1",
            page_from=35,
            panel=2,
            character_id=hero.id,
        )
        controlled = catalog.assign_visual_mode(
            PROJECT,
            chibi.id,
            ModeScope.EVENT,
            trigger=ModeTrigger.CHARACTER_CONTROLLED,
            event_label="shrinks to slip through the gate",
            character_id=hero.id,
        )
        session.commit()

        in_effect = catalog.modes_in_effect(PROJECT, "S1E1", 35, 2)
        assert [a.scope for a in in_effect] == [
            ModeScope.EPISODE,
            ModeScope.SEQUENCE,
            ModeScope.PANEL,
        ]
        assert [a.visual_mode_id for a in catalog.modes_in_effect(PROJECT, "S1E1", 40)] == [
            dream.id
        ]
        assert catalog.modes_in_effect("other-project", "S1E1", 35, 2) == []

        vault = character_vault(catalog, hero.id)
        assert {m["assignment_id"] for m in vault["scoped_visual_modes"]} == {
            str(involuntary.id),
            str(controlled.id),
        }
        session.refresh(hero)
        assert hero.row_version == identity_version

    @pytest.mark.parametrize(
        ("scope", "kwargs"),
        [
            (ModeScope.EPISODE, {}),
            (ModeScope.SCENE, {"episode": "S1E1"}),
            (ModeScope.SEQUENCE, {"episode": "S1E1", "page_from": 9, "page_to": 3}),
            (ModeScope.PANEL, {"episode": "S1E1", "page_from": 3}),
            (ModeScope.EVENT, {"event_label": "   "}),
            (ModeScope.EVENT, {"event_label": "x", "trigger": ModeTrigger.CHARACTER_CONTROLLED}),
        ],
    )
    def test_assignments_need_their_target(
        self, catalog: ReferenceCatalog, scope: ModeScope, kwargs: dict[str, object]
    ) -> None:
        mode = catalog.create_visual_mode("Any", VisualModeCategory.ATMOSPHERE)
        with pytest.raises(CatalogInputError):
            catalog.assign_visual_mode(PROJECT, mode.id, scope, **kwargs)  # type: ignore[arg-type]


class TestDescriptorsAndHostileInput:
    def test_user_and_analysis_descriptors_are_labelled(
        self, catalog: ReferenceCatalog, world: World
    ) -> None:
        item = catalog.add_from_source(
            world.id_of(MANGA),
            canon(descriptors=(DescriptorSpec(DescriptorFacet.SEASON_WEATHER, "snow"),)),
            page_index=0,
        )
        catalog.add_descriptor(
            item.id,
            DescriptorSpec(DescriptorFacet.SHOT_TYPE, "close-up"),
            origin=DescriptorOrigin.ANALYSIS,
            analyzer_ref="synthetic-analyzer@1",
            confidence=0.7,
        )
        labels = {
            (d["value"], d["origin_label"]) for d in reference_view(catalog, item)["descriptors"]
        }
        assert labels == {("snow", "USER TAGGED"), ("close-up", "ANALYSIS DERIVED")}
        with pytest.raises(CatalogInputError):
            catalog.add_descriptor(
                item.id, DescriptorSpec(DescriptorFacet.MOOD, "calm"), analyzer_ref="fake"
            )
        with pytest.raises(CatalogInputError):
            catalog.add_descriptor(
                item.id,
                DescriptorSpec(DescriptorFacet.MOOD, "calm"),
                origin=DescriptorOrigin.ANALYSIS,
            )

    @pytest.mark.parametrize(
        "project_key", ["../escape", "C:\\ContinuumVault", "Demo Project", "", "a" * 81, "x/y"]
    )
    def test_hostile_project_keys(
        self, catalog: ReferenceCatalog, world: World, project_key: str
    ) -> None:
        item = catalog.add_from_source(world.id_of(MANGA), canon(), page_index=0)
        with pytest.raises(CatalogInputError):
            catalog.set_standing(item.id, StandingSpec(project_key, ProjectStanding.USEFUL))
        with pytest.raises(CatalogInputError):
            catalog.add_panel_source(
                item.id, PanelSourceSpec(project_key, "S1E1", 1, PanelSourceRole.COMPOSITION)
            )

    @pytest.mark.parametrize("episode", ["../S1", "S1 E1", "", "S1/E1", "S1\x00"])
    def test_hostile_episodes(self, catalog: ReferenceCatalog, world: World, episode: str) -> None:
        item = catalog.add_from_source(world.id_of(MANGA), canon(), page_index=0)
        with pytest.raises(CatalogInputError):
            catalog.add_panel_source(
                item.id, PanelSourceSpec(PROJECT, episode, 1, PanelSourceRole.COMPOSITION)
            )

    def test_control_characters_and_locked_fields(
        self, catalog: ReferenceCatalog, world: World
    ) -> None:
        with pytest.raises(CatalogInputError):
            catalog.create_character("Aster\x1b[31m")
        item = catalog.add_from_source(world.id_of(MANGA), canon(), page_index=0)
        for key in ("locator", "asset_id", "provenance", "region_x"):
            with pytest.raises(CatalogInputError):
                catalog.update_reference(item.id, item.row_version, **{key: "x"})
        with pytest.raises(CatalogInputError):
            catalog.update_reference(item.id, item.row_version, origin="GENERATED")
        with pytest.raises(CatalogInputError):
            catalog.list_references(locator_hash="%")

    def test_locations_are_vault_relative_observations(
        self, catalog: ReferenceCatalog, session: Session, world: World
    ) -> None:
        catalog.add_from_source(world.id_of(MANGA), canon(), page_index=0)
        catalog.add_upload(picture(3), canon(origin=ReferenceOrigin.USER_CREATED))
        for location in session.execute(select(LibraryAssetLocation)).scalars():
            assert not Path(location.relative_path).is_absolute()
            assert "\\" not in location.relative_path
            assert str(world.root) not in location.relative_path
        for item in session.execute(select(ReferenceItem)).scalars():
            assert str(world.root) not in str(item.provenance)
